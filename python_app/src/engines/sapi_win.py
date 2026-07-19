"""Windows SAPI5 TTS engine via pywin32 COM.

Voice IDs are the SAPI token registry paths, e.g.:
  HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech\\Voices\\Tokens\\TTS_MS_EN-US_DAVID_11.0

These are stable across installs; index-based IDs change when voices are added.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

if sys.platform != "win32":
    raise ImportError("sapi_win is Windows-only")

import win32com.client  # type: ignore

from .base import TtsEngine, Voice, SpeakParams

# SAPI SpeakFlags constants
_SVSFlagsAsync       = 1   # non-blocking speak
_SVSFPurgeBeforeSpeak = 2  # stop current speech before starting

# SpFileStream open mode
_SSFMCreateForWrite = 3


class SapiEngine(TtsEngine):
    def __init__(self) -> None:
        self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
        self._lock = threading.Lock()

    # ── Voice enumeration ─────────────────────────────────────────────────────

    def list_voices(self) -> list[Voice]:
        """Return all installed SAPI5 voices with stable registry-path IDs."""
        tokens = self._sapi.GetVoices()
        result: list[Voice] = []
        for i in range(tokens.Count):
            token = tokens.Item(i)
            voice_id: str = token.Id  # e.g. HKEY_LOCAL_MACHINE\...\TTS_MS_EN-US_DAVID_11.0
            name: str = token.GetDescription()
            result.append(Voice(id=voice_id, name=name))
        return result

    def _find_token(self, voice_id: str):
        """Return the SAPI token matching voice_id, or the first token."""
        tokens = self._sapi.GetVoices()
        for i in range(tokens.Count):
            token = tokens.Item(i)
            if token.Id == voice_id:
                return token
        return tokens.Item(0)

    # ── Speak ─────────────────────────────────────────────────────────────────

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Speak text asynchronously. Returns immediately; call stop() to interrupt."""
        with self._lock:
            self._apply_params(voice_id, params)
            ssml = self._build_ssml(text, params)
            self._sapi.Speak(ssml, _SVSFlagsAsync)

    def speak_sync(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Blocking speak — waits until audio completes. Used by speak_to_wav tests."""
        with self._lock:
            self._apply_params(voice_id, params)
            self._sapi.Speak(text, 0)  # synchronous

    def speak_to_wav(
        self,
        text: str,
        voice_id: str,
        params: SpeakParams,
        out_path: Path,
    ) -> None:
        """Render speech to a WAV file — no audio hardware required.

        Useful for offline tests and preview export.
        """
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(str(out_path), _SSFMCreateForWrite, False)
        with self._lock:
            old_output = self._sapi.AudioOutputStream
            try:
                self._sapi.AudioOutputStream = stream
                self._apply_params(voice_id, params)
                ssml = self._build_ssml(text, params)
                self._sapi.Speak(ssml, 0)  # must be synchronous before closing stream
            finally:
                self._sapi.AudioOutputStream = old_output
        stream.Close()

    # ── Control ───────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Stop current speech immediately, purging the queue."""
        self._sapi.Speak("", _SVSFlagsAsync | _SVSFPurgeBeforeSpeak)

    def pause(self) -> None:
        self._sapi.Pause()

    def resume(self) -> None:
        self._sapi.Resume()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _apply_params(self, voice_id: str, params: SpeakParams) -> None:
        self._sapi.Voice = self._find_token(voice_id)
        self._sapi.Rate = max(-10, min(10, params.rate))
        self._sapi.Volume = max(0, min(100, params.volume))

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape characters significant in SAPI XML/SSML."""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;'))

    def _build_ssml(self, text: str, params: SpeakParams) -> str:
        """Build SSML string if pitch is non-zero, otherwise return plain text."""
        if params.pitch != 0:
            escaped = self._escape_xml(text)
            pitch_val = max(-10, min(10, params.pitch))
            return f'<pitch absmiddle="{pitch_val}"/>{escaped}'
        return text

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        """Wait for speech queue to drain with finite timeout.

        Returns True if speech completed, False if timed out or error.
        Unlike WaitUntilDone(-1), this will not block forever.
        """
        try:
            return self._sapi.WaitUntilDone(timeout_ms)
        except Exception:
            return False
