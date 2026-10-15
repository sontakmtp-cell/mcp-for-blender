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
