"""Manual Alien Conversation chat UI: microphone -> local STT -> Ollama -> local TTS.

QUICK START (Windows Command Prompt)
====================================
Run this single line from any directory. It repairs the skill's Python 3.13
virtual environment if needed, installs dependencies for all bundled tools,
activates it, and starts the chat using Gemma 4 12B and SAPI Zira. Setup is
larger because the shared environment also includes Pipecat, PyTorch, and ML TTS:

    py -3.13 -m venv --upgrade "C:\dev\personal\.repos\tts\.agents\SKILLS\alien_conv\.venv" && powershell -NoProfile -ExecutionPolicy Bypass -File "C:\dev\personal\.repos\tts\.agents\SKILLS\alien_conv\scripts\setup.ps1" && call "C:\dev\personal\.repos\tts\.agents\SKILLS\alien_conv\.venv\Scripts\activate.bat" && python "C:\dev\personal\.repos\tts\.agents\SKILLS\alien_conv\scripts\local_test.py" --model gemma4:12b --input-device 1 --tts-engine sapi5 --tts-voice TTS_MS_EN-US_ZIRA_11.0

The command assumes the repository is at C:\dev\personal\.repos\tts and
the Python launcher has Python 3.13 registered. It only repairs/recreates the
venv metadata; setup then installs this skill's declared requirements. The
Whisper model is not downloaded by default. If its weights are not already
cached, startup stops with instructions; downloading is an explicit opt-in via
--allow-stt-model-download.

WHAT THIS SCRIPT DOES
=====================
This is a standalone, manual local conversation runner for trying the audio
loop without an MCP client. It is separate from alien_conv.py, the host-driven
stdin/stdout JSONL bridge. This script calls the configured local Ollama
server itself; it does not send the conversation to the calling host.
Unlike pipecat_conv.py, this runner does not use Pipecat; its small control loop
captures a turn, transcribes it, gets an Ollama reply, speaks it, then listens
again. Pipecat keeps its own pipeline and turn management in that separate POC.

Audio and conversation flow:
    Microphone -> faster-whisper transcription -> local Ollama chat -> local TTS

The default stack is faster-whisper large-v3-turbo on CUDA with float16,
Ollama gemma4:12b at http://localhost:11434, and Windows SAPI5 Zira. Select
another installed Ollama model with --model. Select --device cpu and
--compute-type int8 for CPU transcription. SAPI5 voices are Windows voices;
--tts-engine piper or kokoro uses the corresponding local AlienVox TTS package
and its installed voice files.

INTERACTIVE CONTROLS
====================
* The bottom input line is always available for typing. Press Enter to send a
  typed message to Ollama and have the response spoken.
* After the greeting, the first microphone turn starts automatically. Pause to
  end the utterance; Whisper transcribes it, then Ollama replies and TTS speaks.
* After each spoken reply, microphone listening resumes automatically. Use
  /listen to restart if a turn times out or returns to text mode.
* Enter /help to show the controls, or /quit and /exit to close the runner.
  Saying "exit" as the complete microphone transcription also closes it.
* Type / to see slash-command completions. Use Up/Down or Tab to select one.
  Enter fills the selected suggestion; press Enter again to run that command.
* PageUp and PageDown scroll the conversation history. Ctrl+Home and Ctrl+End
  jump to its beginning and end. New messages resume following the latest turn.
* The startup greeting is shown in the history and spoken through the selected
  TTS voice; the microphone starts automatically when the greeting finishes.
  The microphone automatically resumes after each spoken reply. Type a message
  at any time to send a text turn instead.
* The status LED is green while listening, yellow while transcribing or
  thinking, red while TTS speaks, and blue while idle or in text mode.

USEFUL OPTIONS
==============
    --model gemma4:12b             Installed Ollama chat model
    --ollama-url URL               Ollama base URL (default localhost:11434)
    --stt-model large-v3-turbo     Whisper model already present in the cache
    --device cuda|cpu              Whisper device (default cuda)
    --compute-type float16         Whisper precision (CPU commonly uses int8)
    --language en|auto             Spoken language or automatic detection
    --input-device 1               Microphone index or name
    --silence-seconds 1.0           Silence that ends the microphone turn
    --max-seconds 30                Maximum microphone capture duration
    --tts-engine sapi5|piper|kokoro Speech synthesis engine (default sapi5)
    --tts-voice VOICE               Voice ID/name; default Zira/Amy/af_heart
    --tts-device cpu|gpu             AlienVox TTS device (default cpu)
    --list-models                   Show installed Ollama models and exit
    --list-audio-devices            Show microphone devices and exit
    --list-voices                   Show supported installed voices and exit
    --once                          Exit after the first completed reply
    --allow-stt-model-download      Explicitly allow downloading Whisper weights

Typed turns can be queued while an earlier typed turn is being answered; model
and speech playback are processed serially to avoid overlapping audio. Start a
microphone turn after the current response finishes. The runner does not save
recorded audio or a transcript file. With the default local Ollama endpoint,
conversation text is sent to that local service for response generation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from alien_conv import find_cached_whisper_model, list_audio_devices, record_utterance, speak_sapi


SKILL_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_ROOT.parents[2]
SYSTEM_PROMPT = (
    "You are Alien Conversation, a friendly voice assistant. Reply naturally in one or two "
    "short spoken sentences. Be useful and warm without sounding scripted. Do not use lists "
    "unless asked, and do not include stage directions or hidden reasoning."
)


def request_json(url: str, payload: dict[str, Any] | None = None, timeout: float = 180) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Local Ollama request failed at {url}: {exc}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Ollama returned an invalid JSON object")
    return result


def list_ollama_models(base_url: str) -> list[dict[str, Any]]:
    return request_json(base_url.rstrip("/") + "/api/tags", timeout=10).get("models", [])


def list_voices() -> list[dict[str, str]]:
    voices = []
    if os.name == "nt":
        try:
            import pythoncom
            import win32com.client
        except ImportError:
            pass
        else:
            pythoncom.CoInitialize()
            try:
                sapi = win32com.client.Dispatch("SAPI.SpVoice")
                tokens = sapi.GetVoices()
                voices.extend(
                    {"engine": "sapi5", "name": str(tokens.Item(i).GetDescription()), "id": str(tokens.Item(i).Id)}
                    for i in range(tokens.Count)
                )
            finally:
                pythoncom.CoUninitialize()
    try:
        from alienvox_tts import list_voices as list_alienvox_voices

        for engine in ("piper", "kokoro"):
            for voice in list_alienvox_voices(engine):
                voices.append({"engine": engine, "name": voice.name, "id": voice.id})
    except ImportError:
        pass
    return voices


def speak(text: str, engine: str, voice: str, tts_device: str) -> str:
    if engine == "sapi5":
        return speak_sapi(text, voice)
    from alienvox_tts import speak as alienvox_speak

    alienvox_speak(text, voice=voice, engine=engine, device=tts_device, wait=True)
    return f"{engine}/{voice}"


def pick_voice(args: argparse.Namespace) -> str:
    if args.tts_voice:
        return args.tts_voice
    return {
        "sapi5": "zira",
        "piper": "en_US-amy-medium",
        "kokoro": "af_heart",
    }[args.tts_engine]


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manual interactive local mic -> STT -> Ollama -> TTS conversation")
    parser.add_argument("--model", "--llm-model", dest="model", default="gemma4:12b", help="installed local Ollama model")
    parser.add_argument("--ollama-url", default="http://localhost:11434", help="local Ollama base URL")
    parser.add_argument("--stt-model", default="large-v3-turbo", help="cached faster-whisper model")
    parser.add_argument("--allow-stt-model-download", "--allow-model-download", dest="allow_model_download", action="store_true", help="explicitly permit downloading missing Whisper weights")
    parser.add_argument("--language", default="en", help="spoken language code, or auto")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cuda", help="Whisper inference device")
    parser.add_argument("--compute-type", default="float16", help="Whisper compute type, e.g. float16 or int8")
    parser.add_argument("--input-device", help="microphone device index or name")
    parser.add_argument("--max-seconds", type=float, default=30, help="maximum microphone time per turn")
    parser.add_argument("--silence-seconds", type=float, default=1.0, help="end the utterance after this much silence")
    parser.add_argument("--start-timeout", type=float, default=10, help="wait this long for speech to start")
    parser.add_argument("--vad-threshold", type=float, default=0.012, help="RMS level used for speech detection")
    parser.add_argument("--tts-engine", choices=("sapi5", "piper", "kokoro"), default="sapi5")
    parser.add_argument("--tts-voice", help="voice ID or name substring; defaults to Zira, Amy, or af_heart by engine")
    parser.add_argument("--tts-device", choices=("cpu", "gpu"), default="cpu")
    parser.add_argument("--list-models", action="store_true", help="list installed Ollama models and exit")
    parser.add_argument("--list-audio-devices", "--list-devices", action="store_true", help="list microphones and exit")
    parser.add_argument("--list-voices", action="store_true", help="list available SAPI/Piper/Kokoro voices and exit")
    parser.add_argument("--once", action="store_true", help="run one conversation turn and exit")
    return parser


async def run_chat_ui(args: argparse.Namespace, stt: Any, voice: str) -> None:
    """Run a full-screen chat view with scrollback and a fixed input line."""
    try:
        from prompt_toolkit.application import Application
        from prompt_toolkit.completion import WordCompleter
        from prompt_toolkit.formatted_text import FormattedText
        from prompt_toolkit.key_binding import KeyBindings
        from prompt_toolkit.layout import HSplit, Layout, ScrollOffsets, ScrollbarMargin, Window
        from prompt_toolkit.layout.controls import FormattedTextControl
        from prompt_toolkit.styles import Style
        from prompt_toolkit.widgets import TextArea
    except ImportError as exc:
        raise RuntimeError("Install the Alien Conversation dependencies with scripts/setup.ps1.") from exc

    messages: list[tuple[str, str]] = []
    conversation: list[dict[str, str]] = []
    pending: asyncio.Queue[str] = asyncio.Queue()
    speaker_lock = asyncio.Lock()
    capture_lock = asyncio.Lock()
    state = {"status": "Starting", "phase": "idle", "busy": False, "listening": False, "listen_active": False, "tts_active": False, "follow_tail": True, "closed": False}
    app_holder: dict[str, Application[Any]] = {}
    history_window: Window | None = None

    def formatted_history() -> FormattedText:
        fragments: list[tuple[str, str]] = []
        for role, text in messages:
            style = "class:role.user" if role == "You" else "class:role.assistant" if role == "Alien Conversation" else "class:role.system"
            fragments.extend(((style, role + "\n"), ("class:message", text + "\n\n")))
        if not fragments:
            return FormattedText([("class:placeholder", "Your conversation will appear here.\nType a message below, or enter /listen to speak.\n")])
        return FormattedText(fragments)

    def status_text() -> FormattedText:
        indicator_style, label = {
            "transcribing": ("class:led.thinking", "TRANSCRIBING"),
            "thinking": ("class:led.thinking", "THINKING"),
            "speaking": ("class:led.speaking", "SPEAKING"),
        }.get(state["phase"], ("class:led.idle", "IDLE / TEXT MODE"))
        detail = state["status"]
        if state["listening"]:
            indicator_style, label, detail = "class:led.listening", "LISTENING", "Speak now; pause to finish"
        elif state["tts_active"]:
            indicator_style, label = "class:led.speaking", "SPEAKING"
        return FormattedText([
            (indicator_style, "[●] "),
            ("class:status", f"{label}  {detail}\n"),
            ("class:hint", "Type a message | /listen  /help  /quit | PgUp/PgDn scrolls history"),
        ])

    history_window = Window(
        content=FormattedTextControl(formatted_history),
        wrap_lines=True,
        style="class:history",
        always_hide_cursor=True,
        right_margins=[ScrollbarMargin(display_arrows=True)],
        scroll_offsets=ScrollOffsets(top=1, bottom=1),
    )
    status_window = Window(content=FormattedTextControl(status_text), height=2, style="class:statusbar")

    def redraw() -> None:
        if history_window is not None and state["follow_tail"]:
            history_window.vertical_scroll = 1_000_000
        app = app_holder.get("app")
        if app is not None:
            app.invalidate()

    def add_message(role: str, text: str) -> None:
        messages.append((role, text))
        redraw()

    async def process_messages() -> None:
        while True:
            user_text = await pending.get()
            state["busy"] = True
            state["phase"] = "thinking"
            state["status"] = f"Thinking with {args.model}…"
            redraw()
            try:
                payload = {
                    "model": args.model,
                    "messages": [{"role": "system", "content": SYSTEM_PROMPT}, *conversation[-8:], {"role": "user", "content": user_text}],
                    "stream": False,
                    "think": False,
                    "keep_alive": "10m",
                    "options": {"temperature": 0.65, "num_predict": 120},
                }
                started = time.perf_counter()
                result = await asyncio.to_thread(request_json, args.ollama_url.rstrip("/") + "/api/chat", payload)
                reply = str(result.get("message", {}).get("content", "")).strip()
                if not reply:
                    raise RuntimeError(f"Ollama model {args.model!r} returned no spoken response.")
                elapsed = time.perf_counter() - started
                add_message("Alien Conversation", reply)
                conversation.extend((
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": reply},
                ))
                conversation[:] = conversation[-8:]
                state["phase"] = "thinking"
                state["status"] = "Waiting for microphone capture to finish before speaking..."
                redraw()
                async with capture_lock:
                    state["phase"] = "speaking"
                    state["status"] = f"Speaking with {args.tts_engine}/{voice}…"
                    state["tts_active"] = True
                    redraw()
                    try:
                        async with speaker_lock:
                            await asyncio.to_thread(speak, reply, args.tts_engine, voice, args.tts_device)
                    finally:
                        state["tts_active"] = False
                state["phase"] = "idle"
                state["status"] = f"Ready | {args.model} | {elapsed:.1f}s"
                if args.once:
                    state["closed"] = True
                    app_holder["app"].exit()
                    return
            except Exception as exc:
                add_message("System", f"Turn failed: {exc}")
                state["phase"] = "idle"
                state["status"] = "Ready — see the conversation history for the error"
            finally:
                state["busy"] = False
                pending.task_done()
                redraw()
                if not args.once and not state["closed"] and not state["listen_active"] and pending.empty():
                    start_listening()

    async def listen_to_microphone() -> None:
        state["listening"] = True
        state["phase"] = "listening"
        state["status"] = "Listening — speak now; pause to finish"
        redraw()

        def transcribe_audio(audio: Any) -> str:
            language = None if args.language.casefold() == "auto" else args.language
            segments, _info = stt.transcribe(audio, language=language, vad_filter=True)
            return " ".join(segment.text.strip() for segment in segments).strip()

        try:
            async with capture_lock:
                audio = await asyncio.to_thread(
                    record_utterance,
                    16_000,
                    args.max_seconds,
                    args.silence_seconds,
                    args.start_timeout,
                    args.vad_threshold,
                    args.input_device,
                )
                state["listening"] = False
                if audio is None:
                    state["phase"] = "idle"
                    state["status"] = "No speech detected — type a message or enter /listen to try again"
                    return
                state["phase"] = "transcribing"
                state["status"] = f"Transcribing with {args.stt_model}..."
                redraw()
                user_text = await asyncio.to_thread(transcribe_audio, audio)
            if not user_text:
                state["phase"] = "idle"
                state["status"] = "No speech detected — type a message or enter /listen to try again"
                return
            add_message("You", user_text)
            if re.sub(r"[^\w]+", " ", user_text, flags=re.UNICODE).strip().casefold() == "exit":
                state["phase"] = "idle"
                state["status"] = "Stopped by voice command"
                state["closed"] = True
                app_holder["app"].exit()
                return
            pending.put_nowait(user_text)
        except Exception as exc:
            add_message("System", f"Microphone turn failed: {exc}")
            state["phase"] = "idle"
            state["status"] = "Ready — see the conversation history for the error"
        finally:
            state["listening"] = False
            state["listen_active"] = False
            redraw()

    def start_listening() -> None:
        if state["closed"] or state["listen_active"]:
            return
        state["listen_active"] = True
        app_holder["app"].create_background_task(listen_to_microphone())

    def accept_input(buffer: Any) -> bool:
        completion_state = buffer.complete_state
        if completion_state is not None:
            completion = completion_state.current_completion
            if completion is None and completion_state.completions:
                completion = completion_state.completions[0]
            if completion is not None and completion.text.casefold() != buffer.text.strip().casefold():
                buffer.apply_completion(completion)
                return True

        text = buffer.text.strip()
        buffer.reset()
        if not text:
            return True
        command = text.casefold()
        if command in ("/quit", "/exit"):
            state["closed"] = True
            app_holder["app"].exit()
            return True
        if command == "/help":
            add_message("System", "Type a message and press Enter, or use /listen to talk into the microphone. Say 'exit' while listening, or use /quit to close the app.")
            return True
        if command == "/listen":
            if state["listen_active"] or state["busy"] or not pending.empty():
                state["status"] = "Wait for the current turn to finish before starting a microphone turn"
                redraw()
            else:
                start_listening()
            return True
        if text.startswith("/"):
            add_message("System", f"Unknown command: {text}. Use /help for commands.")
            return True
        add_message("You", text)
        pending.put_nowait(text)
        return True

    input_area = TextArea(
        height=1,
        prompt="> ",
        multiline=False,
        wrap_lines=False,
        accept_handler=accept_input,
        completer=WordCompleter(["/listen", "/help", "/quit", "/exit"], ignore_case=True, sentence=True),
        complete_while_typing=True,
        style="class:input",
    )
    key_bindings = KeyBindings()

    @key_bindings.add("tab")
    def cycle_completions(event: Any) -> None:
        buffer = event.current_buffer
        if buffer.complete_state:
            buffer.complete_next()
        else:
            buffer.start_completion(select_first=True)

    @key_bindings.add("pageup")
    def scroll_history_up(event: Any) -> None:
        info = history_window.render_info
        step = max(1, info.window_height - 2) if info else 10
        history_window.vertical_scroll = max(0, history_window.vertical_scroll - step)
        state["follow_tail"] = False
        event.app.invalidate()

    @key_bindings.add("pagedown")
    def scroll_history_down(event: Any) -> None:
        info = history_window.render_info
        step = max(1, info.window_height - 2) if info else 10
        history_window.vertical_scroll += step
        if info and history_window.vertical_scroll >= max(0, info.content_height - info.window_height - 1):
            state["follow_tail"] = True
        event.app.invalidate()

    @key_bindings.add("c-home")
    def scroll_history_top(event: Any) -> None:
        history_window.vertical_scroll = 0
        state["follow_tail"] = False
        event.app.invalidate()

    @key_bindings.add("c-end")
    def scroll_history_bottom(event: Any) -> None:
        state["follow_tail"] = True
        history_window.vertical_scroll = 1_000_000
        event.app.invalidate()

    root = HSplit([
        Window(FormattedTextControl([("class:title", "Alien Conversation — manual local test")]), height=1, style="class:titlebar"),
        history_window,
        Window(height=1, char="─", style="class:separator"),
        status_window,
        input_area,
    ])
    style = Style.from_dict({
        "titlebar": "bg:#1f2b3a",
        "title": "bold #9ccaff",
        "history": "bg:#101820",
        "role.user": "bold #70d8ff",
        "role.assistant": "bold #a6e3a1",
        "role.system": "bold #f9cb8c",
        "message": "#e6edf3",
        "placeholder": "#8493a3",
        "separator": "#34475b",
        "statusbar": "bg:#1f2b3a #c8d3de",
        "status": "#c8d3de",
        "hint": "#9badbf",
        "led.listening": "bold #45e078",
        "led.thinking": "bold #ffd166",
        "led.speaking": "bold #ff5b64",
        "led.idle": "bold #72b7ff",
        "input": "bg:#1a2633 #ffffff",
    })
    app = Application(
        layout=Layout(root, focused_element=input_area),
        key_bindings=key_bindings,
        style=style,
        full_screen=True,
        mouse_support=True,
        erase_when_done=False,
    )
    app_holder["app"] = app

    async def speak_greeting() -> None:
        greeting = "Hi, this is Alien Conversation. I'm up and running, and I'm listening now."
        add_message("Alien Conversation", greeting)
        state["status"] = f"Speaking startup greeting with {args.tts_engine}/{voice}…"
        state["phase"] = "speaking"
        state["tts_active"] = True
        redraw()
        try:
            async with speaker_lock:
                await asyncio.to_thread(speak, greeting, args.tts_engine, voice, args.tts_device)
            state["phase"] = "idle"
            state["status"] = f"Ready | {args.model} | type a message or /listen"
        except Exception as exc:
            add_message("System", f"Startup greeting could not be spoken: {exc}")
            state["phase"] = "idle"
            state["status"] = f"Ready | {args.model} | greeting audio failed"
        finally:
            state["tts_active"] = False
        redraw()
        if not state["closed"] and not state["busy"] and pending.empty():
            start_listening()

    app.create_background_task(process_messages())
    app.create_background_task(speak_greeting())
    await app.run_async()


def main() -> int:
    args = make_parser().parse_args()
    try:
        if args.list_models:
            for model in list_ollama_models(args.ollama_url):
                details = model.get("details", {})
                print(f"{model.get('name', '...')}  {details.get('parameter_size', '')}  {details.get('quantization_level', '')}")
            return 0
        if args.list_audio_devices:
            for device in list_audio_devices():
                print(f"{device['index']}: {device['name']} ({device['input_channels']} input channels)")
            return 0
        if args.list_voices:
            for voice in list_voices():
                print(f"{voice['engine']}: {voice['name']} [{voice['id']}]")
            return 0
        if os.name != "nt":
            raise RuntimeError("Manual local conversation currently requires Windows for microphone controls/SAPI.")
        if not 0 < args.max_seconds <= 120 or not 0 < args.silence_seconds <= 10 or args.start_timeout <= 0 or args.vad_threshold < 0:
            raise ValueError("recording duration or speech detection settings are out of range")

        app_models = REPO_ROOT / "python_app" / ".models"
        if app_models.is_dir():
            os.environ.setdefault("ALIENVOX_MODELS_DIR", str(app_models))

        installed = {model.get("name") for model in list_ollama_models(args.ollama_url)}
        if args.model not in installed:
            raise RuntimeError(f"Ollama model {args.model!r} is not installed. Use --list-models to see local tags.")

        if not args.allow_model_download:
            os.environ["HF_HUB_OFFLINE"] = "1"
        else:
            os.environ.pop("HF_HUB_OFFLINE", None)
        from faster_whisper import WhisperModel

        cached_model = find_cached_whisper_model(args.stt_model)
        if cached_model:
            model_path = str(cached_model)
            print(f"Reusing cached Whisper model: {cached_model}")
        elif args.allow_model_download:
            model_path = args.stt_model
        else:
            raise RuntimeError(
                f"Whisper model {args.stt_model!r} is not in the local cache. No download was started; "
                "use --allow-stt-model-download only if you want to download it."
            )
        cache_dir = SKILL_ROOT / ".models" / "faster-whisper"
        cache_dir.mkdir(parents=True, exist_ok=True)
        print(f"Loading Whisper {args.stt_model} ({args.device}/{args.compute_type})...")
        stt = WhisperModel(
            model_path,
            device=args.device,
            compute_type=args.compute_type,
            download_root=str(cache_dir),
            local_files_only=not args.allow_model_download,
        )
        voice = pick_voice(args)
        asyncio.run(run_chat_ui(args, stt, voice))
        return 0
    except KeyboardInterrupt:
        print("\nAlien Conversation stopped.")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
