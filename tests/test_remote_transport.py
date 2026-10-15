"""Transport contract, independent of Blender UI and external services."""
import sys
from unittest.mock import Mock

import pytest

from blender_mcp import server
from blender_mcp.remote import configure_http, parse_transport_args


def test_transport_flags_leave_blender_address_unchanged():
    args, rest = parse_transport_args([
        "--host", "localhost", "--port", "9877", "--transport", "streamable-http",
        "--http-port", "8766",
    ])
    assert server.parse_connection_args(rest) == ("localhost", 9877)
    assert args.http_port == 8766
    assert args.http_host == "127.0.0.1"


@pytest.mark.parametrize("argv", [
    ["--http-host", "0.0.0.0"], ["--http-host", "::"],
    ["--http-port", "0"], ["--http-port", "65536"], ["--transport", "sse"],
])
def test_invalid_or_public_transport_is_rejected(argv):
    with pytest.raises(SystemExit):
        parse_transport_args(argv)


def test_defaults_still_run_stdio(monkeypatch):
    run = Mock()
    monkeypatch.setattr(server.mcp, "run", run)
    monkeypatch.setattr(sys, "argv", ["mcp-for-blender"])
    server.main()
    run.assert_called_once_with()


def test_same_server_is_configured_not_replaced():
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("test")
    args, _ = parse_transport_args(["--transport", "streamable-http"])
    configure_http(mcp, args)
    assert mcp.settings.host == "127.0.0.1"
    assert mcp.settings.stateless_http
    assert mcp.settings.streamable_http_path == "/mcp"
    assert mcp.settings.max_request_body_size == 1024 * 1024
    assert mcp.settings.transport_security.enable_dns_rebinding_protection


def test_socket_exchange_is_serialized():
    import concurrent.futures
    import json
    import socket
    import threading
    left, right = socket.socketpair()
    connection = server.BlenderConnection("localhost", 9876, sock=left)

    def addon():
        for _ in range(2):
            request = json.loads(right.recv(8192))
            right.sendall(json.dumps({"status": "success", "result": request["params"]}).encode())

    thread = threading.Thread(target=addon)
    thread.start()
    try:
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(connection.send_command, "echo", {"id": n}) for n in range(2)]
            assert [f.result(timeout=5) for f in futures] == [{"id": 0}, {"id": 1}]
    finally:
        left.close()
        right.close()
        thread.join(timeout=5)


def test_first_connection_is_created_once(monkeypatch):
    import concurrent.futures
    import time
    monkeypatch.setattr(server, "_blender_connection", None)
    monkeypatch.setattr(server, "_maybe_handshake_addon", lambda conn: None)
    created = []

    def connect(conn):
        time.sleep(0.03)
        created.append(conn)
        conn.sock = object()
        return True

    monkeypatch.setattr(server.BlenderConnection, "connect", connect)
    with concurrent.futures.ThreadPoolExecutor(2) as pool:
        connections = list(pool.map(lambda _: server.get_blender_connection(), range(2)))
    assert connections[0] is connections[1]
    assert len(created) == 1


def test_remote_connection_has_bounded_connect_timeout(monkeypatch):
    import socket
    sock = Mock()
    monkeypatch.setattr(server, "REMOTE_MODE", True)
    monkeypatch.setattr(socket, "socket", Mock(return_value=sock))
    conn = server.BlenderConnection("127.0.0.1", 1)
    assert conn.connect()
    sock.settimeout.assert_called_with(5.0)


def test_stateless_requests_do_not_close_process_lifespan():
    from contextlib import asynccontextmanager
    from mcp.server.fastmcp import FastMCP
    from starlette.testclient import TestClient
    from blender_mcp.remote import process_http_app
    events = []

    @asynccontextmanager
    async def lifespan(_):
        events.append("start")
        yield {}
        events.append("stop")

    mcp = FastMCP("test", lifespan=lifespan)
    args, _ = parse_transport_args([])
    configure_http(mcp, args)
    with TestClient(process_http_app(mcp), base_url="http://127.0.0.1:8765") as client:
        for _ in range(2):
            client.get("/mcp")
            assert events == ["start"]
    assert events == ["start", "stop"]


def test_remote_response_size_and_timeout_are_bounded(monkeypatch):
    import socket
    monkeypatch.setattr(server, "REMOTE_MODE", True)
    monkeypatch.setattr(server, "REMOTE_RESPONSE_LIMIT", 8)
    sock = Mock()
    sock.recv.return_value = b"123456789"
    conn = server.BlenderConnection("127.0.0.1", 9876, sock=sock)
    with pytest.raises(ValueError, match="32 MiB"):
        conn.receive_full_response(sock)
    sock.recv.side_effect = socket.timeout()
    with pytest.raises(socket.timeout):
        conn.receive_full_response(sock)


def test_remote_requires_config_unless_explicit_local_test(monkeypatch):
    from blender_mcp.remote import run_http
    for name in ("GOODMCP_ACCESS_TEAM_DOMAIN", "GOODMCP_ACCESS_AUD", "GOODMCP_ALLOWED_EMAIL", "GOODMCP_PUBLIC_URL"):
        monkeypatch.delenv(name, raising=False)
    args, _ = parse_transport_args(["--transport", "streamable-http"])
    with pytest.raises(ValueError, match="TEAM_DOMAIN"):
        run_http(server.mcp, args)


def test_remote_forces_safe_mode_and_disables_sensitive_logs(monkeypatch):
    from mcp.server.fastmcp import FastMCP
    from blender_mcp.remote import run_http
    import uvicorn
    import logging
    monkeypatch.setattr(server, "CLI_HOST", "127.0.0.1")
    logger = logging.getLogger("BlenderMCPServer")
    monkeypatch.setattr(logger, "disabled", False)
    monkeypatch.setenv("BLENDER_MCP_SAFE_MODE", "0")
    monkeypatch.setenv("DISABLE_TELEMETRY", "false")
    monkeypatch.setenv("BLENDER_MCP_CONTEXT_LOG", "1")
    run = Mock()
    monkeypatch.setattr(uvicorn, "run", run)
    args, _ = parse_transport_args(["--transport", "streamable-http", "--local-test"])
    run_http(FastMCP("test"), args)
    import os
    assert os.environ["BLENDER_MCP_SAFE_MODE"] == "1"
    assert os.environ["DISABLE_TELEMETRY"] == "true"
    assert os.environ["BLENDER_MCP_CONTEXT_LOG"] == "0"
    assert logger.disabled
    assert run.call_args.kwargs["proxy_headers"] is False
    assert run.call_args.kwargs["access_log"] is False
    # Uvicorn's default dictConfig re-enables disabled loggers, including the
    # upstream logger that logs Python payloads.
    assert run.call_args.kwargs["log_config"] is None
