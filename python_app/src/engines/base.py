"""Abstract TTS engine protocol — every engine implements this."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Voice:
    id: str
    name: str


@dataclass
class SpeakParams:
    rate: int = 0       # -10..10
    pitch: int = 0      # -10..10  (ignored by engines that lack pitch control)
    volume: int = 100   # 0..100


class TtsEngine(ABC):
    @abstractmethod
    def list_voices(self) -> list[Voice]: ...

    @abstractmethod
    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    def pause(self) -> None:
        pass  # optional — not all engines support it

    def resume(self) -> None:
        pass

    def wait_until_done(self, timeout_ms: int = 30_000) -> bool:
        """Wait for speech to complete. Override in engines that support it."""
        return True

    def synthesize(
        self, text: str, voice_id: str, params: "SpeakParams"
    ) -> "tuple[object, int] | None":
        """Return (float32 numpy array, sample_rate) without playing audio.

        ML engines override this to expose raw audio for WAV/MP3 export.
        Engines that can't capture audio (e.g. SAPI) return None — the caller
        must use a file-stream path (speak_to_wav) in that case.
        """
        return None

    def speak_sync(self, text: str, voice_id: str, params: SpeakParams) -> None:
        """Blocking speak. Default: speak() + wait_until_done()."""
        self.speak(text, voice_id, params)
        self.wait_until_done()
