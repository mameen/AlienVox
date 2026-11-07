# Alien Conversation maintenance notes

- This folder is self-contained: the runner and optional utilities use the vendored `alienstt` and `alienvox_tts` packages and do not require another repository's Python package or an AlienVox MCP server.
- Use one shared `scripts/requirements.txt` for the bridge, manual chat, copied STT/TTS tools, and Pipecat POC; keep it in sync with the setup instructions.
- Preserve the primary runner's UTF-8 JSONL stdin/stdout protocol. Stdout is protocol-only; diagnostics belong on stderr.
- Keep `scripts/local_test.py` as the separate, manually run Ollama-backed conversational test; don't add Ollama back to the primary host-driven bridge.
- Keep the manual runner's scrollable history and fixed input line intact; update `scripts/requirements.txt` and the README if the terminal UI changes.
- Reuse existing model caches where available. Do not trigger model downloads unless the client explicitly opts in.
- Keep audio capture local. Transcript text intentionally crosses to the calling host; do not claim it stays in the local process or machine.
- Do not persist microphone audio or transcripts by default. Do not execute model-produced text as shell commands or code.
- Read the relevant scripts and docs before editing. Do not run tests unless requested.
