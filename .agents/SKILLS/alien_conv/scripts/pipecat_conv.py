"""Local Pipecat conversational voice pipeline (all model inference local)."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from typing import AsyncGenerator

import numpy as np
from pipecat.frames.frames import EndFrame, ErrorFrame, Frame, TranscriptionFrame, TTSAudioRawFrame
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.ollama.llm import OLLamaLLMService
from pipecat.services.piper.tts import PiperTTSService
from pipecat.services.tts_service import TTSService
from pipecat.services.whisper.stt import WhisperSTTService
from pipecat.transports.local.audio import LocalAudioTransport, LocalAudioTransportParams
from pipecat.pipeline.worker import PipelineWorker
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.workers.runner import WorkerRunner


SKILL_ROOT = Path(__file__).resolve().parents[1]


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


class AlienVoxSapiTTSService(TTSService):
    """Run the skill's copied Windows SAPI adapter inside the Pipecat pipeline."""

    def __init__(self, engine, voice_id: str):
        super().__init__(push_start_frame=True, push_stop_frames=True)
        self._engine = engine
        self._voice_id = voice_id

    async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
        try:
            from alienvox_tts.base import SpeakParams

            await self.start_tts_usage_metrics(text)
            audio, sample_rate = await asyncio.to_thread(
                self._engine.synthesize,
                text,
                self._voice_id,
                SpeakParams(),
            )
            await self.stop_ttfb_metrics()
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            pcm16 = np.clip(audio, -1.0, 1.0)
            pcm16 = (pcm16 * 32767).astype(np.int16)
            chunk_samples = max(1, int(sample_rate * 0.08))
            for start in range(0, len(pcm16), chunk_samples):
                yield TTSAudioRawFrame(
                    pcm16[start:start + chunk_samples].tobytes(),
                    sample_rate,
                    1,
                    context_id=context_id,
                )
        except Exception as exc:
            yield ErrorFrame(error=f"AlienVox SAPI synthesis failed: {exc}")
        finally:
            await self.stop_ttfb_metrics()


class VoiceExitProcessor(FrameProcessor):
    """End the pipeline when the final transcript is exactly the word 'exit'."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if direction == FrameDirection.DOWNSTREAM and isinstance(frame, TranscriptionFrame):
            transcript = re.sub(r"[^\w]+", " ", frame.text, flags=re.UNICODE).strip().casefold()
            if transcript == "exit":
                print("\nVoice command received: exit. Stopping.", flush=True)
                await self.push_frame(EndFrame(reason="spoken exit command"), direction)
                return
        await self.push_frame(frame, direction)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Local microphone to Whisper to Ollama to speech")
    parser.add_argument(
        "--llm-model",
        "--model",
        dest="llm_model",
        default="qwen3.6:35b",
        help="Installed local Ollama model tag (default: qwen3.6:35b)",
    )
    parser.add_argument(
        "--tts-engine",
        choices=("piper", "sapi5"),
        default="sapi5",
        help="TTS engine (default: sapi5)",
    )
    parser.add_argument(
        "--tts-voice",
        help="Voice ID; defaults to the Pipecat Piper voice or the first installed SAPI5 voice",
    )
    parser.add_argument("--allow-model-download", action="store_true", help="explicitly allow downloading Whisper weights when no local copy is found")
    parser.add_argument("--list-devices", action="store_true")
    args = parser.parse_args()

    import pyaudio

    if args.list_devices:
        pa = pyaudio.PyAudio()
        try:
            for index in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(index)
                print(f"{index}: {info['name']} (in={int(info['maxInputChannels'])}, out={int(info['maxOutputChannels'])})")
        finally:
            pa.terminate()
        return

    # Keep all third-party model caches inside this skill.
    cache = SKILL_ROOT / ".models" / "pipecat"
    cache.mkdir(parents=True, exist_ok=True)
    shared_hf_home = Path.home() / ".cache" / "huggingface"
    os.environ.setdefault("HF_HOME", str(shared_hf_home if shared_hf_home.is_dir() else SKILL_ROOT / ".models" / "huggingface"))
    os.environ.setdefault("TORCH_HOME", str(SKILL_ROOT / ".models" / "torch"))
    whisper_model = find_cached_whisper_model("large-v3-turbo")
    if whisper_model is None and not args.allow_model_download:
        raise SystemExit("Whisper large-v3-turbo is not in the local cache. No download was started; pass --allow-model-download only if you want to download it.")
    if not args.allow_model_download:
        os.environ["HF_HUB_OFFLINE"] = "1"

    transport = LocalAudioTransport(LocalAudioTransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
    ))
    stt = WhisperSTTService(
        settings=WhisperSTTService.Settings(model=str(whisper_model) if whisper_model else "large-v3-turbo"),
        device="cuda",
        compute_type="float16",
    )

    if args.tts_engine == "piper":
        tts_voice = args.tts_voice or "en_US-amy-medium"
        tts = PiperTTSService(
            download_dir=cache / "piper",
            settings=PiperTTSService.Settings(voice=tts_voice),
        )
        tts_description = f"Piper voice {tts_voice}"
    else:
        sys.path.insert(0, str(SKILL_ROOT))
        from alienvox_tts.engines.sapi import SapiEngine

        sapi_engine = SapiEngine("sapi5")
        voices = sapi_engine.list_voices()
        if not voices:
            raise SystemExit("No Windows SAPI5 voices are installed.")
        if args.tts_voice:
            match = next((
                voice for voice in voices
                if voice.id == args.tts_voice or voice.id.endswith("\\" + args.tts_voice)
            ), None)
            if match is None:
                available = ", ".join(voice.id for voice in voices)
                raise SystemExit(f"SAPI5 voice {args.tts_voice!r} is not installed. Available: {available}")
            tts_voice = match.id
        else:
            tts_voice = voices[0].id
        tts = AlienVoxSapiTTSService(sapi_engine, tts_voice)
        tts_description = f"Windows SAPI5 voice {tts_voice}"

    llm = OLLamaLLMService(
        base_url="http://localhost:11434/v1",
        settings=OLLamaLLMService.Settings(
            model=args.llm_model,
            system_instruction=(
                "You are the voice assistant in Alien Conversation. "
                "Your configured stack is: Pipecat for the conversation pipeline; "
                "faster-whisper large-v3-turbo on CUDA for speech recognition; "
                f"Ollama model '{args.llm_model}' at localhost for language generation; "
                f"and {tts_description} for speech output. The model inference and "
                "audio processing run locally after model files are installed. "
                "If asked which models or voice you use, state these configured names "
                "and explain that SAPI5 is a Windows system voice, not a learned voice model. "
                "You cannot inspect the live computer, other installed models, device "
                "state, or whether a particular reply finished playing; do not claim "
                "access to those facts. Be warm and natural, use spoken language, and "
                "keep ordinary replies to one or two concise sentences."
            ),
        ),
    )
    context = LLMContext()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )
    pipeline = Pipeline([
        transport.input(),
        stt,
        VoiceExitProcessor(),
        user_aggregator,
        llm,
        tts,
        transport.output(),
        assistant_aggregator,
    ])
    worker = PipelineWorker(pipeline, idle_timeout_secs=None)
    runner = WorkerRunner(handle_sigint=True)

    print(f"Alien Conversation (Pipecat) | LLM={args.llm_model} | Whisper large-v3-turbo CUDA | TTS={tts_description}")
    print("Speak naturally; say 'exit' by itself to stop, or press Ctrl+C.")
    await runner.add_workers(worker)
    await runner.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass


