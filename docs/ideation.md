# Ideation — Future Ideas To Explore

**Updated:** 2026-08-28

A running list of things worth investigating for AlienVox (the app, the `alien_vox` skill, and/or
`python_mcp_server`) that aren't scoped or committed to yet — no implementation decision has been
made on anything below. When an idea gets real investigation, promote it: a model candidate goes to
[`docs/SOTA_models.md`](SOTA_models.md), a concrete implementation plan goes to
`python_app/docs/issues/todo_NNN_<slug>.md` (see that folder's existing entries for the format).

---

## Fish Audio S1/S2-Pro

**Link:** https://huggingface.co/fishaudio/s2-pro

A newer TTS model from Fish Audio. Not yet evaluated against this project's constraints (free/local
fit, license, model size, quality vs. Kokoro/Chatterbox/F5-TTS). Worth a look alongside the existing
candidates in `docs/SOTA_models.md`'s decision table.

## Google Cloud TTS / Gemini Live API

**Video:** https://www.youtube.com/watch?v=pFc-HcUgFgY (feat. Annie — LinkedIn: https://goo.gle/annie-linkedin, X: https://goo.gle/annie-x)

Resources referenced in the video:
- Code for the episode: https://g.dev/cloud/voicedemo1
- Gemini Live API docs: https://g.dev/cloud/gemini-live
- Roadmap preview: https://g.dev/cloud/mma-roadmap
- Agent Development Kit (ADK) docs: https://g.dev/cloud/adk-docs

Cloud, not local — conflicts with this project's local-first constraint (see `SOTA_models.md`'s
`Decision Summary`, which already lists "Gemini TTS / ElevenLabs / OpenAI TTS" as "Optional demo
only", not a default engine). Still worth investigating for: (a) the Gemini **Live** API
specifically, which is bidirectional/streaming rather than one-shot TTS — a different shape than
anything currently in AlienVox — and (b) whether the ADK has anything reusable for AlienVox's own
MCP server design, independent of actually shipping Gemini as a voice.

## Scriberr — bi-directional TTS/STT

**Link:** https://github.com/mameen/Scriberr

AlienVox (app, skill, and MCP server) is TTS-only today — speech-to-text is explicitly out of scope
everywhere it's currently documented (see `alien_vox`'s `SKILL.md`: "Not for speech-to-text/
transcription requests"). Scriberr looks like a candidate for the STT half of a bi-directional
story — worth investigating as a *separate* capability/surface rather than folding STT into the
existing TTS-only skill and MCP server, given how deliberately scoped those are today.
