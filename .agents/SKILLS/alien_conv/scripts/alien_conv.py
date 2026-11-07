"""JSON-lines stdin/stdout bridge: local microphone STT and Windows SAPI TTS."""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import time
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]


def emit(event: str, **fields: Any) -> None:
    """Write one machine-readable event to stdout."""
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def find_cached_whisper_model(model_name: str) -> Path | None:
    hf_home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    hf_hub = Path(os.environ.get("HF_HUB_CACHE", hf_home / "hub"))
    if model_name in ("large-v3-turbo", "turbo"):
        repo_names = (
            "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo",
            "models--Systran--faster-whisper-large-v3-turbo",
        )
    elif "/" in model_name:
        repo_names = ("models--" + model_name.replace("/", "--"),)
    else:
        repo_names = ()
    for repo_name in repo_names:
        snapshots = hf_hub / repo_name / "snapshots"
        revisions = sorted(snapshots.glob("*"), key=lambda path: path.stat().st_mtime, reverse=True) if snapshots.is_dir() else []
        for revision in revisions:
            if (revision / "model.bin").is_file():
                return revision
    return None


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="JSONL stdin/stdout bridge: microphone -> local Whisper STT; host text -> Windows SAPI TTS"
    )
    parser.add_argument("--stt-model", default="large-v3-turbo")
    parser.add_argument("--language", default="en", help="spoken language code, or auto")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--tts-voice", default="zira", help="substring of a local SAPI voice name or token ID")
    parser.add_argument("--input-device", help="sounddevice input index or name")
    parser.add_argument("--max-seconds", type=float, default=30)
    parser.add_argument("--silence-seconds", type=float, default=1.0, help="end an utterance after this much silence")
    parser.add_argument("--start-timeout", type=float, default=10, help="stop a listen command if speech never starts")
    parser.add_argument("--vad-threshold", type=float, default=0.012, help="audio RMS threshold for speech/silence")
    parser.add_argument("--allow-model-download", action="store_true", help="explicitly allow downloading Whisper weights when no local copy is found")
    parser.add_argument("--list-audio-devices", action="store_true")
    parser.add_argument("--list-voices", action="store_true")
    return parser


def list_audio_devices() -> list[dict[str, Any]]:
    import sounddevice as sd

    devices = []
    for index, device in enumerate(sd.query_devices()):
        if int(device["max_input_channels"]) > 0:
            devices.append({"index": index, "name": str(device["name"]), "input_channels": int(device["max_input_channels"])})
    return devices


def list_sapi_voices() -> list[tuple[str, str]]:
    if os.name != "nt":
        raise RuntimeError("Windows SAPI voices are available only on Windows.")
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise RuntimeError("Install this skill's scripts/requirements.txt to use Windows SAPI.") from exc
    pythoncom.CoInitialize()
    try:
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        tokens = voice.GetVoices()
        return [(str(tokens.Item(i).GetDescription()), str(tokens.Item(i).Id)) for i in range(tokens.Count)]
    finally:
        pythoncom.CoUninitialize()


def speak_sapi(text: str, requested_voice: str) -> str:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    try:
        sapi = win32com.client.Dispatch("SAPI.SpVoice")
        tokens = sapi.GetVoices()
        matches = [
            tokens.Item(i)
            for i in range(tokens.Count)
            if requested_voice.casefold() in (
                str(tokens.Item(i).GetDescription()) + " " + str(tokens.Item(i).Id)
            ).casefold()
        ]
        if not matches:
            choices = ", ".join(str(tokens.Item(i).GetDescription()) for i in range(tokens.Count))
            raise RuntimeError(f"No SAPI voice matched {requested_voice!r}. Available voices: {choices}")
        selected = matches[0]
        sapi.Voice = selected
        sapi.Speak(text)
        return str(selected.GetDescription())
    finally:
        pythoncom.CoUninitialize()


def record_utterance(
    sample_rate: int,
    max_seconds: float,
    silence_seconds: float,
    start_timeout: float,
    threshold: float,
    device: str | int | None,
    stop_event: Any | None = None,
) -> Any | None:
    """Capture until speech is followed by silence; return None on no speech."""
    import numpy as np
    import sounddevice as sd

    if isinstance(device, str) and device.isdecimal():
        device = int(device)
    blocks: queue.Queue[Any] = queue.Queue()

    def on_audio(indata: Any, _frames: int, _time_info: Any, status: Any) -> None:
        if status:
            print(f"Microphone status: {status}", file=sys.stderr, flush=True)
        blocks.put(indata[:, 0].copy())

    audio: list[Any] = []
    speech_started = False
    last_voice_at = 0.0
    started_at = time.monotonic()
    with sd.InputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="float32",
        device=device,
        blocksize=max(1, int(sample_rate * 0.05)),
        callback=on_audio,
    ):
        while time.monotonic() - started_at < max_seconds and not (stop_event and stop_event.is_set()):
            try:
                block = blocks.get(timeout=0.1)
            except queue.Empty:
                if not speech_started and time.monotonic() - started_at >= start_timeout:
                    return None
                if speech_started and time.monotonic() - last_voice_at >= silence_seconds:
                    break
                continue
            now = time.monotonic()
            level = float(np.sqrt(np.mean(np.square(block))))
            if level >= threshold:
                speech_started = True
                last_voice_at = now
            if speech_started:
                audio.append(block)
                if now - last_voice_at >= silence_seconds:
                    break
        if not speech_started or (stop_event and stop_event.is_set()):
            return None
    return np.concatenate(audio).astype(np.float32, copy=False)


def handle_command(command: dict[str, Any], *, stt: Any, args: argparse.Namespace, voice: str) -> bool:
    """Handle one host command. Return False when the host requests shutdown."""
    action = command.get("command")
    if action == "stop":
        emit("stopped")
        return False
    if action == "speak":
        text = command.get("text")
        if not isinstance(text, str) or not text.strip():
            emit("error", code="invalid_speak_command", message="speak command requires non-empty string text")
            return True
        emit("speaking")
        selected_voice = speak_sapi(text, voice)
        emit("spoken", voice=selected_voice)
        return True
    if action == "listen":
        emit("listening", silence_seconds=args.silence_seconds)
        audio = record_utterance(
            16_000,
            args.max_seconds,
            args.silence_seconds,
            args.start_timeout,
            args.vad_threshold,
            args.input_device,
        )
        if audio is None:
            emit("no_speech")
            return True
        language = None if args.language.casefold() == "auto" else args.language
        segments, info = stt.transcribe(audio, language=language, vad_filter=True)
        transcript = " ".join(segment.text.strip() for segment in segments).strip()
        emit("transcript", text=transcript, language=getattr(info, "language", language))
        return True
    emit("error", code="unknown_command", message="command must be listen, speak, or stop")
    return True


def main() -> int:
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
    args = make_parser().parse_args()
    try:
        if args.list_audio_devices:
            emit("audio_devices", items=list_audio_devices())
            return 0
        if args.list_voices:
            emit("voices", items=[{"name": name, "id": token_id} for name, token_id in list_sapi_voices()])
            return 0
        if os.name != "nt":
            raise RuntimeError("Alien Conversation audio I/O currently requires Windows for SAPI.")
        if not 0 < args.max_seconds <= 120 or not 0 < args.silence_seconds <= 10 or args.start_timeout <= 0 or args.vad_threshold < 0:
            raise ValueError("max-seconds, silence-seconds, start-timeout, or vad-threshold is out of range")

        if not args.allow_model_download:
            os.environ["HF_HUB_OFFLINE"] = "1"
        else:
            os.environ.pop("HF_HUB_OFFLINE", None)
        from faster_whisper import WhisperModel

        cache_dir = SKILL_ROOT / ".models" / "faster-whisper"
        cache_dir.mkdir(parents=True, exist_ok=True)
        model_path: str = args.stt_model
        cached_model = find_cached_whisper_model(args.stt_model)
        if cached_model:
            model_path = str(cached_model)
            print(f"Reusing cached faster-whisper model: {cached_model}", file=sys.stderr, flush=True)
        elif not args.allow_model_download:
            raise RuntimeError(
                f"Whisper model {args.stt_model!r} is not in the local faster-whisper cache. "
                "No model download was started. If you want to download it, explicitly rerun "
                "with --allow-model-download."
            )
        print(f"Loading faster-whisper {args.stt_model} on {args.device} ({args.compute_type})", file=sys.stderr, flush=True)
        stt = WhisperModel(
            model_path,
            device=args.device,
            compute_type=args.compute_type,
            download_root=str(cache_dir),
            local_files_only=not args.allow_model_download,
        )
        voices = list_sapi_voices()
        if not voices:
            raise RuntimeError("No Windows SAPI voices are installed.")
        voice = args.tts_voice
        selected_voice = speak_sapi("Hi, this is Alien Conversation. I'm up and running.", voice)
        emit(
            "ready",
            protocol="alien-conv-jsonl-v1",
            stt="faster-whisper " + args.stt_model,
            tts="Windows SAPI",
            voice=selected_voice,
            input_device=args.input_device,
            commands=["listen", "speak", "stop"],
        )
        for line in sys.stdin:
            try:
                command = json.loads(line)
                if not isinstance(command, dict):
                    raise ValueError("each input line must be a JSON object")
                if not handle_command(command, stt=stt, args=args, voice=voice):
                    return 0
            except json.JSONDecodeError as exc:
                emit("error", code="invalid_json", message=str(exc))
            except Exception as exc:
                emit("error", code="command_failed", message=str(exc))
                print(f"Command failed: {exc}", file=sys.stderr, flush=True)
        emit("stopped", reason="stdin closed")
        return 0
    except KeyboardInterrupt:
        emit("stopped", reason="interrupted")
        return 0
    except Exception as exc:
        emit("fatal", message=str(exc))
        print(f"Alien Conversation startup failed: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
