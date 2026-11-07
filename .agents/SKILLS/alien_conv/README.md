# Alien Conversation audio bridge

The primary runner connects local microphone/STT/SAPI audio to the calling host. The host reads the transcript, generates the conversational reply, and sends that text back for local speech. The primary runner does not call Ollama.

## Install

From the repository root in PowerShell:

```powershell
.\.agents\SKILLS\alien_conv\scripts\setup.ps1
```

Setup uses this skill's `.venv` and installs one combined requirements file for the bridge, manual chat, copied STT/TTS utilities, and Pipecat POC. It does not search for or reuse another Python environment. The runner reuses the existing faster-whisper cache when possible and does not download weights unless `--allow-model-download` is explicitly passed. For CUDA transcription, faster-whisper requires compatible NVIDIA cuBLAS and cuDNN runtime libraries on `PATH`; CPU fallback is available with `--device cpu --compute-type int8`. See [faster-whisper GPU setup](https://github.com/SYSTRAN/faster-whisper#gpu). The shared environment is larger than a bridge-only environment because it includes PyTorch, Transformers, Pipecat, Piper, Kokoro, and the terminal UI.

## Run the bridge

Start the process with persistent stdin/stdout handles and capture stderr separately. Prefer a subprocess with three redirected streams so protocol and diagnostic output never share the host's user-facing console. If only an interactive terminal is available, dedicate a separate pane to this process.

```powershell
.\.agents\SKILLS\alien_conv\.venv\Scripts\python.exe .\.agents\SKILLS\alien_conv\scripts\alien_conv.py --tts-voice zira
```

Stdout is UTF-8 JSON Lines only; consume it internally and do not show raw JSON to the user. Stderr carries diagnostics. The process speaks a startup greeting and then emits a `ready` event. Keep the session open and send stdin commands as JSON Lines, using a JSON serializer for the response text:

```jsonl
{"command":"listen"}
{"command":"speak","text":"Hi! What can I help you with?"}
{"command":"stop"}
```

After `listen`, the process records until speech is followed by silence and emits a transcript event, for example:

```json
{"event":"transcript","text":"Can you hear me?","language":"en"}
```

The host must read each `transcript` event as the user's actual message, answer it in the host conversation, then send that response using `speak`. Wait for the `spoken` event before starting another listen turn. The host—not the user—operates stdin and is responsible for carrying the conversation; do not leave the transcript unanswered or ask the user to type the reply into the console. If the transcript is exactly `exit`, send `stop`.

Useful options:

- `--input-device INDEX_OR_NAME` selects a microphone.
- `--language en` sets the spoken language; `auto` enables detection.
- `--silence-seconds 1.0` sets end-of-speech silence duration.
- `--max-seconds 30` caps each recording.
- `--list-audio-devices` and `--list-voices` print machine-readable JSON and exit.
- `--allow-model-download` explicitly permits downloading missing Whisper weights.

Audio is processed locally. Transcript text is intentionally sent to the calling host through stdout, where the host's model and privacy behavior apply. The bridge does not save audio or transcript files.

## Manual local conversation test

For interactive testing without a host or MCP, run `local_test.py` after the single setup step above:

```powershell
.\.agents\SKILLS\alien_conv\.venv\Scripts\python.exe .\.agents\SKILLS\alien_conv\scripts\local_test.py --model gemma4:12b --input-device 1 --tts-engine sapi5 --tts-voice TTS_MS_EN-US_ZIRA_11.0
```

It shows scrollable conversation history above a fixed chat input. After the startup greeting, the first microphone turn starts automatically and ends after a pause. Listening resumes automatically after each spoken reply; enter `/listen` to restart if a turn times out or returns to text mode. You can type a message and press Enter at any time. Typing `/` shows command suggestions; use Up/Down or Tab to select one. Enter fills the suggestion; press Enter again to run it. Use PgUp/PgDn to scroll history and `/quit` to exit. Saying `exit` as the complete mic transcription also exits. The POC-style `--model`, `--input-device`, `--stt-model`, `--tts-engine`, and `--tts-voice` options remain available.

It defaults to SAPI5/Zira and uses the existing cached `large-v3-turbo` Whisper model. Piper or Kokoro can be selected with `--tts-engine`; their packages are included in the combined requirements. This manual runner calls Ollama at `localhost`; the primary `alien_conv.py` bridge remains host-driven and does not call Ollama.

The two-line status bar includes a colored activity LED: green means microphone capture, yellow means transcription or LLM processing, red means TTS playback, and blue means idle/text entry. Listening automatically resumes after each spoken reply. This simple loop belongs to `local_test.py`; the separate Pipecat experiment has its own pipeline and turn handling.

## Bundled standalone utilities

All bundled utilities use the same skill `.venv` and combined requirements. They reuse the existing Hugging Face cache and AlienVox development voice models when available. File transcription also needs `ffmpeg` and `ffprobe` on `PATH` for formats beyond WAV.

### File transcription

`scripts/transcribe.py` transcribes files using the copied `alienstt` package. It is separate from the microphone bridge.

```powershell
.\.agents\SKILLS\alien_conv\.venv\Scripts\python.exe .\.agents\SKILLS\alien_conv\scripts\transcribe.py recording.mp3 --lang en
```

### Local text to speech

`scripts/speak.py` generates and plays speech using local Piper (default) or Kokoro. Piper uses AlienVox's existing development model directory when available; it does not expose the networked Edge engine.

```powershell
.\.agents\SKILLS\alien_conv\.venv\Scripts\python.exe .\.agents\SKILLS\alien_conv\scripts\speak.py "Hello from Alien Conversation" --engine piper
```

### Pipecat pipeline POC

`scripts/pipecat_conv.py` remains a separate local pipeline experiment using Pipecat, Whisper, local Ollama, and Piper or Windows SAPI. It is not used by the primary host-driven bridge. The SAPI adapter is copied into this skill; Pipecat and its audio dependencies are included in the combined requirements.

```powershell
.\.agents\SKILLS\alien_conv\.venv\Scripts\python.exe .\.agents\SKILLS\alien_conv\scripts\pipecat_conv.py --list-devices
```

See [`SKILL.md`](SKILL.md) for host interaction rules and [`AGENTS.md`](AGENTS.md) for maintenance notes. This skill is intentionally stored under `.agents/SKILLS/` and should only be used when explicitly requested.
