"""Performance testing harness for AlienVox.

Mandatory welcome-phrase benchmark + unit-level instrumentation benchmarks.

Usage:
    python run.py perf          # runs all perf tests via pytest
    python run.py perf --real   # runs real-speech benchmark (requires audio)

Metrics collected per stack/model/voice:
    1. synthesis_ms      — wall-clock time for full synthesis (ML: synthesize(); SAPI: speak()+done)
    2. first_chunk_ms    — same as synthesis_ms for blocking engines; -1 for streaming
    3. audio_duration_s  — length of generated audio in seconds (ML only)
    4. audio_bytes       — raw PCM size in bytes as int16 (ML only)
    5. audio_sample_rate — engine output sample rate (ML only)
    6. memory_mb         — RSS delta before/after synthesis
    7. cpu_percent       — peak CPU during synthesis
    8. gpu_mb            — GPU memory used, whole-device snapshot (requires pynvml)
    9. gpu_percent       — GPU compute utilization, whole-device snapshot (requires pynvml)
    10. device           — "cuda" or "cpu", whatever select_device() picked for this run
                            (respects run.py's --cpu/--gpu, i.e. CUDA_VISIBLE_DEVICES)

Each voice is tested with its primary locale's phrase from
tests/fixtures/performance_phrases.json. Reports keep both voice_locale and
phrase_locale so fallback/mismatch is visible instead of silently benchmarking
an Arabic or Japanese voice with English text.

Reports written to .logs/YYYYMMDDHHmmss.{json,html}
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# ── Thresholds ────────────────────────────────────────────────────────────────

THRESHOLDS = {
    "latency_ms":   {"warn": 2000, "error": 5000},
    "memory_mb":    {"warn": 500,  "error": 1000},
    "cpu_percent":  {"warn": 80,   "error": 95},
    "completion_ms":{"warn": 3000, "error": 8000},
}

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
LOGS_DIR = ROOT / ".logs"
PERF_PHRASE_FILE = FIXTURES / "performance_phrases.json"
with PERF_PHRASE_FILE.open(encoding="utf-8") as _phrase_file:
    PERF_PHRASE_CATALOG = json.load(_phrase_file)
_LOCALES_BY_ID = {row["locale_id"].lower(): row for row in PERF_PHRASE_CATALOG["locales"]}
_SAMPLES_BY_LOCALE = {row["locale_id"].lower(): row for row in PERF_PHRASE_CATALOG["samples"]}
WELCOME_PHRASE = _SAMPLES_BY_LOCALE["en"]["text"]


def _voice_locale(stack_id: str, model_id: str | None, voice_id: str) -> str:
    """Return the voice's primary locale, falling back conservatively to English."""
    leaf_id = voice_id.split("\\")[-1]
    if model_id == "pockettts":
        from src.engines.pockettts_engine import _VOICE_LANGUAGES
        locale_by_language = {
            "english": "en", "italian": "it-IT", "spanish": "es-ES",
            "german": "de-DE", "portuguese": "pt-BR", "dutch": "nl-NL",
            "french": "fr-FR",
        }
        return locale_by_language.get(_VOICE_LANGUAGES.get(leaf_id.lower(), ""), "und")
    match = re.search(r"(?:^|[_-])([a-z]{2})[-_]?([A-Z]{2})(?:[_\-.]|$)", leaf_id, re.IGNORECASE)
    if match:
        return f"{match.group(1).lower()}-{match.group(2).upper()}"

    if model_id == "kokoro" and leaf_id:
        return {"a": "en-US", "b": "en-GB", "e": "es-ES", "f": "fr-FR",
                "h": "hi-IN", "i": "it-IT", "j": "ja-JP", "p": "pt-BR",
                "z": "zh-CN"}.get(leaf_id[0].lower(), "und")
    if model_id == "qwen3tts":
        return {"vivian": "zh-CN", "serena": "zh-CN", "dylan": "en", "eric": "en",
                "ryan": "en", "aiden": "en", "uncle_fu": "zh-CN", "ono_anna": "ja-JP",
                "sohee": "ko-KR"}.get(leaf_id.lower(), "und")
    if model_id == "moss_tts_nano":
        return {"junhao": "zh-CN", "zhiming": "zh-CN", "weiguo": "zh-CN",
                "xiaoyu": "zh-CN", "yuewen": "zh-CN", "lingyu": "zh-CN",
                "trump": "en", "ava": "en", "bella": "en", "adam": "en",
                "nathan": "en", "soyo": "ja-JP", "saki": "ja-JP", "mortis": "ja-JP",
                "umiri": "ja-JP", "mei": "ja-JP", "anon": "ja-JP", "arisa": "ja-JP"}.get(leaf_id.lower(), "und")
    if model_id in {"chatterbox", "dia", "f5tts", "outetts", "vibevoice_realtime", "supertonic3"}:
        return "en"
    return "und"


def _voice_profile(stack_id: str, model_id: str | None, voice_id: str) -> str:
    """Return a catalog-supported voice profile; never infer from a person's name."""
    voice = voice_id.rsplit("\\", 1)[-1].lower()
    model = (model_id or "").lower()

    if model == "kokoro":
        prefix = voice.split("_", 1)[0]
        if prefix.endswith("f"):
            return "Female"
        if prefix.endswith("m"):
            return "Male"
    if model == "supertonic3":
        if voice.startswith("f"):
            return "Female"
        if voice.startswith("m"):
            return "Male"
    if model == "qwen3tts":
        if voice in {"vivian", "serena", "ono_anna", "sohee"}:
            return "Female"
        if voice in {"dylan", "eric", "ryan", "aiden", "uncle_fu"}:
            return "Male"
    if model == "vibevoice_realtime":
        if voice in {"emma", "grace"}:
            return "Female"
        if voice in {"carter", "davis", "frank", "mike"}:
            return "Male"

    tokens = set(re.findall(r"[a-z]+", voice))
    if tokens & {"child", "kid", "juvenile"}:
        return "Child"
    if tokens & {"neutral", "androgynous"}:
        return "Neutral"
    if tokens & {"female", "woman", "feminine"}:
        return "Female"
    if tokens & {"male", "man", "masculine"}:
        return "Male"
    return "Unknown"


def _result_row(result: PerfResult) -> dict[str, Any]:
    """Serialize a benchmark row with report-only voice metadata."""
    row = asdict(result)
    row["voice_profile"] = _voice_profile(result.stack_id, result.model_id, result.voice_id)
    return row


def _phrase_for_locale(locale: str) -> dict[str, Any]:
    """Find an exact locale phrase, then a language-only phrase, then English."""
    normalized = locale.replace("_", "-").lower()
    locale_id = normalized if normalized in _LOCALES_BY_ID else normalized.split("-", 1)[0]
    if locale_id not in _LOCALES_BY_ID:
        locale_id = "en"
    locale = _LOCALES_BY_ID[locale_id]
    sample = _SAMPLES_BY_LOCALE[locale_id]
    return {**locale, **sample, "phrase": sample["text"], "phrase_variants": sample["text_variants"]}


def _phrase_settings(stack_id: str, model_id: str | None, voice_id: str, variant_id: str = "neutral") -> dict[str, Any]:
    profiles = PERF_PHRASE_CATALOG["delivery_profiles"]
    if variant_id not in profiles:
        raise ValueError(f"Unknown delivery variant {variant_id!r}; choose from {', '.join(profiles)}")
    profile = profiles[variant_id]
    voice_locale = _voice_locale(stack_id, model_id, voice_id)
    phrase = _phrase_for_locale(voice_locale)
    return {
        "voice_locale": voice_locale,
        "phrase_locale": phrase["locale"],
        "language": phrase["locale"] if voice_locale.lower() == phrase["locale"].lower()
                    else f"{phrase['locale']} (voice {voice_locale})",
        "language_main": phrase["language_main"],
        "language_sub": phrase["language_sub"],
        "phrase_id": phrase["sample_id"],
        "phrase": phrase["phrase_variants"][variant_id],
        "variant_id": variant_id,
        "emotion": profile["emotion"],
        "tone": profile["tone"],
        "expression": profile["expression"],
        "extra_params": {"lang": phrase["language_main"]} if model_id == "supertonic3" else {},
    }

# ── psutil helpers (optional — skip if not installed) ─────────────────────────

_psutil_available = False
try:
    import psutil  # type: ignore
    _psutil_available = True
except ImportError:
    pass


def _get_memory_mb() -> float:
    """Return current process RSS in MB."""
    if not _psutil_available:
        return -1.0
    proc = psutil.Process(os.getpid())
    return proc.memory_info().rss / (1024 * 1024)


def _get_cpu_percent() -> float:
    """Return current process CPU % (non-blocking)."""
    if not _psutil_available:
        return -1.0
    return psutil.Process(os.getpid()).cpu_percent(interval=None)


# ── Status coloring ───────────────────────────────────────────────────────────

def _status_color(value: float, metric: str) -> str:
    """Return ANSI color code based on thresholds."""
    if value < 0:
        return "\033[90m"  # grey (N/A)
    thresh = THRESHOLDS.get(metric, {})
    if value >= thresh.get("error", float("inf")):
        return "\033[91m"  # red
    if value >= thresh.get("warn", float("inf")):
        return "\033[93m"  # yellow
    return "\033[92m"    # green


def _reset_color() -> str:
    return "\033[0m"


# ── Metric collection (mandatory) ─────────────────────────────────────────────

@dataclass
class PerfResult:
    stack_id: str
    model_id: str | None = None
    voice_id: str = ""
    language: str = "en"
    voice_locale: str = "en"
    phrase_locale: str = "en"
    language_main: str = "en"
    language_sub: str | None = None
    phrase_id: str = "welcome-performance-v1:en"
    phrase_chars: int = 0
    variant_id: str = "neutral"
    emotion: str = "neutral"
    tone: str = "measured"
    expression: str = "clear and matter-of-fact"
    # Timing
    first_chunk_ms: float = -1.0   # time until synthesis produces first audio (ML only)
    synthesis_ms: float = 0.0      # total time for full synthesis (speak() → done)
    latency_ms: float = 0.0        # speak() call overhead (legacy alias for synthesis_ms)
    completion_ms: float = 0.0     # speak() → wait_until_done()
    # Audio characteristics (from synthesize() on ML engines)
    audio_samples: int = -1        # frames in output; for mono, equals scalar samples
    audio_duration_s: float = -1.0 # duration in seconds = frames / sample_rate
    audio_bytes: int = -1          # raw PCM size (int16), including all channels
    audio_sample_rate: int = -1    # engine sample rate
    # System
    device: str = "cpu"            # "cuda" or "cpu" — what select_device() picked for this run
    memory_mb: float = -1.0
    cpu_percent: float = -1.0
    gpu_percent: float = -1.0      # GPU compute utilization (requires pynvml)
    gpu_mb: float = -1.0
    skipped: bool = False
    skip_reason: str = ""


def _audio_measurements(audio: Any, sample_rate: int) -> tuple[int, float, int]:
    """Return frame count, duration, and PCM16 byte size for mono or multichannel audio."""
    import numpy as np

    arr = np.asarray(audio)
    frames = int(arr.size if arr.ndim == 1 else arr.shape[0])
    total_samples = int(arr.size)
    duration = frames / sample_rate if sample_rate > 0 else -1.0
    return frames, duration, total_samples * 2


def collect_metrics(
    phrase: str,
    engine: Any,
    voice_id: str,
    listen: bool = True,
    save_path: Path | None = None,
    phrase_settings: dict[str, Any] | None = None,
) -> PerfResult:
    """Run one synthesis cycle and collect timing, audio, and system metrics.

    For ML engines that implement synthesize(), measures audio characteristics
    (samples, duration, bytes, sample rate) and synthesis wall-clock time.
    Falls back to speak()+wait_until_done() for SAPI engines (which always
    plays audio as part of the speak() call itself) — unless save_path is
    given, in which case the SAPI fallback uses speak_to_wav() instead (see
    below), since plain speak() has no way to capture the audio at all.

    If listen=True (default), ML engine audio is played back *after* timing
    is recorded — so you can actually hear each stack/model/voice for a
    quality check, without polluting the synthesis_ms measurement.

    If save_path is given, the generated audio is also written there as a
    WAV file (parent directories created as needed) — used by
    generate_perf_samples() to capture one reference sample per stack/
    model/voice, independent of whatever this call's timing/skip result
    ends up being.
    """
    from src.device import select_device
    result = PerfResult(
        stack_id=getattr(engine, "stack_id", "unknown"),
        model_id=getattr(engine, "model_id", None),
        voice_id=voice_id,
        device=select_device(),
    )
    phrase_settings = phrase_settings or {}
    result.voice_locale = phrase_settings.get("voice_locale", "en")
    result.phrase_locale = phrase_settings.get("phrase_locale", "en")
    result.language = phrase_settings.get("language", result.phrase_locale)
    result.language_main = phrase_settings.get("language_main", "en")
    result.language_sub = phrase_settings.get("language_sub")
    result.phrase_id = phrase_settings.get("phrase_id", "welcome-performance-v1:en")
    result.phrase_chars = len(phrase)
    result.variant_id = phrase_settings.get("variant_id", "neutral")
    result.emotion = phrase_settings.get("emotion", "neutral")
    result.tone = phrase_settings.get("tone", "measured")
    result.expression = phrase_settings.get("expression", "clear and matter-of-fact")

    from src.engines.base import SpeakParams, TtsEngine
    params = SpeakParams(extra=phrase_settings.get("extra_params", {}))

    # ── Memory + CPU baseline ─────────────────────────────────────────────
    mem_before = _get_memory_mb()
    cpu_start = _get_cpu_percent()

    # ── Try synthesize() path (ML engines) ───────────────────────────────
    # Every TtsEngine subclass inherits a callable synthesize() from the base
    # class (default: returns None for engines that can't capture raw audio,
    # e.g. SAPI) — checking callable(engine.synthesize) is therefore ALWAYS
    # True and can't distinguish "ML engine with real synthesize()" from
    # "SAPI, whose synthesize() is a no-op." That bug caused SAPI/Speech
    # Platform to silently skip speak() entirely during every benchmark run
    # (0.0ms readings, no audio ever produced). Fixed by attempting
    # synthesize() unconditionally and falling back to speak() when it
    # returns None, instead of pre-branching on callable().
    t0 = time.perf_counter()
    try:
        synth_result = engine.synthesize(phrase, voice_id, params)
    except Exception as exc:
        result.skipped = True
        result.skip_reason = f"synthesize() failed: {exc}"
        return result
    synthesis_end = time.perf_counter()

    # Only engines that inherit the base no-op implementation (SAPI) may
    # fall back to speak(). An ML engine overriding synthesize() and
    # returning None has failed this voice and must not be reported as a
    # successful ~1 ms measurement.
    if synth_result is None and type(engine).synthesize is not TtsEngine.synthesize:
        result.skipped = True
        result.skip_reason = f"synthesize() returned no audio for voice {voice_id!r}"
        return result

    if synth_result is not None:
        result.synthesis_ms = (synthesis_end - t0) * 1000
        result.first_chunk_ms = result.synthesis_ms  # synthesize() is a single blocking call
        result.latency_ms = result.synthesis_ms

        # synthesize() returns (array, sample_rate) or just the array for
        # engines whose sample rate is fixed (fall back to _SAMPLE_RATE).
        if isinstance(synth_result, tuple) and len(synth_result) == 2:
            audio_arr, sr = synth_result
        else:
            audio_arr, sr = synth_result, getattr(engine, "_SAMPLE_RATE", 24000)

        try:
            result.audio_samples, result.audio_duration_s, result.audio_bytes = _audio_measurements(audio_arr, int(sr))
            result.audio_sample_rate = int(sr)
        except Exception:
            pass  # numpy not available or array format unexpected

        result.completion_ms = result.synthesis_ms

        # ── Save sample (independent of listen/timing) ──────────────────
        if save_path is not None:
            try:
                from src.control.audio_exporter import write_mp3, write_wav
                save_path.parent.mkdir(parents=True, exist_ok=True)
                if save_path.suffix.lower() == ".mp3":
                    write_mp3(audio_arr, sr, save_path)
                else:
                    write_wav(audio_arr, sr, save_path)
            except Exception as exc:
                print(f"    (save failed for {result.stack_id}/{result.model_id}: {exc})")

        # ── Playback (after timing, so it doesn't skew synthesis_ms) ────
        if listen:
            try:
                from src.audio_player import play_audio
                play_audio(audio_arr, sr)
            except Exception as exc:
                print(f"    (playback failed for {result.stack_id}/{result.model_id}: {exc})")

    elif save_path is not None and hasattr(engine, "speak_to_wav"):
        # ── Fallback: speak_to_wav() straight to save_path (SAPI-style
        # engines have no synthesize() to capture audio from — speak_to_wav
        # is the only way to get a file out of them at all) ─────────────
        t0 = time.perf_counter()
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            if save_path.suffix.lower() == ".mp3":
                from src.control.audio_exporter import convert_wav_to_mp3
                tmp_wav = save_path.with_suffix(".wav")
                engine.speak_to_wav(phrase, voice_id, params, tmp_wav)
                convert_wav_to_mp3(tmp_wav, save_path)
                try:
                    tmp_wav.unlink(missing_ok=True)
                except Exception:
                    pass
            else:
                engine.speak_to_wav(phrase, voice_id, params, save_path)
        except Exception as exc:
            result.skipped = True
            result.skip_reason = f"speak_to_wav() failed: {exc}"
            return result
        completion_end = time.perf_counter()
        result.latency_ms = (completion_end - t0) * 1000
        result.synthesis_ms = result.latency_ms
        result.completion_ms = result.latency_ms

    else:
        # ── Fallback: speak() + wait_until_done() (SAPI, or any engine
        # whose synthesize() genuinely couldn't produce audio this time) ──
        t0 = time.perf_counter()
        try:
            engine.speak(phrase, voice_id, params)
        except Exception as exc:
            result.skipped = True
            result.skip_reason = f"speak() failed: {exc}"
            return result
        engine.wait_until_done(timeout_ms=30_000)
        completion_end = time.perf_counter()
        result.latency_ms = (completion_end - t0) * 1000
        result.synthesis_ms = result.latency_ms
        result.completion_ms = result.latency_ms

    # ── System metrics ────────────────────────────────────────────────────
    if _psutil_available:
        result.memory_mb = _get_memory_mb() - mem_before
        result.cpu_percent = max(0.0, _get_cpu_percent() - cpu_start)

    # ── GPU metrics (optional) ────────────────────────────────────────────
    # Whole-GPU snapshot taken right after synthesis, not a process-scoped
    # delta (pynvml has no per-process compute-utilization API) — read as
    # "how busy was the GPU at that moment," same caveat as gpu_mb already
    # had (whole-device memory used, not this process's share of it).
    try:
        import pynvml  # type: ignore
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        result.gpu_mb = mem_info.used / (1024 * 1024)
        util = pynvml.nvmlDeviceGetUtilizationRates(handle)
        result.gpu_percent = float(util.gpu)
        pynvml.nvmlShutdown()
    except Exception:
        result.gpu_mb = -1.0
        result.gpu_percent = -1.0

    return result


# ── Welcome phrase benchmark ──────────────────────────────────────────────────

def _safe_filename(name: str) -> str:
    """Sanitize a voice_id (some SAPI voice IDs are full registry paths with
    backslashes/parens/spaces) into a filesystem-safe filename stem."""
    name = name.split("\\")[-1] if "\\" in name else name
    return re.sub(r'[<>:"/\\|?*]', "_", name).strip() or "voice"


def welcome_phrase_benchmark(
    save_dir: Path | None = None,
    sample_format: str = "wav",
    variant_id: str = "neutral",
    ml_only: bool = False,
) -> list[PerfResult]:
    """Speak each voice's localized performance phrase across installed stacks.

    Returns a list of PerfResults. Skips unavailable stacks/models gracefully.

    If save_dir is given, also writes one audio file per voice under
    save_dir/<stack_id>/[<model_id>/]<voice_id>.<sample_format> — the same layout the
    Manage Voices dialog groups voices in (SAPI5/Speech Platform are flat
    under the stack; ML stacks nest under their model). Used by
    `run.py perf --save-samples` to capture a reference sample set for
    deciding what's small enough to bundle vs. host externally.
    """
    results: list[PerfResult] = []
    skipped: list[str] = []

    from src.config import list_stacks, load_stacks_catalog
    from src.engines.registry import available_stacks

    stacks_yaml = FIXTURES / "stacks.yaml"
    from src.config import models_root as _config_models_root
    models_root = _config_models_root()  # same resolution every engine actually uses

    # Load stack catalog
    load_stacks_catalog(stacks_yaml)
    stack_ids = list_stacks(stacks_yaml)

    for stack_id in stack_ids:
        # ── SAPI5 / Speech Platform (enumerate voices via engine) ─────────
        if stack_id in ("sapi5", "speech_platform"):
            if ml_only:
                continue
            try:
                if sys.platform != "win32":
                    skipped.append(f"{stack_id}: not on Windows")
                    continue

                from src.engines.sapi_win import SapiEngine, SpeechPlatformEngine
                engine = SapiEngine() if stack_id == "sapi5" else SpeechPlatformEngine()
                engine.stack_id = stack_id  # set for perf reporting
                voices = engine.list_voices()

                if not voices:
                    skipped.append(f"{stack_id}: no voices found")
                    continue

                for voice in voices:
                    phrase_settings = _phrase_settings(stack_id, None, voice.id, variant_id)
                    save_path = (
                        save_dir / stack_id / f"{_safe_filename(voice.id)}.{sample_format}"
                        if save_dir is not None else None
                    )
                    r = collect_metrics(
                        phrase_settings["phrase"], engine, voice.id,
                        save_path=save_path, phrase_settings=phrase_settings,
                    )
                    # Truncate registry path to last segment for display
                    r.voice_id = r.voice_id.split("\\")[-1] if "\\" in r.voice_id else r.voice_id
                    results.append(r)

            except Exception as exc:
                skipped.append(f"{stack_id}: {exc}")
            continue

        # ── ML stacks (iterate models) ────────────────────────────────────
        stack_info = available_stacks(stacks_yaml, models_root)
        stack_entry = None
        for s in stack_info:
            if s.id == stack_id and s.models:
                stack_entry = s
                break

        if not stack_entry:
            skipped.append(f"{stack_id}: no models in catalog")
            continue

        for model in stack_entry.models:
            if not model.available:
                skipped.append(f"{stack_id}/{model.id}: weights not installed")
                continue

            # ── Try to load the engine ────────────────────────────────────
            try:
                engine = _load_ml_engine(stack_id, model)
                if engine is None:
                    skipped.append(f"{stack_id}/{model.id}: engine load failed")
                    continue

                # Set stack_id and model_id for perf reporting
                engine.stack_id = stack_id
                engine.model_id = model.id

                voices = engine.list_voices()
                for voice in voices:
                    phrase_settings = _phrase_settings(stack_id, model.id, voice.id, variant_id)
                    save_path = (
                        save_dir / stack_id / model.id / f"{_safe_filename(voice.id)}.{sample_format}"
                        if save_dir is not None else None
                    )
                    r = collect_metrics(
                        phrase_settings["phrase"], engine, voice.id,
                        save_path=save_path, phrase_settings=phrase_settings,
                    )
                    # Truncate registry path to last segment for display
                    r.voice_id = r.voice_id.split("\\")[-1] if "\\" in r.voice_id else r.voice_id
                    results.append(r)

            except Exception as exc:
                skipped.append(f"{stack_id}/{model.id}: {exc}")

    # Print skipped stacks
    if skipped:
        print("\n  Skipped:")
        for s in skipped:
            print(f"    ⏭ {s}")

    return results


def single_case_benchmark(stack_id: str, model_id: str | None, voice_id: str, variant_id: str = "neutral") -> list[PerfResult]:
    """Run the voice-matched localized phrase for one stack/model/voice.

    Mirrors welcome_phrase_benchmark()'s engine-loading logic but for a
    single case instead of iterating everything — for a fast targeted
    check ("did my change to this one engine/voice help or hurt?") instead
    of a multi-minute full sweep across every installed stack.

    Returns a single-element list (skipped=True with skip_reason on any
    failure, so callers/renderers don't need a separate error path).
    """
    from src.config import models_root as _config_models_root
    from src.engines.registry import available_stacks

    stacks_yaml = FIXTURES / "stacks.yaml"
    models_root = _config_models_root()

    if stack_id in ("sapi5", "speech_platform"):
        if sys.platform != "win32":
            r = PerfResult(stack_id=stack_id, model_id=model_id, voice_id=voice_id)
            r.skipped, r.skip_reason = True, f"{stack_id}: not on Windows"
            return [r]
        try:
            from src.engines.sapi_win import SapiEngine, SpeechPlatformEngine
            engine = SapiEngine() if stack_id == "sapi5" else SpeechPlatformEngine()
            engine.stack_id = stack_id
            phrase_settings = _phrase_settings(stack_id, None, voice_id, variant_id)
            r = collect_metrics(phrase_settings["phrase"], engine, voice_id, phrase_settings=phrase_settings)
            r.voice_id = r.voice_id.split("\\")[-1] if "\\" in r.voice_id else r.voice_id
            return [r]
        except Exception as exc:
            r = PerfResult(stack_id=stack_id, model_id=model_id, voice_id=voice_id)
            r.skipped, r.skip_reason = True, str(exc)
            return [r]

    # ── ML stacks ────────────────────────────────────────────────────────
    if not model_id:
        r = PerfResult(stack_id=stack_id, model_id=model_id, voice_id=voice_id)
        r.skipped, r.skip_reason = True, "--model is required for non-SAPI stacks"
        return [r]

    stack_entry = next((s for s in available_stacks(stacks_yaml, models_root) if s.id == stack_id), None)
    model_entry = next((m for m in (stack_entry.models if stack_entry else []) if m.id == model_id), None)
    if model_entry is None:
        r = PerfResult(stack_id=stack_id, model_id=model_id, voice_id=voice_id)
        r.skipped, r.skip_reason = True, f"{stack_id}/{model_id}: not found in catalog"
        return [r]
    if not model_entry.available:
        r = PerfResult(stack_id=stack_id, model_id=model_id, voice_id=voice_id)
        r.skipped, r.skip_reason = True, f"{stack_id}/{model_id}: weights not installed"
        return [r]

    try:
        engine = _load_ml_engine(stack_id, model_entry)
        if engine is None:
            r = PerfResult(stack_id=stack_id, model_id=model_id, voice_id=voice_id)
            r.skipped, r.skip_reason = True, f"{stack_id}/{model_id}: engine load failed"
            return [r]
        engine.stack_id, engine.model_id = stack_id, model_id
        phrase_settings = _phrase_settings(stack_id, model_id, voice_id, variant_id)
        r = collect_metrics(phrase_settings["phrase"], engine, voice_id, phrase_settings=phrase_settings)
        r.voice_id = r.voice_id.split("\\")[-1] if "\\" in r.voice_id else r.voice_id
        return [r]
    except Exception as exc:
        r = PerfResult(stack_id=stack_id, model_id=model_id, voice_id=voice_id)
        r.skipped, r.skip_reason = True, str(exc)
        return [r]


def _load_ml_engine(stack_id: str, model_info: Any) -> Any | None:
    """Load an ML engine instance. Returns None on failure."""
    try:
        model_id = model_info.id
        if model_id == "kokoro":
            from src.engines.kokoro_engine import KokoroEngine
            return KokoroEngine()
        elif model_id == "piper":
            from src.engines.piper_win import PiperEngine
            return PiperEngine()
        elif model_id == "chatterbox":
            from src.engines.chatterbox_engine import ChatterboxEngine
            return ChatterboxEngine()
        elif model_id == "dia":
            from src.engines.dia_engine import DiaEngine
            return DiaEngine()
        elif model_id == "f5tts":
            from src.engines.f5tts_engine import F5TTSEngine
            return F5TTSEngine()
        elif model_id == "outetts":
            from src.engines.outetts_engine import OuteTTSEngine
            return OuteTTSEngine()
        elif model_id == "vibevoice_realtime":
            from src.engines.vibevoice_engine import VibeVoiceEngine
            return VibeVoiceEngine()
        elif model_id == "qwen3tts":
            from src.engines.qwen3tts_engine import Qwen3TTSEngine
            return Qwen3TTSEngine()
        elif model_id == "pockettts":
            from src.engines.pockettts_engine import PocketTTSEngine
            return PocketTTSEngine()
        elif model_id == "supertonic3":
            from src.engines.supertonic3_engine import Supertonic3Engine
            return Supertonic3Engine()
        elif model_id == "moss_tts_nano":
            from src.engines.moss_tts_nano_engine import MossTtsNanoEngine
            return MossTtsNanoEngine()
    except Exception:
        pass
    return None


# ── Console table rendering ───────────────────────────────────────────────────

def render_console_table(results: list[PerfResult]) -> None:
    """Print formatted ASCII table to console with color-coded thresholds."""
    if not results:
        print("\n  No results to display.")
        return

    # Column widths
    col_w = {
        "stack": max(8, max(len(r.stack_id) for r in results)),
        "model": max(6, max(len(r.model_id or "-") for r in results)),
        "voice": max(5, max(len(r.voice_id) for r in results)),
        "language": max(8, min(24, max(len(r.language) for r in results))),
    }
    col_w["dev"]   = 6    # device
    col_w["synth"] = 12   # synthesis_ms
    col_w["dur"]   = 9    # audio_duration_s
    col_w["kb"]    = 8    # audio_bytes → KB
    col_w["sr"]    = 8    # sample_rate
    col_w["mem"]   = 9
    col_w["cpu"]   = 7
    col_w["gpu"]   = 7    # gpu_percent
    col_w["gpumb"] = 9    # gpu_mb

    header_fmt = (
        f"  {{:<{col_w['stack']}}}  "
        f"{{:<{col_w['model']}}}  "
        f"{{:<{col_w['voice']}}}  "
        f"{{:<{col_w['language']}}}  "
        f"{{:<{col_w['dev']}}}  "
        f"{{:>{col_w['synth']}}}  "
        f"{{:>{col_w['dur']}}}  "
        f"{{:>{col_w['kb']}}}  "
        f"{{:>{col_w['sr']}}}  "
        f"{{:>{col_w['mem']}}}  "
        f"{{:>{col_w['cpu']}}}  "
        f"{{:>{col_w['gpu']}}}  "
        f"{{:>{col_w['gpumb']}}}"
    )

    total_width = sum(col_w.values()) + 2 + 10 * 2
    print(f"\n{'─' * total_width}")
    print(header_fmt.format(
        "STACK", "MODEL", "VOICE", "LANGUAGE", "DEVICE",
        "SYNTH(ms)", "DUR(s)", "SIZE(KB)", "RATE(Hz)",
        "MEM(MB)", "CPU(%)", "GPU(%)", "GPU(MB)",
    ))
    print(f"{'─' * total_width}")

    def _fmt_dur(v: float) -> str:
        return f"{v:.2f} s" if v >= 0 else "N/A"

    def _fmt_kb(b: int) -> str:
        return f"{b / 1024:.1f} KB" if b >= 0 else "N/A"

    def _fmt_sr(sr: int) -> str:
        return str(sr) if sr >= 0 else "N/A"

    def _fmt_mb(v: float) -> str:
        return f"{v:.1f} MB" if v >= 0 else "N/A"

    def _fmt_cpu(v: float) -> str:
        return f"{v:.1f} %" if v >= 0 else "N/A"

    def _fmt_gpu_pct(v: float) -> str:
        return f"{v:.0f} %" if v >= 0 else "N/A"

    # Data rows
    for r in results:
        if r.skipped:
            print(f"  {r.stack_id:<{col_w['stack']}}  {r.model_id or '-':<{col_w['model']}}  {r.voice_id:<{col_w['voice']}}  ⏭ {r.skip_reason}")
            continue

        c = _reset_color()
        synth_c = _status_color(r.synthesis_ms, "latency_ms")
        mem_c   = _status_color(r.memory_mb, "memory_mb")
        cpu_c   = _status_color(r.cpu_percent, "cpu_percent")

        print(header_fmt.format(
            f"{synth_c}{r.stack_id}{c}",
            r.model_id or "-",
            r.voice_id[:col_w["voice"]],
            r.language[:col_w["language"]],
            r.device,
            f"{synth_c}{r.synthesis_ms:>8.1f} ms{c}",
            _fmt_dur(r.audio_duration_s),
            _fmt_kb(r.audio_bytes),
            _fmt_sr(r.audio_sample_rate),
            f"{mem_c}{_fmt_mb(r.memory_mb)}{c}",
            f"{cpu_c}{_fmt_cpu(r.cpu_percent)}{c}",
            _fmt_gpu_pct(r.gpu_percent),
            _fmt_mb(r.gpu_mb),
        ))

    # Summary row (timing + audio averages for valid ML runs with audio data)
    valid = [r for r in results if not r.skipped]
    if valid:
        avg_synth = sum(r.synthesis_ms for r in valid) / len(valid)
        valid_dur = [r for r in valid if r.audio_duration_s >= 0]
        avg_dur = sum(r.audio_duration_s for r in valid_dur) / len(valid_dur) if valid_dur else -1.0
        valid_mem = [r for r in valid if r.memory_mb >= 0]
        avg_mem = sum(r.memory_mb for r in valid_mem) / len(valid_mem) if valid_mem else -1.0
        valid_cpu = [r for r in valid if r.cpu_percent >= 0]
        avg_cpu = sum(r.cpu_percent for r in valid_cpu) / len(valid_cpu) if valid_cpu else -1.0
        valid_gpu = [r for r in valid if r.gpu_percent >= 0]
        avg_gpu = sum(r.gpu_percent for r in valid_gpu) / len(valid_gpu) if valid_gpu else -1.0
        valid_gpu_mb = [r for r in valid if r.gpu_mb >= 0]
        avg_gpu_mb = sum(r.gpu_mb for r in valid_gpu_mb) / len(valid_gpu_mb) if valid_gpu_mb else -1.0

        print(f"{'─' * total_width}")
        print(header_fmt.format(
            "AVG", "", "", "",
            f"{avg_synth:>8.1f} ms",
            _fmt_dur(avg_dur),
            "", "",
            _fmt_mb(avg_mem),
            _fmt_cpu(avg_cpu),
            _fmt_gpu_pct(avg_gpu),
            _fmt_mb(avg_gpu_mb),
        ))
        print(f"{'─' * total_width}")


# ── JSON report ───────────────────────────────────────────────────────────────

def write_json_report(results: list[PerfResult], path: Path) -> None:
    """Write raw results to JSON file atomically."""
    data = {
        "timestamp": datetime.now().strftime("%Y%m%d%H%M%S"),
        "platform": {
            "os": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
        },
        "welcome_phrase": WELCOME_PHRASE,
        "performance_phrase_catalog": {
            "phrase_id": PERF_PHRASE_CATALOG["phrase_id"],
            "path": "tests/fixtures/performance_phrases.json",
            "locales": [row["locale"] for row in PERF_PHRASE_CATALOG["locales"]],
        },
        "thresholds": THRESHOLDS,
        "results": [_result_row(r) for r in results],
    }

    # Atomic write: temp → rename
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", dir=path.parent, delete=False) as f:
        json.dump(data, f, indent=2, default=str)
        tmp_path = f.name
    shutil.move(tmp_path, path)

    # Also write a JS wrapper so the HTML can <script src> it
    js_path = path.with_suffix(".js")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".js", dir=path.parent, delete=False) as f:
        f.write(f"const data = {json.dumps(data, indent=2, default=str)};")
        tmp_js = f.name
    shutil.move(tmp_js, js_path)


# ── CSS generation ────────────────────────────────────────────────────────────

def generate_css() -> str:
    """Generate CSS string for the HTML report."""
    return """
body {
    font-family: 'Segoe UI', system-ui, sans-serif;
    background: #f3f6fb;
    color: #182433;
    margin: 0;
    padding: 20px;
}
h1 { color: #174a7e; text-align: center; }
h2 { color: #23476d; margin-top: 30px; }
#info { background: #e6eef8; color: #1c3552; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
#chart-container { width: 100%; min-height: 400px; overflow-x: auto; }
table { width: 100%; border-collapse: collapse; margin-top: 20px; background: #fff; border-radius: 8px; overflow: hidden; }
th { background: #dce8f5; color: #173b5f; padding: 10px; text-align: left; }
td { padding: 8px 10px; border-bottom: 1px solid #d6deea; }
tr:hover { background: #edf4fb; }
.status-ok { color: #17633a; }
.status-warn { color: #855400; }
.status-error { color: #a32323; }
.status-na { color: #687587; }
.error-flag { width: 27px; height: 27px; border: 2px solid #ff4545; border-radius: 50%; background: transparent; color: #ff4545; cursor: pointer; font-size: 17px; font-weight: 900; line-height: 1; padding: 0; margin-right: 7px; vertical-align: middle; }
.error-flag.selected { background: #e32636; color: #fff; box-shadow: 0 0 8px rgba(255,48,48,.55); }
.error-flag:focus-visible { outline: 2px solid #ff9b9b; outline-offset: 2px; }
.star-rating { display: inline-flex; align-items: center; white-space: nowrap; vertical-align: middle; }
.rating-star:disabled { cursor: not-allowed; opacity: .3; }
.rating-star { flex: 0 0 auto; background: transparent; border: 0; color: #68748c; cursor: pointer; font-size: 17px; line-height: 1; padding: 0; }
.rating-star.selected { color: #ffd34e; }
.listen-button { background: #087f23; color: white; border: 0; border-radius: 4px; padding: 5px 8px; cursor: pointer; }
.listen-button:disabled { background: #555; cursor: default; }
.table-wrap { overflow-x: auto; }
.raw-results-panel { background: #fff; border: 1px solid #cbd6e4; border-radius: 9px; padding: 16px; margin: 15px 0; }
.raw-results-panel h2 { margin-top: 0; }
.model-nav { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin: 10px 0 14px; }
.model-nav-label { color: #40516a; font-weight: 600; margin-right: 3px; }
.model-nav button { background: #edf3fa; color: #174a7e; border: 1px solid #9fb4ca; border-radius: 5px; padding: 6px 10px; cursor: pointer; }
.model-nav button:hover, .model-nav button:focus-visible { background: #d8e9f8; outline: 2px solid #4d8fc8; outline-offset: 1px; }
.model-row-highlight { animation: model-row-flash 1.4s ease-out; }
@keyframes model-row-flash { from { background: #ffe89a; } to { background: transparent; } }
button.export { padding: 8px 12px; background: #176b9c; border: 0; border-radius: 5px; color: white; cursor: pointer; }
button.export:hover { background: #2189c4; }
.legend { display: flex; gap: 20px; margin-top: 10px; font-size: 14px; }
.legend-item { display: flex; align-items: center; gap: 5px; cursor: pointer; user-select: none;
    padding: 2px 8px; border-radius: 4px; transition: background 0.15s; }
.legend-item:hover { background: #e3ebf5; }
.legend-item.inactive { opacity: 0.35; }
.legend-dot { width: 12px; height: 12px; border-radius: 50%; }
.legend-hint { font-size: 12px; color: #526176; margin-top: 8px; }
.chart-bar { cursor: pointer; transition: opacity 0.15s; }
#chart-tooltip {
    position: fixed;
    display: none;
    background: #fff;
    color: #182433;
    border: 1px solid #547ba5;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
    pointer-events: none;
    z-index: 1000;
    box-shadow: 0 4px 12px rgba(35,55,80,0.22);
}
#chart-tooltip b { color: #174a7e; }
.report-note { color: #40516a; font: 14px 'Segoe UI', sans-serif; line-height: 1.5; }
.axis-label, .tick text { fill: #34465e; color: #34465e; font: 12px 'Segoe UI', sans-serif; }
.domain, .tick line { stroke: #8998aa; }
.theme-toggle { float: right; background: #174a7e; color: #fff; border: 0; border-radius: 5px; padding: 8px 12px; cursor: pointer; }
.theme-dark { background: #111827; color: #e5edf7; }
.theme-dark h1 { color: #8ecbff; }
.theme-dark h2 { color: #b8d8f2; }
.theme-dark #info { background: #1e293b; color: #e5edf7; }
.theme-dark .report-note, .theme-dark .quality-panel p { color: #c5d2e3; }
.theme-dark table, .theme-dark .raw-results-panel, .theme-dark .quality-panel { background: #1e293b; border-color: #42536a; color: #e5edf7; }
.theme-dark .model-nav-label { color: #d8e3f0; }
.theme-dark .model-nav button { background: #263750; color: #d6eaff; border-color: #607792; }
.theme-dark .model-nav button:hover, .theme-dark .model-nav button:focus-visible { background: #344d6a; }
.theme-dark th { background: #263750; color: #d6eaff; }
.theme-dark td { border-color: #384a61; }
.theme-dark tr:hover { background: #2a3a50; }
.theme-dark .status-ok { color: #83e0a7; }
.theme-dark .status-warn { color: #ffd17c; }
.theme-dark .status-error { color: #ff9b9b; }
.theme-dark .status-na { color: #b3c0d0; }
.theme-dark .legend-item { color: #e5edf7; }
.theme-dark .legend-item:hover { background: #30445f; }
.theme-dark .legend-hint { color: #bdcadd; }
.theme-dark .axis-label, .theme-dark .tick text { fill: #d8e3f0; color: #d8e3f0; }
.theme-dark .domain, .theme-dark .tick line { stroke: #8b9bb0; }
.theme-dark #chart-tooltip { background: #263750; color: #f3f7fc; border-color: #8ecbff; }
.theme-dark #chart-tooltip b { color: #8ecbff; }
.theme-dark .quality-legend button { background: #263750; color: #f3f7fc; border-color: #607792; }
.theme-toggle:hover { filter: brightness(1.1); }
.chart-panel { background: #fff; border: 1px solid #cbd6e4; border-radius: 8px; padding: 16px; margin: 18px 0; }
.chart-panel > summary { color: #23476d; cursor: pointer; font-size: 20px; font-weight: 700; }
.chart-panel[open] > summary { margin-bottom: 12px; }
.chart-controls { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin: 8px 0 12px; color: #40516a; }
.chart-controls label { font-weight: 600; }
.chart-controls select { background: #fff; color: #182433; border: 1px solid #9fb4ca; border-radius: 5px; padding: 6px 9px; }
.theme-dark .chart-panel { background: #1e293b; border-color: #42536a; color: #e5edf7; }
.theme-dark .chart-panel > summary { color: #b8d8f2; }
.theme-dark .chart-controls { color: #d8e3f0; }
.theme-dark .chart-controls select { background: #263750; color: #f3f7fc; border-color: #607792; }
.quality-panel { background: #fff; border: 1px solid #cbd6e4; border-radius: 8px; padding: 16px; margin: 18px 0; }
.quality-panel p { color: #40516a; }
.quality-legend { display: flex; gap: 18px; color: #26364c; margin: 6px 0 12px; }
.quality-legend span { display: inline-flex; gap: 6px; align-items: center; }
.quality-legend i { width: 12px; height: 12px; display: inline-block; border-radius: 50%; }
.quality-legend button { background: #edf3fa; color: #26364c; border: 1px solid #a9b9cb; border-radius: 5px; padding: 5px 9px; cursor: pointer; }
.quality-legend button.inactive { opacity: .45; }
.metric-legend .legend-item { color: #26364c; }
"""


# ── HTML generation ───────────────────────────────────────────────────────────

def generate_html(json_js_path: str) -> str:
    """Generate HTML string that includes data via <script src>."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AlienVox Performance Report</title>
<style>
{generate_css()}
</style>
<script src="https://d3js.org/d3.v7.min.js"></script>
<script src="{json_js_path}"></script>
</head>
<body>
<h1>AlienVox Performance Report</h1>
<button class="theme-toggle" id="theme-toggle" type="button">Switch to dark theme</button>
<div id="info">Rendering report...</div>
<p style="color:#bac4dd;font:14px 'Segoe UI',sans-serif">Each voice uses its matching localized phrase where known. Compare timing within the same phrase locale; translation lengths differ. Locale translations are drafts pending native-speaker review.</p>
<details class="chart-panel" id="metrics-panel">
<summary>Latency, CPU load, and memory</summary>
<p class="report-note">Each metric is normalized to its highest result (100%) so different units can share one chart. Hover a bar to see its model, voice, and measured value.</p>
<div class="chart-controls"><label for="chart-model-filter">Focus model:</label><select id="chart-model-filter" aria-label="Focus the bar chart on a model"></select></div>
<div id="chart-container"></div>
</details>
<div id="chart-tooltip"></div>
<details class="chart-panel quality-panel" id="quality-panel">
<summary>Quality vs latency</summary>
<p>Subjective voice ratings (1–5 stars) compared with latency percentiles across rated voices. CPU appears as an additional series when usable measurements are available.</p>
<div class="quality-legend" id="quality-legend"></div>
<div id="quality-chart"></div>
</details>
<section class="raw-results-panel">
<h2>Raw Results</h2>
<div id="model-nav" class="model-nav" aria-label="Jump to model results"></div>
<p><button class="export" id="export-ratings" type="button">Download metrics + ratings JSON</button></p>
<div class="table-wrap"><table id="results-table">
<thead><tr>
    <th>Stack</th><th>Model</th><th>Voice</th><th>Voice profile</th><th>Voice language</th><th>Sample language</th><th>Phrase chars</th><th>Variant</th><th>Emotion</th><th>Tone</th><th>Device</th>
    <th>Synth (ms)</th><th>Duration (s)</th><th>Size (KB)</th><th>Sample Rate</th>
    <th>Memory (MB)</th><th>CPU (%)</th><th>GPU (%)</th><th>GPU (MB)</th><th>Sample</th><th>Rating</th>
</tr></thead>
<tbody id="results-body"></tbody>
</table></div>
</section>

<script>
const THRESHOLDS = {json.dumps(THRESHOLDS, indent=2)};
const WELCOME_PHRASE = {json.dumps(WELCOME_PHRASE)};

(function() {{
  try {{
    document.getElementById('info').innerHTML =
        '<b>Generated:</b> ' + data.timestamp + ' | ' +
        '<b>Platform:</b> ' + data.platform.os + ' ' + data.platform.release + ' | ' +
        '<b>Python:</b> ' + data.platform.python + ' | ' +
        '<b>Runs:</b> ' + data.results.length;

    const themeToggle = document.getElementById('theme-toggle');
    const themeKey = 'alienvox-report-theme-v1';
    let reportTheme = 'light';
    try {{ reportTheme = localStorage.getItem(themeKey) === 'dark' ? 'dark' : 'light'; }} catch (_) {{}}
    const applyTheme = theme => {{
        reportTheme = theme;
        document.body.classList.toggle('theme-dark', theme === 'dark');
        themeToggle.textContent = theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme';
        themeToggle.setAttribute('aria-pressed', theme === 'dark');
        try {{ localStorage.setItem(themeKey, theme); }} catch (_) {{}}
    }};
    themeToggle.addEventListener('click', () => applyTheme(reportTheme === 'dark' ? 'light' : 'dark'));
    applyTheme(reportTheme);

    const metrics = [
        {{key: 'synthesis_ms', label: 'Latency', unit: 'ms', color: '#2364aa'}},
        {{key: 'cpu_percent', label: 'CPU load', unit: '%', color: '#c45b08'}},
        {{key: 'memory_mb', label: 'Memory', unit: 'MB', color: '#087f8c'}},
    ];
    const metricValue = (row, key) => Number.isFinite(Number(row[key])) && Number(row[key]) >= 0 ? Number(row[key]) : null;
    const allChartable = data.results.filter(d => !d.skipped && metrics.some(m => metricValue(d, m.key) !== null));
    const container = document.getElementById('chart-container');
    const tooltip = document.getElementById('chart-tooltip');
    const modelKey = d => d.model_id ? `${{d.stack_id}}/${{d.model_id}}` : d.stack_id;
    const modelLabel = d => d.model_id || d.stack_id;
    const voiceKey = d => d.voice_id;
    const modelFilter = document.getElementById('chart-model-filter');
    const filterModels = Array.from(new Map(allChartable.map(d => [modelKey(d), {{key: modelKey(d), label: modelLabel(d)}}])).values());
    [['all', 'All models'], ...filterModels.map(group => [group.key, group.label])].forEach(([key, label]) => {{
        const option = document.createElement('option'); option.value = key; option.textContent = label; modelFilter.appendChild(option);
    }});
    const renderMetricChart = () => {{
    if (!document.getElementById('metrics-panel').open) return;
    const chartable = allChartable.filter(d => modelFilter.value === 'all' || modelKey(d) === modelFilter.value);
    container.replaceChildren();
    if (chartable.length) {{
        const margin = {{top: 20, right: 24, bottom: 145, left: 58}};
        const width = Math.max(220, container.clientWidth - margin.left - margin.right);
        const height = 380 - margin.top - margin.bottom;
        const svg = d3.select('#chart-container').append('svg')
            .attr('width', width + margin.left + margin.right)
            .attr('height', height + margin.top + margin.bottom)
            .append('g').attr('transform', `translate(${{margin.left}},${{margin.top}})`);
        const maxima = Object.fromEntries(metrics.map(m => [m.key, d3.max(chartable, d => metricValue(d, m.key) || 0) || 1]));
        const modelGroups = Array.from(d3.group(chartable, modelKey), ([key, rows]) => ({{key, label: modelLabel(rows[0]), rows}}));
        const x0 = d3.scaleBand().domain(modelGroups.map(group => group.key)).range([0, width]).paddingInner(0.16);
        const maxVoices = d3.max(modelGroups, group => group.rows.length) || 1;
        const voiceSlotWidth = x0.bandwidth() / maxVoices;
        const voiceScales = new Map(modelGroups.map(group => [group.key,
            d3.scaleBand().domain(group.rows.map(voiceKey)).range([0, maxVoices * voiceSlotWidth]).paddingInner(0.08)]));
        const x2 = d3.scaleBand().domain(metrics.map(m => m.key)).range([0, voiceSlotWidth]).padding(0.08);
        const y = d3.scaleLinear().domain([0, 100]).range([height, 0]);
        const metricFor = key => metrics.find(m => m.key === key);
        const tooltip = document.getElementById('chart-tooltip');
        const positionTooltip = evt => {{
            const gap = 14, edge = 8;
            const box = tooltip.getBoundingClientRect();
            let left = evt.clientX + gap;
            let top = evt.clientY + gap;
            if (left + box.width > window.innerWidth - edge) left = evt.clientX - box.width - gap;
            if (top + box.height > window.innerHeight - edge) top = evt.clientY - box.height - gap;
            tooltip.style.left = Math.max(edge, left) + 'px';
            tooltip.style.top = Math.max(edge, top) + 'px';
        }};
        svg.append('path').attr('class', 'domain').attr('d', `M0,${{height}}H${{width}}`);
        modelGroups.forEach(group => {{
            const modelX = x0(group.key);
            const scale = voiceScales.get(group.key);
            group.rows.forEach(row => {{
                const center = modelX + scale(row.voice_id) + scale.bandwidth() / 2;
                svg.append('text').attr('class', 'axis-label').attr('x', center).attr('y', height + 5).attr('text-anchor', 'end').attr('transform', `rotate(-45,${{center}},${{height + 5}})`).text(row.voice_id);
            }});
            svg.append('text').attr('class', 'axis-label').attr('x', modelX + x0.bandwidth() / 2).attr('y', height + 112).attr('text-anchor', 'middle').attr('font-weight', '700').text(group.label);
        }});
        svg.append('g').call(d3.axisLeft(y).ticks(5).tickFormat(v => v + '%'));
        svg.append('text').attr('class', 'axis-label').attr('transform', 'rotate(-90)')
            .attr('x', -height / 2).attr('y', -42).attr('text-anchor', 'middle').text('Relative value within metric (max = 100%)');
        const hideTooltip = () => {{ tooltip.style.display = 'none'; }};
        const bars = svg.selectAll('.voice-bars').data(chartable).enter().append('g')
            .attr('transform', d => `translate(${{x0(modelKey(d)) + voiceScales.get(modelKey(d))(voiceKey(d))}},0)`);
        bars.selectAll('rect').data(d => metrics.map(m => ({{row: d, metric: m}}))).enter().append('rect')
            .attr('x', d => x2(d.metric.key)).attr('y', d => y((metricValue(d.row, d.metric.key) || 0) / maxima[d.metric.key] * 100))
            .attr('width', x2.bandwidth())
            .attr('height', d => metricValue(d.row, d.metric.key) === null ? 0 : height - y(metricValue(d.row, d.metric.key) / maxima[d.metric.key] * 100))
            .attr('fill', d => d.metric.color).attr('rx', 2)
            .on('mousemove', (evt, d) => {{
                tooltip.innerHTML = `<b>${{d.metric.label}}</b><br>${{d.row.model_id || d.row.stack_id}}/${{d.row.voice_id}}<br>${{Number(d.row[d.metric.key]).toFixed(1)}} ${{d.metric.unit}}`;
                tooltip.style.display = 'block'; positionTooltip(evt);
            }}).on('mouseleave', hideTooltip);
        document.addEventListener('click', hideTooltip);
        const legend = d3.select('#chart-container').append('div').attr('class', 'legend metric-legend');
        const activeMetrics = new Set(metrics.map(m => m.key));
        const legendItems = new Map();
        metrics.forEach(m => {{
            const item = legend.append('div').attr('class', 'legend-item').on('click', () => {{
                if (activeMetrics.size === metrics.length) activeMetrics.delete(m.key);
                else if (activeMetrics.size === 1 && activeMetrics.has(m.key)) metrics.forEach(value => activeMetrics.add(value.key));
                else {{ activeMetrics.clear(); activeMetrics.add(m.key); }}
                if (!activeMetrics.size) activeMetrics.add(m.key);
                metrics.forEach(value => legendItems.get(value.key).classed('inactive', !activeMetrics.has(value.key)));
                svg.selectAll('rect').style('display', d => activeMetrics.has(d.metric.key) ? null : 'none');
            }});
            item.append('div').attr('class', 'legend-dot').style('background', m.color);
            item.append('span').text(`${{m.label}} (${{m.unit}})`); legendItems.set(m.key, item);
        }});
    }}
    }};
    modelFilter.addEventListener('change', renderMetricChart);
    document.getElementById('metrics-panel').addEventListener('toggle', () => {{
        if (document.getElementById('metrics-panel').open) renderMetricChart();
    }});
    const tbody = document.getElementById('results-body');
    const ratingsKey = 'alienvox-voice-ratings-v1';
    const errorsKey = 'alienvox-voice-errors-v1';
    const loadFeedback = (stableKey, legacyPrefixes, errorEntries = false) => {{
        const saved = {{}};
        try {{
            for (let i = 0; i < localStorage.length; i++) {{
                const key = localStorage.key(i);
                if (key !== stableKey && legacyPrefixes.some(prefix => key.startsWith(prefix)) && key.endsWith('-errors') === errorEntries) {{
                    Object.assign(saved, JSON.parse(localStorage.getItem(key) || '{{}}'));
                }}
            }}
            Object.assign(saved, JSON.parse(localStorage.getItem(stableKey) || '{{}}'));
            localStorage.setItem(stableKey, JSON.stringify(saved));
        }} catch (_) {{}}
        return saved;
    }};
    const voiceRatings = loadFeedback(ratingsKey, ['alienvox-voice-ratings-', 'alienvox-voice-quality-']);
    const voiceErrors = loadFeedback(errorsKey, ['alienvox-voice-ratings-', 'alienvox-voice-quality-'], true);
    const rowKey = d => d.model_id ? d.model_id + '/' + d.voice_id : d.stack_id + '/' + d.voice_id;
    const renderQualityChart = () => {{
        if (!document.getElementById('quality-panel').open) return;
        const root = document.getElementById('quality-chart'); root.replaceChildren();
        const ratedRows = data.results.filter(d => !d.skipped && Number(voiceRatings[rowKey(d)]) >= 1 && Number(voiceRatings[rowKey(d)]) <= 5 && voiceErrors[rowKey(d)] !== true);
        if (!ratedRows.length) {{
            root.textContent = 'Rate voices in Raw Results to populate this chart.';
            return;
        }}
        const costs = [
            {{key: 'synthesis_ms', label: 'Latency', unit: 'ms', color: '#087f8c', shape: d3.symbolCircle}},
        ];
        if (ratedRows.some(d => Number(d.cpu_percent) > 0))
            costs.push({{key: 'cpu_percent', label: 'CPU load', unit: '%', color: '#6c3fc5', shape: d3.symbolDiamond}});
        const costSamples = Object.fromEntries(costs.map(cost => [cost.key,
            ratedRows.map(d => Number(d[cost.key])).filter(value => value >= 0)]));
        const points = ratedRows.flatMap(row => costs.filter(cost => Number(row[cost.key]) >= 0).map(cost => ({{
            row, cost, score: Number(voiceRatings[rowKey(row)]),
            percentile: (() => {{
                const values = costSamples[cost.key], value = Number(row[cost.key]);
                const below = values.filter(item => item < value).length;
                const tied = values.filter(item => item === value).length;
                return values.length <= 1 || below + tied === values.length && below === 0
                    ? 50
                    : 100 * (below + (tied - 1) / 2) / (values.length - 1);
            }})(),
        }})));
        const margin = {{top: 20, right: 24, bottom: 58, left: 58}};
        const width = Math.max(320, document.getElementById('quality-panel').clientWidth) - margin.left - margin.right;
        const height = 320 - margin.top - margin.bottom;
        const svg = d3.select(root).append('svg').attr('width', '100%').attr('viewBox', `0 0 ${{width + margin.left + margin.right}} 320`)
            .append('g').attr('transform', `translate(${{margin.left}},${{margin.top}})`);
        const x = d3.scaleLinear().domain([0, 100]).range([0, width]);
        const y = d3.scaleLinear().domain([0.5, 5.5]).range([height, 0]);
        svg.append('g').attr('transform', `translate(0,${{height}})`).call(d3.axisBottom(x).ticks(5).tickFormat(v => 'P' + Math.round(v)));
        svg.append('g').call(d3.axisLeft(y).ticks(5).tickFormat(v => v + ' ★'));
        svg.append('text').attr('class', 'axis-label').attr('x', width / 2).attr('y', height + 45).attr('text-anchor', 'middle')
            .text(costs.length > 1
                ? 'Latency / CPU percentile among rated voices (P0 = lower, P100 = higher)'
                : 'Latency percentile among rated voices (P0 = fastest, P100 = slowest)');
        const tooltip = document.getElementById('chart-tooltip');
        const positionTooltip = evt => {{
            const gap = 14, edge = 8;
            const box = tooltip.getBoundingClientRect();
            let left = evt.clientX + gap;
            let top = evt.clientY + gap;
            if (left + box.width > window.innerWidth - edge) left = evt.clientX - box.width - gap;
            if (top + box.height > window.innerHeight - edge) top = evt.clientY - box.height - gap;
            tooltip.style.left = Math.max(edge, left) + 'px';
            tooltip.style.top = Math.max(edge, top) + 'px';
        }};
        const qualityMarks = svg.selectAll('.quality-point').data(points).enter().append('path')
            .attr('class', 'quality-point').attr('transform', d => `translate(${{x(d.percentile)}},${{y(d.score)}})`)
            .attr('d', d => d3.symbol().type(d.cost.shape).size(100)())
            .attr('fill', d => d.cost.color).attr('stroke', '#26364c').attr('stroke-width', 1)
            .on('mousemove', (evt, d) => {{
                tooltip.innerHTML = `<b>${{d.cost.label}} vs quality</b><br>${{d.row.model_id || d.row.stack_id}}/${{d.row.voice_id}}<br>Quality: ${{d.score}} / 5<br>${{d.cost.label}}: P${{Math.round(d.percentile)}} (${{Number(d.row[d.cost.key]).toFixed(1)}} ${{d.cost.unit}})`;
                tooltip.style.display = 'block'; positionTooltip(evt);
            }}).on('mouseleave', () => {{ tooltip.style.display = 'none'; }});
        const legend = d3.select('#quality-legend');
        costs.forEach(cost => {{
            const item = legend.append('span');
            item.append('i').style('background', cost.color);
            item.append('span').text(cost.label);
        }});
    }};
    const addRatingCell = (tr, d) => {{
        const td = tr.insertCell();
        const wrap = document.createElement('span'); wrap.className = 'star-rating';
        const key = rowKey(d);
        if (voiceErrors[key] === true && Object.prototype.hasOwnProperty.call(voiceRatings, key)) {{
            delete voiceRatings[key];
            try {{ localStorage.setItem(ratingsKey, JSON.stringify(voiceRatings)); }} catch (_) {{}}
        }}
        const error = document.createElement('button'); error.type = 'button'; error.className = 'error-flag';
        error.textContent = '!'; error.title = 'Flag an error for ' + key + '; this blocks star rating until cleared.';
        error.setAttribute('aria-label', error.title); error.setAttribute('aria-pressed', voiceErrors[key] === true); error.classList.toggle('selected', voiceErrors[key] === true);
        error.addEventListener('click', () => {{
            voiceErrors[key] = voiceErrors[key] !== true;
            if (voiceErrors[key]) {{
                delete voiceRatings[key];
                wrap.querySelectorAll('.rating-star').forEach(star => {{ star.disabled = true; star.classList.remove('selected'); }});
                try {{ localStorage.setItem(ratingsKey, JSON.stringify(voiceRatings)); }} catch (_) {{}}
            }} else {{
                wrap.querySelectorAll('.rating-star').forEach(star => {{ star.disabled = false; }});
            }}
            error.classList.toggle('selected', voiceErrors[key]);
            error.title = (voiceErrors[key] ? 'Error reported; clear to rate ' : 'Report an error for ') + key;
            error.setAttribute('aria-label', error.title); error.setAttribute('aria-pressed', voiceErrors[key]);
            try {{ localStorage.setItem(errorsKey, JSON.stringify(voiceErrors)); }} catch (_) {{ alert('Browser storage is unavailable; export the JSON to keep error reports.'); }}
            renderQualityChart();
        }});
        wrap.appendChild(error);
        for (let score = 1; score <= 5; score++) {{
            const star = document.createElement('button'); star.type = 'button'; star.className = 'rating-star'; star.textContent = '\u2605';
            star.title = 'Rate ' + key + ' ' + score + ' out of 5'; star.setAttribute('aria-label', star.title);
            star.disabled = voiceErrors[key] === true;
            if (star.disabled) star.title = 'Clear the error flag before rating ' + key;
            star.classList.toggle('selected', voiceErrors[key] !== true && Number(voiceRatings[key]) >= score);
            star.addEventListener('click', () => {{
                if (voiceErrors[key] === true) return;
                voiceRatings[key] = score;
                wrap.querySelectorAll('.rating-star').forEach((item, index) => item.classList.toggle('selected', index < score));
                try {{ localStorage.setItem(ratingsKey, JSON.stringify(voiceRatings)); }} catch (_) {{ alert('Browser storage is unavailable; export the JSON to keep ratings.'); }}
                renderQualityChart();
            }});
            wrap.appendChild(star);
        }}
        td.appendChild(wrap);
    }};
    document.getElementById('export-ratings').addEventListener('click', () => {{
        const payload = {{ schema_version: 1, benchmark_timestamp: data.timestamp, welcome_phrase: data.welcome_phrase,
            platform: data.platform, voice_ratings: voiceRatings, voice_errors: voiceErrors,
            results: data.results.map(row => ({{...row, user_rating_1_to_5: voiceRatings[rowKey(row)] ?? null,
                error_reported: voiceErrors[rowKey(row)] === true}})) }};
        const blob = new Blob([JSON.stringify(payload, null, 2)], {{type: 'application/json'}});
        const url = URL.createObjectURL(blob); const a = document.createElement('a');
        a.href = url; a.download = 'alienvox-performance-ratings-' + data.timestamp + '.json'; a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
    }});
    const modelNav = document.getElementById('model-nav');
    const navModelKey = d => d.model_id ? `${{d.stack_id}}/${{d.model_id}}` : d.stack_id;
    const firstRowByModel = new Map();
    const modelGroups = Array.from(new Map(data.results.map(d => [navModelKey(d), {{key: navModelKey(d), label: d.model_id || d.stack_id}}])).values());
    const navLabel = document.createElement('span'); navLabel.className = 'model-nav-label'; navLabel.textContent = 'Jump to model:';
    modelNav.appendChild(navLabel);
    modelGroups.forEach(group => {{
        const button = document.createElement('button'); button.type = 'button'; button.textContent = group.label;
        button.title = 'Scroll to ' + group.key; button.setAttribute('aria-label', 'Jump to ' + group.key);
        button.addEventListener('click', () => {{
            const row = firstRowByModel.get(group.key);
            if (row) {{
                row.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                row.classList.remove('model-row-highlight'); void row.offsetWidth; row.classList.add('model-row-highlight');
            }}
        }});
        modelNav.appendChild(button);
    }});
    data.results.forEach(d => {{
        const tr = tbody.insertRow();
        const groupKey = navModelKey(d);
        tr.dataset.modelKey = groupKey;
        if (!firstRowByModel.has(groupKey)) firstRowByModel.set(groupKey, tr);
        if (d.skipped) {{
            const td = tr.insertCell();
            td.colSpan = 21;
            td.className = 'status-na';
            td.textContent = `${{d.stack_id}}${{d.model_id ? '/' + d.model_id : ''}}/${{d.voice_id}} — skipped: ${{d.skip_reason}}`;
            return;
        }}
        const cols = [
            {{ key: 'stack_id',          fmt: v => v }},
            {{ key: 'model_id',          fmt: v => v ?? '-' }},
            {{ key: 'voice_id',          fmt: v => v }},
            {{ key: 'voice_profile',     fmt: v => v || 'Unknown' }},
            {{ key: 'voice_locale',     fmt: v => v || 'unknown' }},
            {{ key: 'phrase_locale',    fmt: v => v || 'unknown' }},
            {{ key: 'phrase_chars',      fmt: v => String(v ?? 0) }},
            {{ key: 'variant_id',        fmt: v => v || 'neutral' }},
            {{ key: 'emotion',           fmt: v => v || 'neutral' }},
            {{ key: 'tone',              fmt: v => v || 'measured' }},
            {{ key: 'device',            fmt: v => v ?? '-' }},
            {{ key: 'synthesis_ms',      fmt: v => v >= 0 ? v.toFixed(1) + ' ms' : 'N/A' }},
            {{ key: 'audio_duration_s',  fmt: v => v >= 0 ? v.toFixed(2) + ' s'  : 'N/A' }},
            {{ key: 'audio_bytes',       fmt: v => v >= 0 ? (v/1024).toFixed(1) + ' KB' : 'N/A' }},
            {{ key: 'audio_sample_rate', fmt: v => v >= 0 ? v.toString()          : 'N/A' }},
            {{ key: 'memory_mb',         fmt: v => v >= 0 ? v.toFixed(1) + ' MB' : 'N/A' }},
            {{ key: 'cpu_percent',       fmt: v => v >= 0 ? v.toFixed(1) + '%'   : 'N/A' }},
            {{ key: 'gpu_percent',       fmt: v => v >= 0 ? v.toFixed(0) + '%'   : 'N/A' }},
            {{ key: 'gpu_mb',            fmt: v => v >= 0 ? v.toFixed(1) + ' MB' : 'N/A' }},
        ];
        cols.forEach(({{ key, fmt }}) => {{
            const td = tr.insertCell();
            const val = d[key];
            if (val === -1 || val === null || val === undefined) {{ td.className = 'status-na'; }}
            else if (THRESHOLDS[key] && val >= THRESHOLDS[key].error) {{ td.className = 'status-error'; }}
            else if (THRESHOLDS[key] && val >= THRESHOLDS[key].warn)  {{ td.className = 'status-warn'; }}
            else {{ td.className = 'status-ok'; }}
            td.textContent = fmt(val);
        }});
        const sampleCell = tr.insertCell();
        if (d.sample_url) {{
            const play = document.createElement('button'); play.type = 'button';
            play.className = 'listen-button'; play.textContent = 'Play';
            play.title = 'Play the offline sample for ' + d.voice_id;
            play.setAttribute('aria-label', play.title);
            const audio = document.createElement('audio'); audio.preload = 'none'; audio.src = d.sample_url;
            play.addEventListener('click', () => {{
                document.querySelectorAll('#results-body audio').forEach(other => {{
                    if (other !== audio) {{ other.pause(); other.currentTime = 0; }}
                }});
                if (audio.paused) {{
                    document.querySelectorAll('.listen-button').forEach(button => {{ button.textContent = 'Play'; }});
                    audio.play().then(() => {{ play.textContent = 'Pause'; }}).catch(() => {{ play.textContent = 'Unavailable'; }});
                }} else {{ audio.pause(); audio.currentTime = 0; play.textContent = 'Play'; }}
            }});
            audio.addEventListener('ended', () => {{ play.textContent = 'Play'; }});
            sampleCell.append(play, audio);
        }} else {{
            sampleCell.className = 'status-na'; sampleCell.textContent = 'N/A';
        }}
        addRatingCell(tr, d);
    }});
    document.getElementById('quality-panel').addEventListener('toggle', () => {{
        if (document.getElementById('quality-panel').open) renderQualityChart();
    }});
    renderQualityChart();
  }} catch (err) {{
    document.getElementById('info').innerHTML = '<b>Error rendering:</b> ' + err.message;
    console.error(err);
  }}
}})();
</script>
</body>
</html>"""


# ── HTML report writer ────────────────────────────────────────────────────────

def write_html_report(html_str: str, path: Path) -> None:
    """Write HTML report to the given path."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", dir=path.parent, delete=False, encoding="utf-8") as f:
        f.write(html_str)
        tmp_path = f.name
    shutil.move(tmp_path, path)


def _report_sample_url(
    result: PerfResult, sample_dir: Path | None, report_dir: Path, sample_format: str,
) -> str | None:
    """Return a report-relative URL for a saved sample when the file exists."""
    if sample_dir is None or result.skipped:
        return None
    parts = [result.stack_id]
    if result.model_id:
        parts.append(result.model_id)
    parts.append(f"{_safe_filename(result.voice_id)}.{sample_format}")
    sample_path = sample_dir.joinpath(*parts)
    if not sample_path.is_file():
        return None
    return Path(os.path.relpath(sample_path, report_dir)).as_posix()


# ── Report generation (orchestrator) ──────────────────────────────────────────

def generate_reports(
    results: list[PerfResult], sample_dir: Path | None = None, sample_format: str = "wav",
) -> tuple[Path, Path]:
    """Generate JSON + HTML reports in .logs/ with timestamp naming.

    Returns (json_path, html_path).
    """
    LOGS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")

    json_path = LOGS_DIR / f"{ts}.json"
    html_path = LOGS_DIR / f"{ts}.html"

    report_data = [_result_row(result) for result in results]
    for result, row in zip(results, report_data):
        row["sample_url"] = _report_sample_url(result, sample_dir, LOGS_DIR, sample_format)
    # Keep the regular results schema intact; add the optional playback URL to
    # the report's JS payload only.
    write_json_report(results, json_path)
    # HTML includes the JS file via <script src>
    js_rel = f"./{ts}.js"
    write_html_report(generate_html(js_rel), html_path)
    js_path = json_path.with_suffix(".js")
    data = json.loads(js_path.read_text(encoding="utf-8").removeprefix("const data = ").rstrip(";"))
    for row, report_row in zip(data["results"], report_data):
        row["sample_url"] = report_row["sample_url"]
    js_path.write_text(f"const data = {json.dumps(data, indent=2, default=str)};", encoding="utf-8")

    return json_path, html_path


# ── Pytest integration (unit benchmarks only — no real-speech) ────────────────

# Real-speech benchmark runs standalone via run.py cmd_perf() because SAPI COM
# requires STA threading, which pytest's test runner does not set up correctly.


# ── Unit-level benchmarks (no audio required) ─────────────────────────────────

class TestPerfAudioMeasurements:
    def test_mono_audio_metrics(self):
        import numpy as np

        assert _audio_measurements(np.zeros(24_000, dtype=np.float32), 24_000) == (
            24_000, 1.0, 48_000
        )

    def test_stereo_audio_uses_frames_and_counts_both_channels(self):
        import numpy as np

        assert _audio_measurements(np.zeros((48_000, 2), dtype=np.float32), 48_000) == (
            48_000, 1.0, 192_000
        )

    def test_nonpositive_sample_rate_has_unknown_duration(self):
        import numpy as np

        assert _audio_measurements(np.zeros((8, 2), dtype=np.float32), 0) == (8, -1.0, 32)

    def test_ml_engine_returning_no_audio_is_marked_skipped(self):
        class NoAudioEngine:
            stack_id = "ml"
            model_id = "f5tts"

            def synthesize(self, phrase, voice_id, params):
                return None

        result = collect_metrics("sample phrase", NoAudioEngine(), "preset", listen=False)
        assert result.skipped
        assert "returned no audio" in result.skip_reason
        assert result.audio_samples == -1


class TestConfigPerf:
    """Existing unit benchmarks — timing contracts for config/registry/telemetry."""

    def test_load_stacks_catalog_under_20ms(self):
        from src.config import load_stacks_catalog
        stacks_yaml = FIXTURES / "stacks.yaml"
        ms = _elapsed_ms(load_stacks_catalog, stacks_yaml)
        print(f"\n  load_stacks_catalog: {ms:.2f} ms")
        assert ms < 20, f"load_stacks_catalog took {ms:.1f} ms (threshold 20 ms)"

    def test_list_stacks_under_20ms(self):
        from src.config import list_stacks
        stacks_yaml = FIXTURES / "stacks.yaml"
        ms = _elapsed_ms(list_stacks, stacks_yaml)
        print(f"\n  list_stacks: {ms:.2f} ms")
        assert ms < 20, f"list_stacks took {ms:.1f} ms (threshold 20 ms)"

    def test_load_effective_config_under_30ms(self, tmp_path):
        from src.config import load_effective_config
        stacks_yaml = FIXTURES / "stacks.yaml"
        user_yaml = tmp_path / "user.yaml"
        ms = _elapsed_ms(load_effective_config, "sapi5", stacks_file=stacks_yaml, user_file=user_yaml)
        print(f"\n  load_effective_config: {ms:.2f} ms")
        assert ms < 30, f"load_effective_config took {ms:.1f} ms (threshold 30 ms)"

    def test_get_controls_under_25ms(self):
        from src.config import get_controls
        stacks_yaml = FIXTURES / "stacks.yaml"
        ms = _elapsed_ms(get_controls, "sapi5", stacks_yaml=stacks_yaml)
        print(f"\n  get_controls: {ms:.2f} ms")
        assert ms < 25, f"get_controls took {ms:.1f} ms (threshold 25 ms)"


class TestRegistryPerf:
    def test_available_stacks_under_50ms(self, tmp_path):
        from src.engines.registry import available_stacks
        stacks_yaml = FIXTURES / "stacks.yaml"
        ms = _elapsed_ms(available_stacks, stacks_yaml, tmp_path)
        print(f"\n  available_stacks (no weights): {ms:.2f} ms")
        assert ms < 50, f"available_stacks took {ms:.1f} ms (threshold 50 ms)"

    def test_available_stacks_with_weights_under_50ms(self, tmp_path):
        from src.engines.registry import available_stacks
        stacks_yaml = FIXTURES / "stacks.yaml"
        (tmp_path / "ml" / "kokoro").mkdir(parents=True)
        (tmp_path / "ml" / "piper").mkdir(parents=True)
        ms = _elapsed_ms(available_stacks, stacks_yaml, tmp_path)
        print(f"\n  available_stacks (with weights): {ms:.2f} ms")
        assert ms < 50, f"available_stacks took {ms:.1f} ms (threshold 50 ms)"


class TestTelemetryPerf:
    def test_emit_single_event_under_5ms(self, tmp_path):
        from src.control.telemetry import Telemetry
        tel = Telemetry(sink=tmp_path / "tel.jsonl")
        ms = _elapsed_ms(tel.emit, "speak_start", engine="sapi5", text_chars=100)
        print(f"\n  telemetry.emit (single): {ms:.2f} ms")
        assert ms < 5, f"telemetry.emit took {ms:.1f} ms (threshold 5 ms)"

    def test_emit_100_events_under_200ms(self, tmp_path):
        from src.control.telemetry import Telemetry
        tel = Telemetry(sink=tmp_path / "tel.jsonl")
        t0 = time.perf_counter()
        for i in range(100):
            tel.emit("speak_start", engine="sapi5", text_chars=i)
        ms = (time.perf_counter() - t0) * 1000
        print(f"\n  telemetry.emit x100: {ms:.2f} ms ({ms/100:.3f} ms/event)")
        assert ms < 200, f"100 telemetry events took {ms:.1f} ms (threshold 200 ms)"

    def test_jsonl_file_is_valid_json_per_line(self, tmp_path):
        from src.control.telemetry import Telemetry
        sink = tmp_path / "tel.jsonl"
        tel = Telemetry(sink=sink)
        for i in range(5):
            tel.emit("speak_start", engine="sapi5", text_chars=i * 10)
        lines = sink.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 5
        for line in lines:
            record = json.loads(line)
            assert "event" in record
            assert "timestamp_unix_ms" in record
            assert "session_id" in record


# ── Helpers (used by benchmarks) ──────────────────────────────────────────────

def _elapsed_ms(fn, *args, **kwargs) -> float:
    """Return median warm-call latency to reduce first-call scheduling noise."""
    import statistics

    fn(*args, **kwargs)  # warm caches and filesystem metadata
    measurements = []
    for _ in range(7):
        t0 = time.perf_counter()
        fn(*args, **kwargs)
        measurements.append((time.perf_counter() - t0) * 1000)
    return statistics.median(measurements)


# ── CLI entry point (python -m tests.test_perf _benchmark) ───────────────────

if __name__ == "__main__":
    # Windows consoles often default to cp1252, which can't encode the
    # emoji/box-drawing characters used in this benchmark's output.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    if "_benchmark" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("_benchmark", nargs="?")
        parser.add_argument("--stack", default=None, help="Run a single stack/model/voice instead of the full sweep")
        parser.add_argument("--model", default=None, help="Required for non-SAPI stacks (e.g. kokoro, vibevoice_realtime)")
        parser.add_argument("--voice", default=None, help="Voice ID within --stack/--model (see stacks.yaml)")
        parser.add_argument("--variant", choices=tuple(PERF_PHRASE_CATALOG["delivery_profiles"]), default="neutral", help="Localized delivery cue profile")
        parser.add_argument(
            "--save-samples", action="store_true",
            help="Also save one sample per stack/model/voice under .generated/perf_samples/ "
                 "(gitignored) — full sweep only, ignored with --stack",
        )
        parser.add_argument(
            "--sample-format",
            choices=("wav", "mp3"),
            default="wav",
            help="Audio format to use with --save-samples (default: wav)",
        )
        parser.add_argument(
            "--samples-dir", default=None,
            help="Override the --save-samples output dir (default: <repo>/.generated/perf_samples)",
        )
        args = parser.parse_args()

        if args.stack:
            if not args.voice:
                print("ERROR: --voice is required when --stack is given.")
                sys.exit(1)
            print(f"\n  Running single case: stack={args.stack} model={args.model or '-'} voice={args.voice}...\n")
            results = single_case_benchmark(args.stack, args.model, args.voice, args.variant)
        else:
            save_dir = None
            if args.save_samples:
                save_dir = Path(args.samples_dir) if args.samples_dir else ROOT / ".generated" / "perf_samples"
                print(f"\n  Saving one {args.sample_format.upper()} per voice to {save_dir}\n")
            print("\n  Running welcome-phrase benchmark on all available stacks/models/voices...\n")
            results = welcome_phrase_benchmark(save_dir=save_dir, sample_format=args.sample_format, variant_id=args.variant)

            json_path, html_path = generate_reports(
                results, sample_dir=save_dir, sample_format=args.sample_format,
            )
        print(f"\n  JSON report: {json_path}")
        print(f"  HTML report: {html_path}")
        render_console_table(results)
        print()

        if results and results[0].skipped and args.stack:
            sys.exit(1)
