"""Windows SAPI5 TTS engine via pywin32 COM."""
from __future__ import annotations

import sys

if sys.platform != "win32":
    raise ImportError("sapi_win is Windows-only")

import win32com.client  # type: ignore

from .base import TtsEngine, Voice, SpeakParams


class SapiEngine(TtsEngine):
    def __init__(self) -> None:
        self._sapi = win32com.client.Dispatch("SAPI.SpVoice")

    def list_voices(self) -> list[Voice]:
        tokens = self._sapi.GetVoices()
        return [
            Voice(id=str(i), name=tokens.Item(i).GetDescription())
            for i in range(tokens.Count)
        ]

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        voices = self._sapi.GetVoices()
        idx = int(voice_id) if voice_id.isdigit() else 0
        self._sapi.Voice = voices.Item(idx)
        # SAPI rate: -10..10 maps directly
        self._sapi.Rate = max(-10, min(10, params.rate))
        self._sapi.Volume = max(0, min(100, params.volume))
        self._sapi.Speak(text)

    def stop(self) -> None:
        self._sapi.Speak("", 3)  # SVSFPurgeBeforeSpeak

    def pause(self) -> None:
        self._sapi.Pause()

    def resume(self) -> None:
        self._sapi.Resume()
