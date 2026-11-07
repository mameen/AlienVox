"""JSONL host adapter for Alien Conversation's local FastAPI session.

The client relays session events from HTTP to stdout and forwards host commands
from stdin to the API. This lets the skill retain a simple persistent
stdin/stdout process contract while the visible local_test console shows the
same transcript, host reply, and activity state.

Use --mode start to launch local_test.py in a new visible console and attach to
its localhost API. Use --mode connect --url URL to attach to a console that is
already running. The host sends JSONL commands: status, speak, listen, stop.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 5,
) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8")).get("detail", str(exc))
        except (UnicodeDecodeError, json.JSONDecodeError):
            detail = str(exc)
        raise RuntimeError(f"Session API returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not reach session API at {base_url}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError("Session API returned an invalid JSON object")
    return value


def emit(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, ensure_ascii=False), flush=True)


def start_console(args: argparse.Namespace, url: str) -> subprocess.Popen[Any]:
    local_test = SCRIPT_DIR / "local_test.py"
    command = [
        sys.executable,
        str(local_test),
        "--mode", "api-server",
        "--api-host", args.api_host,
        "--api-port", str(args.port),
        "--stt-model", args.stt_model,
        "--device", args.device,
        "--compute-type", args.compute_type,
        "--language", args.language,
        "--max-seconds", str(args.max_seconds),
        "--silence-seconds", str(args.silence_seconds),
        "--start-timeout", str(args.start_timeout),
        "--vad-threshold", str(args.vad_threshold),
        "--tts-engine", args.tts_engine,
        "--tts-device", args.tts_device,
    ]
    if args.token:
        command.extend(("--api-token", args.token))
    if args.input_device is not None:
        command.extend(("--input-device", str(args.input_device)))
    if args.tts_voice:
        command.extend(("--tts-voice", args.tts_voice))
    if os.name == "nt":
        return subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_CONSOLE)
    return subprocess.Popen(command)


def wait_for_server(args: argparse.Namespace, url: str, child: subprocess.Popen[Any] | None) -> None:
    deadline = time.monotonic() + args.startup_timeout
    last_error = "not ready yet"
    while time.monotonic() < deadline:
        if child is not None and child.poll() is not None:
            raise RuntimeError(f"Alien Conversation console exited with code {child.returncode}")
        try:
            request_json(url, "/v1/health", token=args.token, timeout=2)
            return
        except RuntimeError as exc:
            last_error = str(exc)
            time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for Alien Conversation at {url}: {last_error}")


def read_commands(commands: queue.Queue[str | None], stop: threading.Event) -> None:
    try:
        for line in sys.stdin:
            if stop.is_set():
                break
            commands.put(line)
    finally:
        commands.put(None)


def handle_command(command: dict[str, Any], *, url: str, token: str | None) -> bool:
    action = command.get("command")
    if action == "speak":
        text = command.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("speak command requires nonempty text")
        request_json(url, "/v1/reply", method="POST", payload={"text": text}, token=token)
        return True
    if action == "status":
        phase = command.get("phase", "thinking")
        message = command.get("message", "")
        request_json(
            url,
            "/v1/status",
            method="POST",
            payload={"phase": phase, "message": message},
            token=token,
        )
        return True
    if action == "listen":
        request_json(url, "/v1/listen", method="POST", payload={}, token=token)
        return True
    if action == "stop":
        request_json(url, "/v1/stop", method="POST", payload={}, token=token)
        emit("stopped")
        return False
    raise ValueError(f"Unknown command: {action!r}")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Connect the Alien Conversation skill host to its local session API")
    parser.add_argument("--mode", choices=("start", "connect"), default="connect", help="start a visible console or attach to an existing session")
    parser.add_argument("--url", help="running session base URL, e.g. http://127.0.0.1:8765")
    parser.add_argument("--token", help="optional API Bearer token")
    parser.add_argument("--port", type=int, default=8765, help="API port when --mode start is used")
    parser.add_argument("--api-host", default="127.0.0.1", help="bind host when --mode start is used")
    parser.add_argument("--input-device", help="microphone device index or name for a newly started console")
    parser.add_argument("--stt-model", default="large-v3-turbo")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="cuda")
    parser.add_argument("--compute-type", default="float16")
    parser.add_argument("--language", default="en", help="spoken language code, or auto")
    parser.add_argument("--max-seconds", type=float, default=30)
    parser.add_argument("--silence-seconds", type=float, default=1.0)
    parser.add_argument("--start-timeout", type=float, default=10)
    parser.add_argument("--vad-threshold", type=float, default=0.012)
    parser.add_argument("--tts-engine", choices=("sapi5", "piper", "kokoro"), default="sapi5")
    parser.add_argument("--tts-voice")
    parser.add_argument("--tts-device", choices=("cpu", "gpu"), default="cpu")
    parser.add_argument("--startup-timeout", type=float, default=180)
    return parser


def main() -> int:
    args = make_parser().parse_args()
    child: subprocess.Popen[Any] | None = None
    try:
        if args.mode == "start":
            if args.url:
                raise ValueError("Use --port instead of --url with --mode start")
            if not 1 <= args.port <= 65535:
                raise ValueError("--port must be between 1 and 65535")
            if args.api_host.casefold() not in {"127.0.0.1", "localhost", "::1"} and not args.token:
                raise ValueError("Binding beyond localhost requires --token")
            url = f"http://127.0.0.1:{args.port}"
            child = start_console(args, url)
        else:
            if not args.url:
                raise ValueError("--url is required with --mode connect")
            url = args.url.rstrip("/")
            parsed = urllib.parse.urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("--url must be an HTTP(S) base URL")

        wait_for_server(args, url, child)
        commands: queue.Queue[str | None] = queue.Queue()
        stop = threading.Event()
        command_thread = threading.Thread(target=read_commands, args=(commands, stop), daemon=True)
        command_thread.start()

        failures = 0
        while not stop.is_set():
            try:
                raw_command = commands.get_nowait()
            except queue.Empty:
                raw_command = ...
            if raw_command is None:
                break
            if raw_command is not ...:
                try:
                    command = json.loads(raw_command)
                    if not isinstance(command, dict):
                        raise ValueError("stdin command must be a JSON object")
                    if not handle_command(command, url=url, token=args.token):
                        break
                except (json.JSONDecodeError, ValueError, RuntimeError) as exc:
                    emit("error", message=str(exc))
                continue

            try:
                event = request_json(url, "/v1/events?timeout=1", token=args.token, timeout=3)
                failures = 0
                if event.get("event") != "heartbeat":
                    event_name = str(event.pop("event", "unknown"))
                    emit(event_name, **event)
                    if event_name == "stopped":
                        break
            except RuntimeError as exc:
                emit("error", message=str(exc))
                failures += 1
                if failures >= 3:
                    emit("disconnected", url=url)
                    break
                time.sleep(0.5)
        stop.set()
        return 0
    except KeyboardInterrupt:
        if child is not None and child.poll() is None:
            try:
                request_json(f"http://127.0.0.1:{args.port}", "/v1/stop", method="POST", payload={}, token=args.token, timeout=2)
            except RuntimeError:
                pass
        return 0
    except Exception as exc:
        emit("error", message=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
