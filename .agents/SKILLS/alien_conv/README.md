# Alien Conversation audio bridge

The primary runner connects local microphone/STT/SAPI audio to the calling host. The host reads the transcript, generates the conversational reply, and sends that text back for local speech. The primary runner does not call Ollama.

## Install

From the repository root in PowerShell:

```powershell
.\.agents\SKILLS\alien_conv\scripts\setup.ps1
```

To preserve an existing venv created with another Python version, select a new skill-local environment name, such as `-VenvName .venv312`. Create it first with `py -3.12 -m venv .agents\SKILLS\alien_conv\.venv312`, then run setup with the same `-VenvName` and launch `api_client.py` with that environment's `Scripts\python.exe`.

Setup uses this skill's `.venv` and installs one combined requirements file for the bridge, manual chat, copied STT/TTS utilities, and Pipecat POC. It does not search for or reuse another Python environment. The requirements use NumPy 2.x on Python 3.13 because NumPy 1.x has no CPython 3.13 wheels. Kokoro's published package is installed on Python 3.10–3.12; Python 3.13 sessions can use SAPI or Piper without attempting an unverified Kokoro source build. The runner reuses the existing faster-whisper cache when possible and does not download Whisper weights unless `--allow-model-download` is explicitly passed. For CUDA transcription, faster-whisper requires compatible NVIDIA cuBLAS and cuDNN runtime libraries on `PATH`; CPU fallback is available with `--device cpu --compute-type int8`. See [faster-whisper GPU setup](https://github.com/SYSTRAN/faster-whisper#gpu). The shared environment is larger than a bridge-only environment because it includes PyTorch, Transformers, Pipecat, Piper, Kokoro where supported, and the terminal UI.

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

## Host-driven session over a local API

`local_test.py --mode api-server` runs the visible chat console, microphone capture, local Whisper, local TTS, and a FastAPI session API. It does not call Ollama in this mode. The host uses `api_client.py` as a persistent JSONL process: transcript and status events arrive on stdout, and host replies/status commands go to stdin. The console shows both sides of the conversation and the current activity; its title displays the session URL to copy to the host. The `ready` event also includes the URL.

### Start a new visible console and attach the host

```powershell
.\.agents\SKILLS\alien_conv\.venv\Scripts\python.exe .\.agents\SKILLS\alien_conv\scripts\local_test.py --mode api-server --api-host 127.0.0.1 --api-port 8765 --input-device 1 --stt-model large-v3-turbo --device cuda --compute-type float16 --tts-engine sapi5 --tts-voice TTS_MS_EN-US_ZIRA_11.0
```

This runs the interactive console and embedded API in the current terminal. Its title shows `http://127.0.0.1:8765`; the API emits `ready` with the same URL after the greeting. The host attaches using `api_client.py --mode connect --url http://127.0.0.1:8765`. Press Ctrl+C or use `/quit` to stop the console and API server cleanly. The host sends serialized JSONL commands to that client such as:

```jsonl
{"command":"status","phase":"thinking","message":"Preparing a reply"}
{"command":"speak","text":"Hello! I heard you."}
{"command":"stop"}
```

Listening resumes automatically after speech. The local console briefly shows a separate cyan `API: STATUS`, `API: REPLY`, or `API: LISTEN` indicator when it receives a host command; the main LED continues to show listening, transcription, or speech. The host should relay `listening`, `transcript`, `speaking`, `spoken`, errors, and stop state to the user in its normal response channel.

For direct HTTP clients, send JSON objects with these bodies (the API client translates the equivalent JSONL commands automatically):

```http
POST /v1/status
Content-Type: application/json

{"phase":"thinking","message":"Preparing a reply"}

POST /v1/reply
Content-Type: application/json

{"text":"Hello! I heard you."}
```

Both fields are request bodies, not query parameters. Keep their Pydantic request models at module scope in `local_test.py`; with postponed annotations, nested request models are not resolved by FastAPI and can produce `422 query.body missing`.

### Connect to a console that is already running

First start the console in a terminal:

```powershell
.\.agents\SKILLS\alien_conv\.venv\Scripts\python.exe .\.agents\SKILLS\alien_conv\scripts\local_test.py --mode api-server --api-host 127.0.0.1 --api-port 8765 --input-device 1 --stt-model large-v3-turbo --device cuda --compute-type float16 --tts-engine sapi5 --tts-voice TTS_MS_EN-US_ZIRA_11.0
```

Then launch the persistent host adapter and attach it:

```powershell
.\.agents\SKILLS\alien_conv\.venv\Scripts\python.exe .\.agents\SKILLS\alien_conv\scripts\api_client.py --mode connect --url http://127.0.0.1:8765
```

For a non-loopback bind, pass the same `--api-token SECRET` to the console and `--token SECRET` to the client. Non-loopback binding without a token is rejected. Prefer localhost for local use.
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
