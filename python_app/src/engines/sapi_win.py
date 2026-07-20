"""Windows SAPI5 TTS engine via pywin32 COM.

Architecture mirrors the Rust implementation (audio_win.rs):
- A single dedicated STA thread owns the ISpVoice COM object for its lifetime.
- All SAPI calls are dispatched through a queue.Queue, so any Python thread
  can safely call speak/stop/pause without COM apartment violations.
- Completion is tracked via SpeakCompleteEvent (Win32 HANDLE) waited on a
  separate lightweight thread, matching Rust's WaitForSingleObject pattern.

Voice IDs are the stable SAPI token registry paths, e.g.:
  HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Speech_OneCore\\Voices\\Tokens\\MSTTS_V110_enUS_MarkM
"""
from __future__ import annotations

import queue
import sys
import threading
from pathlib import Path
from typing import Callable

if sys.platform != "win32":
    raise ImportError("sapi_win is Windows-only")

import pythoncom  # type: ignore
import win32com.client  # type: ignore
import win32event  # type: ignore

from .. import logger as _logger_mod
from .base import SpeakParams, TtsEngine, Voice

_log = _logger_mod.get_logger("sapi")

# SAPI SpeakFlags
_SPF_ASYNC            = 1
_SPF_PURGEBEFORESPEAK = 2
_SPF_IS_XML           = 8   # tell SAPI to parse the string as SAPI XML

# SpFileStream open mode
_SSFMCreateForWrite = 3

# Registry category sets per stack — mirrors Rust audio_win.rs enumerate_engine().
_CATEGORIES_SAPI5 = [
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices",
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices",
]
_CATEGORIES_SPEECH_PLATFORM = [
    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech Server\v11.0\Voices",
]

# Default (used when constructing without an explicit stack)
_VOICE_CATEGORIES = _CATEGORIES_SAPI5

# Sentinel to shut down the worker thread cleanly.
_STOP_WORKER = object()


class _SapiWorker:
    """Dedicated STA thread that owns a single ISpVoice COM object.

    Mirrors Rust's NativeAudioEngine: commands arrive via queue.Queue;
    all COM calls happen exclusively on the worker thread.
    """

    def __init__(self, categories: list[str] | None = None) -> None:
        self._categories = categories or _VOICE_CATEGORIES
        self._q: queue.Queue = queue.Queue()
        self._sapi = None          # set by worker thread only
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="alienvox-sapi"
        )
        self._thread.start()
        self._ready.wait(timeout=5)  # wait for COM init

    # ── Public command API (any thread) ───────────────────────────────────────

    def speak(
        self,
        text: str,
        voice_id: str,
        params: SpeakParams,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        self._q.put(("speak", text, voice_id, params, on_complete))

    def stop(self) -> None:
        self._q.put(("stop",))

    def pause(self) -> None:
        self._q.put(("pause",))

    def resume(self) -> None:
        self._q.put(("resume",))

    def speak_to_wav(
        self,
        text: str,
        voice_id: str,
        params: SpeakParams,
        out_path: Path,
        done: threading.Event,
    ) -> None:
        """Queue a synchronous WAV render; caller waits on `done`."""
        self._q.put(("speak_to_wav", text, voice_id, params, out_path, done))

    def list_voices(self) -> list[Voice]:
        """Synchronous round-trip: enumerate voices on the STA thread."""
        reply: queue.Queue = queue.Queue()
        self._q.put(("list_voices", reply))
        return reply.get()

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        """Block the calling thread until speech is complete or timeout."""
        reply: queue.Queue = queue.Queue()
        self._q.put(("wait_until_done", timeout_ms, reply))
        return reply.get()

    def shutdown(self) -> None:
        self._q.put(_STOP_WORKER)

    # ── Worker thread ─────────────────────────────────────────────────────────

    def _run(self) -> None:
        pythoncom.CoInitialize()  # STA — required for ISpVoice
        try:
            self._sapi = win32com.client.Dispatch("SAPI.SpVoice")
            _log.info("STA worker started — ISpVoice ready")
            self._ready.set()

            while True:
                cmd = self._q.get()
                if cmd is _STOP_WORKER:
                    break

                op = cmd[0]

                if op == "speak":
                    _, text, voice_id, params, on_complete = cmd
                    self._do_speak(text, voice_id, params, on_complete)

                elif op == "stop":
                    self._sapi.Speak("", _SPF_ASYNC | _SPF_PURGEBEFORESPEAK)

                elif op == "pause":
                    self._sapi.Pause()

                elif op == "resume":
                    self._sapi.Resume()

                elif op == "speak_to_wav":
                    _, text, voice_id, params, out_path, done = cmd
                    self._do_speak_to_wav(text, voice_id, params, out_path)
                    done.set()

                elif op == "list_voices":
                    _, reply = cmd
                    reply.put(self._enum_all_voices())

                elif op == "wait_until_done":
                    _, timeout_ms, reply = cmd
                    try:
                        result = self._sapi.WaitUntilDone(timeout_ms)
                    except Exception:
                        result = False
                    reply.put(result)

        finally:
            self._sapi = None
            pythoncom.CoUninitialize()

    def _do_speak(
        self,
        text: str,
        voice_id: str,
        params: SpeakParams,
        on_complete: Callable[[], None] | None,
    ) -> None:
        self._apply_params(voice_id, params)
        xml = _build_sapi_xml(text, params)
        flags = _SPF_ASYNC | _SPF_PURGEBEFORESPEAK | _SPF_IS_XML
        try:
            self._sapi.Speak(xml, flags)
            _log.trace("Speak() submitted — xml_len=%d", len(xml))
        except Exception as exc:
            _log.warn("Speak() failed: %s — retrying as plain text", exc)
            try:
                self._sapi.Speak(text, _SPF_ASYNC | _SPF_PURGEBEFORESPEAK)
            except Exception as exc2:
                _log.error("Speak() plain-text fallback also failed: %s", exc2)
                return

        if on_complete is not None:
            # Get the completion event handle and wait on a throw-away thread,
            # exactly as Rust does with SpeakCompleteEvent + WaitForSingleObject.
            # The STA worker thread must NOT block so it can keep processing commands.
            try:
                handle = self._sapi.SpeakCompleteEvent()
                threading.Thread(
                    target=_wait_complete_event,
                    args=(handle, on_complete),
                    daemon=True,
                    name="sapi-complete",
                ).start()
                _log.trace("SpeakCompleteEvent watcher spawned")
            except Exception as exc:
                _log.warn("SpeakCompleteEvent unavailable: %s", exc)

    def _do_speak_to_wav(
        self,
        text: str,
        voice_id: str,
        params: SpeakParams,
        out_path: Path,
    ) -> None:
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        stream.Open(str(out_path), _SSFMCreateForWrite, False)
        old = self._sapi.AudioOutputStream
        try:
            self._sapi.AudioOutputStream = stream
            self._apply_params(voice_id, params)
            xml = _build_sapi_xml(text, params)
            self._sapi.Speak(xml, _SPF_IS_XML)  # synchronous (no _SPF_ASYNC)
        finally:
            self._sapi.AudioOutputStream = old
        stream.Close()

    def _apply_params(self, voice_id: str, params: SpeakParams) -> None:
        token = self._find_token(voice_id)
        if token is not None:
            self._sapi.Voice = token
            _log.trace("voice set: %s", voice_id.split("\\")[-1])
        else:
            _log.warn("voice not found: %s — using default", voice_id)
        self._sapi.Rate   = max(-10, min(10, params.rate))
        self._sapi.Volume = max(0,   min(100, params.volume))

    def _find_token(self, voice_id: str):
        """Search both hives for the token matching voice_id."""
        for cat_id in self._categories:
            try:
                cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
                cat.SetId(cat_id, False)
                tokens = cat.EnumerateTokens()
                for i in range(tokens.Count):
                    t = tokens.Item(i)
                    if t.Id == voice_id:
                        return t
            except Exception:
                continue
        # Fallback: first voice in any hive
        for cat_id in self._categories:
            try:
                cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
                cat.SetId(cat_id, False)
                tokens = cat.EnumerateTokens()
                if tokens.Count > 0:
                    return tokens.Item(0)
            except Exception:
                continue
        return None

    def _enum_all_voices(self) -> list[Voice]:
        seen: set[str] = set()
        result: list[Voice] = []
        for cat_id in self._categories:
            try:
                cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
                cat.SetId(cat_id, False)
                tokens = cat.EnumerateTokens()
                for i in range(tokens.Count):
                    t = tokens.Item(i)
                    if t.Id not in seen:
                        seen.add(t.Id)
                        result.append(Voice(id=t.Id, name=t.GetDescription()))
            except Exception:
                continue
        return result


def _wait_complete_event(handle: int, callback: Callable[[], None]) -> None:
    """Wait on the Win32 SpeakCompleteEvent handle then invoke callback."""
    try:
        win32event.WaitForSingleObject(handle, win32event.INFINITE)
    except Exception:
        pass
    try:
        callback()
    except Exception:
        pass


# ── SAPI XML helpers ──────────────────────────────────────────────────────────

def _escape_xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_sapi_xml(text: str, params: SpeakParams) -> str:
    """Build SAPI native XML — matches Rust's format exactly.

    Rust: `<pitch absmiddle="N"/>escaped_text`  (with SPF_IS_XML flag)
    No W3C SSML <prosody> — SAPI5 native XML only.
    """
    escaped = _escape_xml(text)
    if params.pitch != 0:
        pitch_val = max(-10, min(10, params.pitch))
        return f'<pitch absmiddle="{pitch_val}"/>{escaped}'
    return escaped


# ── Public engine ─────────────────────────────────────────────────────────────

class SapiEngine(TtsEngine):
    """SAPI5 + OneCore TTS engine backed by a single dedicated STA worker thread."""

    def __init__(self, categories: list[str] | None = None) -> None:
        self._worker = _SapiWorker(categories=categories)
        self._done_event = threading.Event()

    def list_voices(self) -> list[Voice]:
        return self._worker.list_voices()

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        if not isinstance(text, str):
            raise TypeError(f"text must be str, not {type(text).__name__}")
        if not text:
            return
        self._done_event.clear()
        self._worker.speak(text, voice_id, params, on_complete=self._on_done)

    def speak_sync(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Blocking speak — waits until audio completes (used by tests)."""
        if not text:
            return
        done = threading.Event()
        self._worker.speak(text, voice_id, params, on_complete=done.set)
        done.wait(timeout=60)

    def speak_to_wav(
        self, text: str, voice_id: str, params: SpeakParams, out_path: Path
    ) -> None:
        done = threading.Event()
        self._worker.speak_to_wav(text, voice_id, params, out_path, done)
        done.wait(timeout=60)

    def stop(self) -> None:
        self._worker.stop()

    def pause(self) -> None:
        self._worker.pause()

    def resume(self) -> None:
        self._worker.resume()

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        """Block until speech completes or timeout (ms). Returns True on completion."""
        return self._done_event.wait(timeout=timeout_ms / 1000.0)

    def _on_done(self) -> None:
        self._done_event.set()

    # ── Test / debug helpers ──────────────────────────────────────────────────

    def get_thread_local_sapi(self):
        """Return the worker's SAPI object (tests use this for low-level checks)."""
        return self._worker._sapi

    def _find_token(self, voice_id: str, sapi: object | None = None):
        """Synchronous token lookup — used by tests."""
        return self._worker._find_token(voice_id)

    @staticmethod
    def _escape_xml(text: str) -> str:
        return _escape_xml(text)

    @staticmethod
    def _build_ssml(text: str, params: SpeakParams) -> str:
        return _build_sapi_xml(text, params)


class SpeechPlatformEngine(SapiEngine):
    """SapiEngine restricted to the Microsoft Speech Server v11 hive."""
    def __init__(self) -> None:
        super().__init__(categories=_CATEGORIES_SPEECH_PLATFORM)
