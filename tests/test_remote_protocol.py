"""Real subprocess transports, SDK traffic, and a deliberately offline Blender."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client


@pytest.fixture
def remote_env(tmp_path):
    # Keep credentials out of both subprocesses and pytest failure diagnostics.
    env = {"DISABLE_TELEMETRY": "true", "XDG_CACHE_HOME": str(tmp_path),
           "XDG_CONFIG_HOME": str(tmp_path)}
    if "SYSTEMROOT" in os.environ:
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


@pytest.fixture
def http_server(tmp_path, remote_env, request):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}/mcp"
    blender_port = request.getfixturevalue("fake_blender") if getattr(request, "param", None) == "fake_blender" else 1
    log = (tmp_path / "server.log").open("w+")
    proc = subprocess.Popen([
        sys.executable, "-c", "from blender_mcp.server import main; main()",
        "--transport", "streamable-http", "--http-port", str(port), "--port", str(blender_port),
        "--local-test",
    ], env=remote_env, stdout=log, stderr=log)
    try:
        for _ in range(100):
            if proc.poll() is not None:
                log.seek(0)
                pytest.fail(log.read())
            try:
                if httpx.get(url, timeout=0.1, trust_env=False).status_code in (405, 406):
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        else:
            pytest.fail("HTTP server did not become ready")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        log.close()


async def exercise(read, write, remote=False):
    async with ClientSession(read, write) as session:
        initialized = await session.initialize()
        assert initialized.serverInfo.name == "MCP for Blender"
        tools = await session.list_tools()
        names = {t.name for t in tools.tools}
        assert {"get_addon_status", "get_scene_info", "look"} <= names
        if remote:
            assert names == {"get_addon_status", "get_scene_info", "look"}
            denied = await session.call_tool("execute_blender_code", {"code": "print('MUST_NOT_RUN')"})
            assert denied.isError
            assert "not allowed" in denied.content[0].text
        else:
            assert "execute_blender_code" in names
        # The process is intentionally pointed at a closed loopback port.
        result = await session.call_tool("get_scene_info", {})
        assert "Error getting scene info" in result.content[0].text
        assert "Blender" in result.content[0].text


def test_streamable_http_real_protocol_and_blender_offline(http_server):
    async def run():
        async with asyncio.timeout(15):
            async with httpx.AsyncClient(trust_env=False) as client:
                async with streamable_http_client(http_server, http_client=client) as (read, write, _):
                    await exercise(read, write, remote=True)
    asyncio.run(run())


def test_stdio_real_protocol_still_works(remote_env):
    async def run():
        async with asyncio.timeout(15):
            params = StdioServerParameters(command=sys.executable,
                args=["-c", "from blender_mcp.server import main; main()", "--port", "1"], env=remote_env)
            async with stdio_client(params) as (read, write):
                await exercise(read, write)
    asyncio.run(run())


def test_remote_rejects_oversized_request_and_wrong_host(http_server):
    with httpx.Client(trust_env=False, timeout=5) as client:
        response = client.post(http_server, content=b"x" * (1024 * 1024 + 1),
                               headers={"Content-Type": "application/json"})
        assert response.status_code == 413
        response = client.post(http_server, json={}, headers={"Host": "attacker.example"})
        assert response.status_code == 421


@pytest.fixture
def fake_blender():
    """Real TCP addon protocol, enough to force script/fallback traffic."""
    import json
    import threading
    stop = threading.Event()
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    listener.settimeout(0.1)
    port = listener.getsockname()[1]

    def serve():
        while not stop.is_set():
            try:
                conn, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with conn:
                conn.settimeout(0.1)
                data = b""
                while not stop.is_set():
                    try:
                        chunk = conn.recv(65536)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    data += chunk
                    try:
                        command = json.loads(data)
                    except ValueError:
                        continue
                    data = b""
                    result = {"name": "test scene"}
                    if command["type"] == "get_addon_info":
                        result = {"protocol_version": 13, "addon_version": [1, 8], "capabilities": []}
                    conn.sendall(json.dumps({"status": "success", "result": result}).encode())

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        stop.set()
        thread.join(timeout=2)
        listener.close()


@pytest.mark.parametrize("http_server", ["fake_blender"], indirect=True)
def test_remote_does_not_log_python_payload(http_server, tmp_path):
    async def run():
        async with httpx.AsyncClient(trust_env=False) as client:
            async with streamable_http_client(http_server, http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("get_scene_info", {"query": "PRIVATE_QUERY_SENTINEL"})
                    assert "test scene" in result.content[0].text
    asyncio.run(run())
    assert "PRIVATE_QUERY_SENTINEL" not in (tmp_path / "server.log").read_text()
