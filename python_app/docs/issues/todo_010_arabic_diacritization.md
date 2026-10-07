# TODO #010: Automatic Arabic diacritization (tashkeel) before synthesis

**Status:** Open
**Created:** 2026-10-06
**Scope:** Text enhancement (`src/control/text_enhancer.py`) and the `alien_vox` skill (`alienvox_tts`). Applies to every engine that reads Arabic, today the networked `edge` engine.

---

## Problem

Arabic is normally written without short vowels, and a TTS engine has to guess them. The guess is sometimes wrong in a way that changes the word. Seen in practice (Quran Research how-to narration, edge `ar-SA-HamedNeural`): "تستخدم" was read as the passive "تُستخدم" instead of "تَستخدم". This is a language requirement, not a voice quality issue: unvowelled Arabic is ambiguous, so a more natural voice does not fix it.

## Proposal

Add a deterministic **Arabic diacritization pre-pass** as its own enhancement strategy (`diacritize_ar`), applied only to Arabic text and before the engine call, like the other strategies in `text_enhancer.py`.

- **Not the LLM strategy by default.** The on-device Qwen2.5-0.5B model is weak at Arabic vowelling and can change words, which breaks the rule that enhancement is presentation only. A dedicated diacritizer is more reliable. Candidates to evaluate: CAMeL Tools (strongest known, needs a local model), Mishkal / Tashkeel (rule-based, light), Shakkala or similar neural models. Prefer offline and local, to keep AlienVox's "no external calls" rule.
- **LLM as an optional second strategy**, validated the way speaker tags are: strip all diacritics from input and output; if the consonant skeleton differs, reject the result and fall back.
- **Pausal style by default**: full vowelling of stems without final case endings (i'rab), as in a normal voice-over. Make full i'rab optional.
- **Leave non-Arabic runs alone** (Latin words, numbers, URLs), and keep user-supplied diacritics.
- **Phrase overrides**: a per-project map for names and terms the diacritizer gets wrong (for example Hafs, Qaloun, Wajh, Tareeq).

## Acceptance

- Test set of Arabic sentences with a known-correct vowelling, starting with "كيف تستخدم" -> "كَيْفَ تَسْتَخْدِم" (must not become تُستخدم).
- Consonant skeleton is identical before and after for every test sentence.
- Works for both `python_app` and `alien_vox` (`speak.py --diacritize`), one implementation.
- Real synthesis comparison by ear on at least the test set, by an Arabic reader.

## Interim workaround

Hand-vowelled narration text per slide, stored with the project that needs it (Quran Research: `tools/qr-kit/narration_ar_vowelled.json`).
