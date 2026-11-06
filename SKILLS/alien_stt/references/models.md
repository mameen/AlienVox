# Choosing a model

`--model` accepts an alias from the table, any Hugging Face id (`org/name`), or a
path to a local folder holding a Whisper model. Aliases are defined in
`alienstt/engines/whisper_hf.py` (`MODEL_ALIASES`); that file wins if this table
and the code ever disagree.

| Alias | Hugging Face id | Languages | Rough size | When |
|---|---|---|---|---|
| `large-v3` (default) | `openai/whisper-large-v3` | ~100 | ~3 GB | Best accuracy; the default for anything that will be read or quoted |
| `turbo` / `large-v3-turbo` | `openai/whisper-large-v3-turbo` | ~100 | ~1.6 GB | Several times faster than large-v3 with a small accuracy loss; the loss is larger on non-English and noisy speech |
| `large-v2` | `openai/whisper-large-v2` | ~100 | ~3 GB | A fallback if large-v3 misbehaves on a particular recording |
| `medium` | `openai/whisper-medium` | ~100 | ~1.5 GB | A middle ground when GPU memory is tight |
| `small` | `openai/whisper-small` | ~100 | ~0.5 GB | Quick drafts |
| `base`, `tiny` | `openai/whisper-base`, `-tiny` | ~100 | 0.15 GB, 0.08 GB | Language detection, smoke tests; poor for real transcription of difficult audio |
| `*.en` (`medium.en`, `small.en`, `base.en`, `tiny.en`) | `openai/whisper-*.en` | English only | as above | English-only audio; a little better than the multilingual model of the same size. Cannot detect or transcribe other languages |
| `distil-large-v3` | `distil-whisper/distil-large-v3` | English only | ~1.5 GB | Fast English transcription |

Sizes are approximate download sizes and change between releases; treat them as
order of magnitude.

## Speed and hardware

- **GPU** (CUDA): the default when one is really present (`--device auto`).
  large-v3 in fp16 needs roughly 4-6 GB of GPU memory. It processes an hour of
  speech in minutes.
- **CPU**: works with every model but large models are slow (often slower than
  real time). Prefer `small`/`base` or `turbo` on a CPU, and say `--device cpu`
  explicitly if you must keep a GPU free.
- Speed also depends on `--beam-size` (1 is greedy and fastest) and on how often
  the temperature ladder has to retry a difficult window.

## Accuracy, honestly

Accuracy differs by language, accent, microphone, background noise and subject.
English studio-quality speech is very good; low-resource languages, dialects,
overlapping speakers, music and phone-quality audio are noticeably worse. Names,
numbers, acronyms and technical terms are the usual errors, and `--prompt` helps
with spelling but does not guarantee it. This is why every transcript is labelled
as an unchecked draft. If a language matters a great deal, test two models on a
short real sample before committing a large batch.

## Where models live, and going offline

Weights are cached by Hugging Face (`HF_HOME`, default `~/.cache/huggingface`).
The first use of a model downloads it; after that it is read from the cache.
`python scripts/check_setup.py --model NAME` says whether it is cached. To forbid
all network access once cached, set `HF_HUB_OFFLINE=1`. To use a model from a
folder you copied by hand, pass the folder path to `--model`.

Check a model's own licence before redistributing weights or building a product
on it; this skill records no licence terms for third-party models.
