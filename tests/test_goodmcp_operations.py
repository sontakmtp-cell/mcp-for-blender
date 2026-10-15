"""Operator safety gates and cleanup, without credentials or a real Tunnel."""
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock, MagicMock

import httpx
import pytest

from blender_mcp import goodmcp


def tunnel_file(tmp_path, service="http://127.0.0.1:8765"):
    credential = tmp_path / "credential.json"
    credential.write_text("{}")
    config = {"tunnel": "00000000-0000-4000-8000-000000000001", "credentials-file": str(credential),
              "ingress": [{"hostname": "mcp.example.com", "service": service}, {"service": "http_status:404"}]}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    return path


def test_valid_named_tunnel_targets_only_http_origin(tmp_path):
    goodmcp.validate_tunnel_config(tunnel_file(tmp_path), "https://mcp.example.com/mcp")


@pytest.mark.parametrize("service", ["tcp://127.0.0.1:9876", "http://127.0.0.1:9876", "http://0.0.0.0:8765"])
def test_tunnel_cannot_publish_blender_port(tmp_path, service):
    with pytest.raises(ValueError, match="never route Blender"):
        goodmcp.validate_tunnel_config(tunnel_file(tmp_path, service), "https://mcp.example.com/mcp")


def test_tunnel_cannot_add_extra_routes_or_bypass(tmp_path):
    path = tunnel_file(tmp_path)
    data = json.loads(path.read_text())
    data["ingress"].insert(1, {"hostname": "bypass.example.com", "service": "tcp://127.0.0.1:9876"})
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        goodmcp.validate_tunnel_config(path, "https://mcp.example.com/mcp")


def test_local_test_never_starts_tunnel(tmp_path, monkeypatch):
    popen = Mock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    with pytest.raises(ValueError, match="requires --no-tunnel"):
        goodmcp.start(tmp_path, local_test=True)
    popen.assert_not_called()


def test_blender_offline_prevents_start(tmp_path, monkeypatch):
    monkeypatch.setattr(goodmcp.socket, "create_connection", Mock(side_effect=ConnectionRefusedError))
    monkeypatch.setenv("BLENDER_HOST", "127.0.0.1")
    popen = Mock()
    monkeypatch.setattr(subprocess, "Popen", popen)
    with pytest.raises(RuntimeError, match="Blender offline"):
        goodmcp.start(tmp_path, local_test=True, no_tunnel=True)
    popen.assert_not_called()


@pytest.mark.parametrize("status,challenge,accepted", [
    (401, 'Bearer resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource"', True),
    (302, "", False), (200, "", False), (401, "Bearer", False), (502, "", False),
])
def test_public_gate_requires_managed_oauth(monkeypatch, status, challenge, accepted):
    response = httpx.Response(status, headers={"WWW-Authenticate": challenge})
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.return_value = response
    monkeypatch.setattr(httpx, "Client", Mock(return_value=client))
    if accepted:
        goodmcp.probe_public("https://mcp.example.com/mcp")
    else:
        with pytest.raises(RuntimeError, match="Managed OAuth"):
            goodmcp.probe_public("https://mcp.example.com/mcp")


def test_stop_only_terminates_a_live_owned_process():
    dead, live = Mock(), Mock()
    dead.poll.return_value = 0
    live.poll.return_value = None
    goodmcp.stop_owned(dead)
    goodmcp.stop_owned(live)
    dead.terminate.assert_not_called()
    live.terminate.assert_called_once()
    live.wait.assert_called_once_with(timeout=5)


def test_start_cleans_up_on_tunnel_exit(tmp_path, monkeypatch):
    config = goodmcp.AccessConfig("https://test.cloudflareaccess.com", "aud", "owner@example.com", "https://mcp.example.com/mcp")
    monkeypatch.setattr(goodmcp.AccessConfig, "from_env", Mock(return_value=config))
    monkeypatch.setattr(goodmcp, "probe_blender", Mock())
    monkeypatch.setattr(goodmcp, "probe_origin", Mock())
    monkeypatch.setattr(goodmcp, "probe_public", Mock())
    monkeypatch.setattr(goodmcp, "validate_tunnel_config", Mock())
    monkeypatch.setattr(goodmcp.shutil, "which", Mock(return_value="cloudflared"))
    monkeypatch.setattr(subprocess, "run", Mock())
    monkeypatch.setattr(goodmcp.socket, "socket", MagicMock())
    monkeypatch.setattr(goodmcp.time, "sleep", Mock())
    server, tunnel = Mock(), Mock()
    server.poll.return_value = None
    tunnel.poll.return_value = 1
    monkeypatch.setattr(subprocess, "Popen", Mock(side_effect=[server, tunnel]))
    with pytest.raises(RuntimeError, match="Tunnel stopped"):
        goodmcp.start(tmp_path)
    server.terminate.assert_called_once()
    tunnel.terminate.assert_not_called()


def test_startup_failure_stops_owned_origin(tmp_path, monkeypatch):
    monkeypatch.setattr(goodmcp, "probe_blender", Mock())
    monkeypatch.setattr(goodmcp.socket, "socket", MagicMock())
    monkeypatch.setattr(goodmcp, "probe_origin", Mock(side_effect=RuntimeError("not ready")))
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr(subprocess, "Popen", Mock(return_value=process))
    with pytest.raises(RuntimeError, match="not ready"):
        goodmcp.start(tmp_path, local_test=True, no_tunnel=True)
    process.terminate.assert_called_once()


@pytest.mark.parametrize("data", [[], {}, {"tunnel": False, "credentials-file": 1, "ingress": []}])
def test_malformed_tunnel_config_is_rejected(tmp_path, data):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        goodmcp.validate_tunnel_config(path, "https://mcp.example.com/mcp")
