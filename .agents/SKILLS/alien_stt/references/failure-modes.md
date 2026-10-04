# Failure modes

What goes wrong with speech recognition, how to recognise it, and what to do.
Add to this file when a new one is learned (strip the host's specifics first:
describe the mechanism, not the project).

## Text written over silence or music

**Looks like:** a confident short phrase ("Thank you.", "Subtitles by ...",
"Please subscribe") with nothing like it in the audio; often at the start, end or
in a gap.
**Why:** the model is trained to always produce text; on silence it falls back on
phrases common in its training data.
**Already handled:** the *silence guard* drops segments that lie (90%+) inside
audio quieter than -55 dBFS and records a warning (`dropped N segment(s) written
over silence`). The model's own no-speech check does not catch everything, which
a real test proved (8 s of exact silence produced "Thank you.").
**If it still happens:** raise `--no-speech-threshold`; if the phrase sits over
quiet but not silent audio, the guard cannot know, so the draft needs a listener.
Never "fix" it by editing the text without listening.

## Repetition loops

**Looks like:** the same sentence over and over, or a paragraph duplicated.
**Why:** the decoder gets stuck; feeding earlier text back in as a prompt makes
it much more likely, which is why this engine turns that off.
**Handled:** the temperature ladder re-decodes a failing window; consecutive
identical segments beyond two are collapsed.
**If it persists:** lower `--compression-ratio-threshold` (stricter), try
`--beam-size 5`, or switch model.

## Wrong language

**Looks like:** gibberish in the right script, text in the wrong script, or a
transcript that is translated when it should not be.
**Why:** detection looks only at the first 30 s and is weak on short clips,
accents, mixed languages, and leading music or silence.
**Do:** name the language with `--lang`. Run `detect_language.py` first when it is
unknown. The pipeline detects once and applies the result to the whole file, so one
wrong guess affects everything; it records a warning when the probability is under 60%.
**Code-switching** (two languages in one recording) is not handled well by any
single setting; expect errors where the speaker switches, and tell the user.

## Names, numbers, terms, spelling

**Looks like:** a name spelled three ways, digits versus words, an acronym
turned into a similar-sounding word.
**Do:** supply `--prompt "Name, Other Name, TermOfArt"`. A short list of real
terms helps; a long or unrelated prompt can hurt. Treat every number and name as
unverified.

## Recited or scripted text

Scripture, poetry, song lyrics, formal readings and quotations are recognised
by sound, not by knowing the text, and can come out subtly wrong or "normalised"
to ordinary speech. If the exact words matter, compare against the authoritative
written text; never publish the recognised text as a quotation.

## Empty output

**Check, in order:** does `probe_audio.py` show an audio stream and a plausible
duration? Is the language right? Is the recording actually quiet (level below
about -40 dBFS everywhere)? Is the warning "no speech was detected" present? A
very quiet recording can be amplified first:
`ffmpeg -i in.wav -af loudnorm out.wav` (the original is untouched).

## Cut-off or missing words at chunk boundaries

Files longer than `--chunk-minutes` are cut in the widest quiet gaps, but a
recording with no gaps (continuous speech or music) gets a hard cut that can
split a word; the transcript then carries the warning "processed in N chunks".
Raise `--chunk-minutes` if memory allows, or accept and check the boundaries.

## Timestamps drifting or odd

Times come from the model's own timing per segment; they are good to about a
second, not frame accurate. Subtitles may start slightly early or late. For
frame-accurate subtitle work a forced aligner is needed (see the roadmap).

## Operational

| Symptom | Cause | Fix |
|---|---|---|
| `ffmpeg not found` | not installed or not on PATH | install ffmpeg; or set `FFMPEG`/`FFPROBE` to the full paths |
| `has no audio stream` | video without sound, or not media | check with `probe_audio.py` |
| CUDA out of memory | model too large for the GPU, or a very long chunk | `--model turbo` or `medium`, lower `--chunk-minutes`, or `--device cpu` |
| Very slow | running a large model on the CPU | use a GPU, or `--model small`/`turbo` |
| First run hangs for minutes | downloading model weights | wait; check the network; weights cache afterwards |
| `cannot reach huggingface.co` offline | model not cached | run once online, or copy the model folder and pass its path |
| Ogg conversion "encoder setup failed" | a fixed bitrate Vorbis cannot do at that sample rate | handled: Ogg uses a quality level by default; avoid forcing `--bitrate` for `.ogg` |
| Arabic/CJK shows as `?` in a console | legacy console code page | the scripts force UTF-8; use a UTF-8 terminal, or read the output files |
| `unauthenticated requests to the HF Hub` | a harmless notice | set `HF_TOKEN` to silence it, or ignore it |
