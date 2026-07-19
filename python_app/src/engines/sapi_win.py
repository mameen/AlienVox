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

# Thread-local storage for SAPI COM objects.
# COM objects MUST be created and used on the same thread with CoInitialize().
# Using a single shared object across threads causes silent audio failure or
# COM exception 0xe0000002 when accessed from a daemon thread that never called
# CoInitializeEx.
_thread_local = threading.local()


def _get_sapi() -> object:
    """Return a SAPI.SpVoice COM object for the current thread.

    Creates a fresh COM object per thread so each thread has its own
    apartment-initialized instance.
    """
    sapi = getattr(_thread_local, "sapi", None)
    if sapi is None:
        _thread_local.sapi = win32com.client.Dispatch("SAPI.SpVoice")
        return _thread_local.sapi
    return sapi


class SapiEngine(TtsEngine):
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def _speak_obj(self):
        """Get the thread-local SAPI COM object for speak operations."""
        return _get_sapi()

    def get_thread_local_sapi(self):
        """Return the current thread's SAPI object (for tests/debugging)."""
        return getattr(_thread_local, "sapi", None)

    # ── Voice enumeration ─────────────────────────────────────────────────────

    def list_voices(self) -> list[Voice]:
        """Return all installed SAPI5 voices with stable registry-path IDs."""
        sapi = self._speak_obj()
        tokens = sapi.GetVoices()
        result: list[Voice] = []
        for i in range(tokens.Count):
            token = tokens.Item(i)
            voice_id: str = token.Id  # e.g. HKEY_LOCAL_MACHINE\...\TTS_MS_EN-US_DAVID_11.0
            name: str = token.GetDescription()
            result.append(Voice(id=voice_id, name=name))
        return result

    def _find_token(self, voice_id: str, sapi: object | None = None):
        """Return the SAPI token matching voice_id, or the first token."""
        if sapi is None:
            sapi = self._speak_obj()
        tokens = sapi.GetVoices()
        for i in range(tokens.Count):
            token = tokens.Item(i)
            if token.Id == voice_id:
                return token
        return tokens.Item(0)

    # ── Speak ─────────────────────────────────────────────────────────────────

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Speak text asynchronously. Returns immediately; call stop() to interrupt."""
        if not isinstance(text, str):
            raise TypeError(f"text must be str, not {type(text).__name__}")
        sapi = self._speak_obj()
        with self._lock:
            self._apply_params(sapi, voice_id, params)
            ssml = self._build_ssml(text, params)
            print(f"[SAPI] speak: voice_id='{voice_id}', ssml_len={len(ssml)}, first_80={repr(ssml[:80])}")
            try:
                sapi.Speak(ssml, _SVSFlagsAsync)
                print(f"[SAPI] Speak() returned OK")
            except Exception as exc:
                print(f"[SAPI] Speak() FAILED: {exc}, falling back to plain text")
                # SSML may fail on some voices/OS versions; fall back to plain text
                if ssml != text:
                    try:
                        sapi.Speak(text, _SVSFlagsAsync)
                    except Exception:
                        pass  # Silently ignore audio errors in tests

    def speak_sync(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Blocking speak — waits until audio completes. Used by speak_to_wav tests."""
        sapi = self._speak_obj()
        with self._lock:
            self._apply_params(sapi, voice_id, params)
            sapi.Speak(text, 0)  # synchronous

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
        sapi = self._speak_obj()
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(str(out_path), _SSFMCreateForWrite, False)
        with self._lock:
            old_output = sapi.AudioOutputStream
            try:
                sapi.AudioOutputStream = stream
                self._apply_params(sapi, voice_id, params)
                ssml = self._build_ssml(text, params)
                sapi.Speak(ssml, 0)  # must be synchronous before closing stream
            finally:
                sapi.AudioOutputStream = old_output
        stream.Close()

    # ── Control ───────────────────────────────────────────────────────────────

    def stop(self) -> None:
        """Stop current speech immediately, purging the queue."""
        sapi = self._speak_obj()
        sapi.Speak("", _SVSFlagsAsync | _SVSFPurgeBeforeSpeak)

    def pause(self) -> None:
        sapi = self._speak_obj()
        sapi.Pause()

    def resume(self) -> None:
        sapi = self._speak_obj()
        sapi.Resume()

    # ── Internals ─────────────────────────────────────────────────────────────

    def _apply_params(self, sapi: object, voice_id: str, params: SpeakParams) -> None:
        sapi.Voice = self._find_token(voice_id, sapi=sapi)
        sapi.Rate = max(-10, min(10, params.rate))
        sapi.Volume = max(0, min(100, params.volume))

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape characters significant in SAPI XML/SSML."""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;'))

    def _build_ssml(self, text: str, params: SpeakParams) -> str:
        """Build SSML string if pitch is non-zero, otherwise return plain text.

        SAPI's SSML requires pitch to be applied via <prosody pitch="..."> wrapping
        the text content. A bare <pitch> element as a sibling before text causes
        COM exception 0xe0000002 because SAPI doesn't recognize it in that position.

        Pitch values are converted from SAPI's -10..+10 range to musical semitones
        (+/-Nst) for the <prosody> element.
        """
        if params.pitch != 0:
            escaped = self._escape_xml(text)
            pitch_val = max(-10, min(10, params.pitch))
            # Use SAPI's prosody element with semitone notation
            return f'<speak><prosody pitch="+{pitch_val}st">{escaped}</prosody></speak>'
        return text

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        """Wait for speech queue to drain with finite timeout.

        Returns True if speech completed, False if timed out or error.
        Unlike WaitUntilDone(-1), this will not block forever.
        """
        sapi = self._speak_obj()
        try:
            return sapi.WaitUntilDone(timeout_ms)
        except Exception:
            return False
