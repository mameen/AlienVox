#!/usr/bin/env python3
"""AlienVox TTS skill — CLI wrapper around the vendored alienvox_tts library
(../alienvox_tts, one level up from this script). Self-sufficient: this
skill folder can be copied on its own and it still runs — no sibling
../../../python_lib dependency.

Thin by design: all real synthesis logic lives in alienvox_tts, this file
only does argument parsing, path resolution, and reporting results in a
script-friendly way (exit codes, printed facts) — no synthesis logic
duplicated here, per the Agent Skills authoring guide's "scripts do
deterministic work, skills document judgment" split.

Usage:
    python speak.py "Text to speak" [--voice af_heart] [--engine kokoro]
                     [--device cpu|gpu|auto] [--no-play] [--out output.wav]
                     [--rate 0] [--pitch 0] [--volume 100]

Plays through the local default audio device BY DEFAULT — this script
runs on the same machine as whoever's asking, so there's a real speaker to
play through; generating a WAV file nobody opens is the wrong default.
Pass --no-play to suppress playback, and/or --out to also (or instead)
write a real file. At least one of playback or --out must be active —
running with both suppressed would do real synthesis work and then
silently discard it, which is never useful.

Exit codes: 0 on success, 1 on any failure (missing deps, empty text,
synthesis error) — always with a message on stderr, never a silent exit.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# alienvox_tts is vendored one level up from this script
# (.agents/SKILLS/alien_vox/scripts/speak.py -> alien_vox/alienvox_tts) —
# this skill is self-sufficient, no sibling ../../../python_lib dependency.
_SKILL_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SKILL_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Synthesize speech with AlienVox's Kokoro-82M TTS engine (local, offline).",
    )
    parser.add_argument("text", help="Text to speak")
    parser.add_argument("--voice", default="af_heart", help="Voice id (default: af_heart). See references/voices.md.")
    parser.add_argument("--engine", default="kokoro", help="Engine id (default: kokoro — the only one currently shipped).")
    parser.add_argument("--device", default="cpu", choices=["cpu", "gpu"],
                         help="Device (default: cpu — the real, enforced default; pass gpu to opt into CUDA if available).")
    parser.add_argument("--no-play", action="store_true", help="Suppress local playback (default: plays).")
    parser.add_argument("--out", default=None, help="Also write a .wav file to this path (default: no file written).")
    parser.add_argument("--rate", type=int, default=0, help="Speech rate, -10..10 (default: 0, natural pace).")
    parser.add_argument("--pitch", type=int, default=0, help="Pitch, -10..10 (ignored by Kokoro — no pitch control).")
    parser.add_argument("--volume", type=int, default=100, help="Volume, 0..100 (default: 100).")
    args = parser.parse_args()

    if not args.text.strip():
        print("ERROR: text is empty (or whitespace-only) — nothing to speak.", file=sys.stderr)
        return 1

    will_play = not args.no_play
    if not will_play and not args.out:
        print(
            "ERROR: --no-play was passed without --out — that would synthesize "
            "audio and then discard it with nothing to show for it. Pass --out "
            "to save a file, or drop --no-play to hear it.",
            file=sys.stderr,
        )
        return 1

    try:
        from alienvox_tts import synthesize
        from alienvox_tts.device import select_device
    except ImportError as exc:
        print(
            f"ERROR: missing dependency ({exc}). "
            "Run: pip install -r <repo_root>/python_lib/requirements.txt",
            file=sys.stderr,
        )
        return 1

    # Same resolution synthesize() itself applies internally (get_engine() ->
    # select_device()) — computed again here only so it can be printed for
    # visibility, not a separate/parallel decision.
    print(f"device: {select_device(prefer=args.device)}", file=sys.stderr)

    try:
        audio, sample_rate = synthesize(
            args.text, voice=args.voice, engine=args.engine, device=args.device,
            rate=args.rate, pitch=args.pitch, volume=args.volume,
        )
    except Exception as exc:
        print(f"ERROR: synthesis failed: {exc}", file=sys.stderr)
        return 1

    duration_s = len(audio) / sample_rate
    print(f"sample_rate: {sample_rate}")
    print(f"duration_s: {duration_s:.2f}")

    if args.out:
        import soundfile as sf
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_path), audio, sample_rate)
        print(f"output: {out_path}")

    if will_play:
        from alienvox_tts.audio import play_audio
        play_audio(audio, sample_rate)
        print("played: true")

    return 0


if __name__ == "__main__":
    sys.exit(main())
