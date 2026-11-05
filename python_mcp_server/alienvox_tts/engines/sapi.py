"""Windows SAPI5 and Microsoft Speech Platform adapters for local speech."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from ..base import SpeakParams, TtsEngine, Voice


class SapiEngine(TtsEngine):
    def __init__(self, platform: str = "sapi5") -> None:
        if sys.platform != "win32":
            raise OSError("Windows SAPI voices are only available on Windows")
        self.platform = platform
        self.categories = {
            "sapi5": [r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices", r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices"],
            "speech_platform": [r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech Server\v11.0\Voices"],
        }[platform]

    def _tokens(self):
        import win32com.client
        tokens = []
        for category_id in self.categories:
            try:
                category = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
                category.SetId(category_id, False)
                collection = category.EnumerateTokens()
                tokens.extend(collection.Item(i) for i in range(collection.Count))
            except Exception:
                continue
        return tokens

    def list_voices(self) -> list[Voice]:
        result = []
        for token in self._tokens():
            result.append(Voice(token.Id, token.GetDescription()))
        return result

    def synthesize(self, text: str, voice_id: str, params: SpeakParams):
        if not text.strip():
            return None
        import pythoncom
        import win32com.client
        import soundfile as sf
        pythoncom.CoInitialize()
        try:
            tokens = self._tokens()
            match = next((t for t in tokens if t.Id == voice_id), None)
            if match is None:
                match = next((t for t in tokens if voice_id.casefold() in (t.Id + " " + t.GetDescription()).casefold()), None)
            if match is None:
                raise ValueError(f"SAPI voice {voice_id!r} is not installed; call list_voices(engine='{self.platform}')")
            sapi = win32com.client.Dispatch("SAPI.SpVoice")
            sapi.Voice = match
            sapi.Rate = max(-10, min(10, params.rate))
            sapi.Volume = max(0, min(100, params.volume))
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            with tempfile.TemporaryDirectory(prefix="alienvox-sapi-") as tmp:
                out = Path(tmp) / "speech.wav"
                stream.Open(str(out), 3, False)
                sapi.AudioOutputStream = stream
                sapi.Speak(text)
                stream.Close()
                audio, sample_rate = sf.read(out, dtype="float32", always_2d=False)
            return audio, int(sample_rate)
        finally:
            pythoncom.CoUninitialize()

    def speak(self, text: str, voice_id: str, params: SpeakParams) -> None:
        raise RuntimeError("SAPI MCP playback uses captured audio from synthesize()")

    def stop(self) -> None:
        pass
