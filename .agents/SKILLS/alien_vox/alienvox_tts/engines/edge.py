"""Microsoft Edge neural TTS engine (via the `edge-tts` package) — a NETWORKED engine.

Unlike Kokoro, this engine is NOT local or offline: every call sends the text
to Microsoft's online Read Aloud service and needs an internet connection. It
needs no API key, and the service is used unofficially (the same endpoint the
Edge browser uses), so it can change or rate-limit without notice. Use it for
languages Kokoro does not ship (Arabic above all) or when a more natural voice
is wanted and the text is fine to leave the machine. Never pick it for text
that must stay private; Piper is the default local engine for that reason.

Voices are Microsoft neural voices identified by their service short name,
for example "ar-SA-HamedNeural" or "en-US-AriaNeural". The service has
hundreds; `VOICES` is a curated starting roster, and any other well-formed
short name is passed through to the service (an unknown one fails there, with
the service's own error, instead of silently falling back to another voice).

The service returns 24 kHz mono MP3. `synthesize()` decodes it to the same
(float32 array, sample_rate) shape every engine returns, so WAV export and
playback work exactly as they do for Kokoro.

Install: pip install edge-tts
"""
from __future__ import annotations

import asyncio
import io
import logging
import re
import threading

import numpy as np

from ..audio import play_audio, stop_playback
from ..base import SpeakParams, TtsEngine, Voice

_log = logging.getLogger("alienvox_tts.edge")

VOICES = [
    Voice(id="ar-SA-HamedNeural",     name="Arabic (Saudi Arabia) M · Hamed"),
    Voice(id="ar-SA-ZariyahNeural",   name="Arabic (Saudi Arabia) F · Zariyah"),
    Voice(id="ar-EG-ShakirNeural",    name="Arabic (Egypt) M · Shakir"),
    Voice(id="ar-EG-SalmaNeural",     name="Arabic (Egypt) F · Salma"),
    Voice(id="ar-AE-HamdanNeural",    name="Arabic (UAE) M · Hamdan"),
    Voice(id="ar-AE-FatimaNeural",    name="Arabic (UAE) F · Fatima"),
    Voice(id="en-US-AriaNeural",      name="English (US) F · Aria"),
    Voice(id="en-US-AndrewNeural",    name="English (US) M · Andrew"),
    Voice(id="en-GB-SoniaNeural",     name="English (UK) F · Sonia"),
    Voice(id="en-GB-RyanNeural",      name="English (UK) M · Ryan"),
]

DEFAULT_VOICE = "ar-SA-HamedNeural"

# <language>-<REGION>[-<script/dialect>]-<Name>Neural, e.g. "ar-SA-HamedNeural", "zh-CN-liaoning-XiaobeiNeural".
_VOICE_ID_RE = re.compile(r"^[a-z]{2,3}-[A-Z]{2,4}(-[A-Za-z]+)?-[A-Za-z]+Neural$")


def _rate_to_percent(rate: int) -> str:
    """Convert this library's -10..+10 rate scale to the service's "+N%"/"-N%"
    string: +10 -> +100% (2x), -10 -> -50% (0.5x), the same range Kokoro maps."""
    clamped = max(-10, min(10, rate))
    pct = clamped * 10 if clamped >= 0 else clamped * 5
    return f"{pct:+d}%"


def _pitch_to_hz(pitch: int) -> str:
    """Convert -10..+10 to the service's "+NHz"/"-NHz" string (5 Hz per step)."""
    return f"{max(-10, min(10, pitch)) * 5:+d}Hz"


async def _fetch_mp3(text: str, voice_id: str, rate: str, pitch: str) -> bytes:
    import edge_tts

    out = bytearray()
    async for chunk in edge_tts.Communicate(text, voice_id, rate=rate, pitch=pitch).stream():
        if chunk["type"] == "audio":
            out += chunk["data"]
    return bytes(out)


def _run(coro):
    """Run a coroutine to completion from sync code, even when the caller is
    already inside a running event loop (asyncio.run() would raise there)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    box: dict[str, object] = {}

    def target() -> None:
        try:
            box["value"] = asyncio.run(coro)
        except BaseException as exc:  # re-raised on the calling thread below
            box["error"] = exc

    t = threading.Thread(target=target, name="edge-tts-run")
    t.start()
    t.join()
    if "error" in box:
        raise box["error"]  # type: ignore[misc]
    return box["value"]


class EdgeEngine(TtsEngine):
    """Microsoft Edge neural voices over the network. Stateless: nothing is
    loaded or cached, so a single instance is cheap and every call is an
    independent request."""

    def __init__(self, device: str = "cpu") -> None:
        # `device` exists only because get_engine() constructs every engine with
        # it; synthesis runs on Microsoft's servers, so it has no meaning here.
        self._done = threading.Event()
        self._done.set()
        self._stop_requested = threading.Event()
        _log.info("EdgeEngine created — networked: text is sent to Microsoft's online service")

    # ── TtsEngine API ─────────────────────────────────────────────────────

    def list_voices(self) -> list[Voice]:
        return list(VOICES)

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Synthesize then play on a background thread; returns immediately.
        Use wait_until_done() / speak_sync() to block until playback ends."""
        if not text:
            return
        self._done.clear()
        self._stop_requested.clear()
        threading.Thread(
            target=self._do_speak,
            args=(text, voice_id or DEFAULT_VOICE, params),
            daemon=True,
            name="edge-speak",
        ).start()

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        """Return (float32 numpy array, sample_rate) WITHOUT playing. Raises
        ValueError for a malformed voice id and propagates the service's own
        error (network down, unknown voice, rate limit) — never falls back."""
        audio = self._synthesize_array(text, voice_id or DEFAULT_VOICE, params)
        return audio

    def stop(self) -> None:
        self._stop_requested.set()
        stop_playback()
        self._done.set()

    def pause(self) -> None:
        stop_playback()  # no true pause on the playback backend; see KokoroEngine.pause()

    def resume(self) -> None:
        pass

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        return self._done.wait(timeout=timeout_ms / 1000.0)

    # ── Internal ──────────────────────────────────────────────────────────

    def _synthesize_array(self, text: str, voice_id: str, params: SpeakParams):
        if not text or not text.strip():
            return None
        if not _VOICE_ID_RE.match(voice_id):
            raise ValueError(
                f"{voice_id!r} is not a valid Edge voice short name "
                "(expected e.g. 'ar-SA-HamedNeural'); see references/voices.md."
            )
        import soundfile as sf

        mp3 = _run(_fetch_mp3(text, voice_id, _rate_to_percent(params.rate), _pitch_to_hz(params.pitch)))
        if not mp3:
            return None
        data, sample_rate = sf.read(io.BytesIO(mp3), dtype="float32", always_2d=True)
        mono = data.mean(axis=1) if data.shape[1] > 1 else data[:, 0]
        volume_scale = max(0.0, min(1.0, params.volume / 100.0))
        return (mono * volume_scale).astype(np.float32), int(sample_rate)

    def _do_speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        try:
            result = self._synthesize_array(text, voice_id, params)
            if result is None or self._stop_requested.is_set():
                return
            audio, sample_rate = result
            play_audio(audio, sample_rate)
        except Exception as exc:
            _log.error("Edge speak failed: %s", exc)
        finally:
            self._done.set()
