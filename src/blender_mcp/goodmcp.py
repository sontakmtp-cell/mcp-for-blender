"""Small foreground operator command for the owner's Windows Blender machine."""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from dotenv import load_dotenv

from .access import AccessConfig

ORIGIN = "http://127.0.0.1:8765/mcp"


def probe_blender():
    host = os.environ.get("BLENDER_HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("BLENDER_HOST must be loopback")
    port = int(os.environ.get("BLENDER_PORT", "9876"))
    try:
        with socket.create_connection((host, port), timeout=2) as conn:
            conn.sendall(b'{"type":"get_addon_info","params":{}}')
            payload = b""
            deadline = time.monotonic() + 5
            while len(payload) < 16384:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                conn.settimeout(remaining)
                part = conn.recv(4096)
                if not part:
                    break
                payload += part
                try:
                    result = json.loads(payload)
                except (ValueError, UnicodeError):
                    continue
                if result.get("status") == "success" and result.get("result", {}).get("protocol_version"):
                    return
                break
    except OSError:
        pass
    raise RuntimeError("Blender offline: open Blender and Start MCP Server in the addon")


def probe_origin(local_test=False):
    with httpx.Client(trust_env=False, timeout=5, follow_redirects=False) as client:
        response = client.post(ORIGIN, headers={"Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": "2025-11-25", "capabilities": {},
                "clientInfo": {"name": "goodmcp-check", "version": "1"}}})
    if local_test:
        if response.status_code != 200 or "serverInfo" not in response.json().get("result", {}):
            raise RuntimeError("Local-test MCP initialization failed")
    elif response.status_code != 401 or response.json().get("error") != "Cloudflare Access authentication required":
        raise RuntimeError("Origin did not deny an unauthenticated request; stop before connecting a Tunnel")


def probe_public(public_url):
    with httpx.Client(timeout=10, follow_redirects=False) as client:
        response = client.post(public_url, headers={"Accept": "application/json, text/event-stream"},
                               json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    if response.status_code != 401 or "resource_metadata" not in response.headers.get("WWW-Authenticate", ""):
        raise RuntimeError("Public endpoint must return Managed OAuth 401 + resource_metadata; check Access before starting Tunnel")


def validate_tunnel_config(path, public_url):
    """JSON is a YAML subset accepted by cloudflared, and easy to validate strictly."""
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict) or set(config) != {"tunnel", "credentials-file", "ingress"}:
        raise ValueError("Tunnel config must contain only tunnel, credentials-file and ingress")
    if not isinstance(config["tunnel"], str) or not isinstance(config["credentials-file"], str):
        raise ValueError("Tunnel UUID and credentials-file must be strings")
    UUID(config["tunnel"])
    expected = [{"hostname": urlsplit(public_url).hostname, "service": "http://127.0.0.1:8765"},
                {"service": "http_status:404"}]
    if config["ingress"] != expected:
        raise ValueError("Tunnel must route only the configured hostname to 127.0.0.1:8765 and end with 404; never route Blender port 9876")
    credentials = Path(config["credentials-file"]).expanduser()
    if not credentials.is_absolute() or not credentials.is_file():
        raise ValueError("Tunnel credential file is missing; run cloudflared tunnel create goodmcp-blender locally")


def stop_owned(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def start(root, local_test=False, no_tunnel=False):
    if local_test and not no_tunnel:
        raise ValueError("--local-test requires --no-tunnel; it must never be published")
    config = None if local_test else AccessConfig.from_env()
    probe_blender()
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", 8765))
        except OSError:
            raise RuntimeError("Port 8765 is already in use; stop your previous GoodMCP instance") from None
    tunnel_path = None
    if not no_tunnel:
        executable = shutil.which("cloudflared")
        if not executable:
            raise RuntimeError("Install cloudflared before starting the named Tunnel")
        tunnel_path = Path(os.environ.get("GOODMCP_TUNNEL_CONFIG", "")).expanduser().resolve()
        validate_tunnel_config(tunnel_path, config.public_url)
        # Access must already protect the hostname, even if the Tunnel is offline.
        probe_public(config.public_url)
        subprocess.run([executable, "tunnel", "--config", str(tunnel_path), "ingress", "validate"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    state = root / ".goodmcp"
    state.mkdir(exist_ok=True)
    processes = []
    env = {**os.environ, "BLENDER_MCP_SAFE_MODE": "1", "DISABLE_TELEMETRY": "true"}
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    with (state / "server.log").open("a", encoding="utf-8") as log:
        try:
            command = [sys.executable, "-c", "from blender_mcp.server import main; main()",
                       "--transport", "streamable-http"]
            if local_test:
                command.append("--local-test")
            server = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=log, creationflags=flags)
            processes.append(server)
            for _ in range(60):
                if server.poll() is not None:
                    raise RuntimeError("GoodMCP exited; inspect the private .goodmcp/server.log")
                try:
                    probe_origin(local_test)
                    break
                except httpx.TransportError:
                    time.sleep(0.25)
            else:
                raise RuntimeError("GoodMCP did not become ready")
            if tunnel_path:
                tunnel = subprocess.Popen([executable, "tunnel", "--config", str(tunnel_path), "run"],
                    cwd=root, stdout=log, stderr=log, creationflags=flags)
                processes.append(tunnel)
            print("GoodMCP started. Ctrl+C stops only the processes launched here; Blender stays open.", flush=True)
            print("Local-test only; no Tunnel." if local_test else "Origin auth enabled; verify owner login in Inspector before web AI use.", flush=True)
            while all(p.poll() is None for p in processes):
                time.sleep(0.5)
            raise RuntimeError("GoodMCP or Tunnel stopped; inspect the private log")
        except KeyboardInterrupt:
            print("Stopping GoodMCP and its Tunnel.")
        finally:
            for process in reversed(processes):
                stop_owned(process)


def main(argv=None):
    parser = argparse.ArgumentParser(description="GoodMCP single-owner operations")
    commands = parser.add_subparsers(dest="command", required=True)
    start_parser = commands.add_parser("start")
    start_parser.add_argument("--local-test", action="store_true")
    start_parser.add_argument("--no-tunnel", action="store_true")
    check_parser = commands.add_parser("check")
    check_parser.add_argument("--local-only", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env", override=False)
    try:
        if args.command == "start":
            start(root, args.local_test, args.no_tunnel)
        else:
            probe_blender()
            print("Blender addon: responding on loopback")
            probe_origin()
            print("Origin: unauthenticated requests denied")
            if not args.local_only:
                probe_public(AccessConfig.from_env().public_url)
                print("Public endpoint: Managed OAuth challenge present (owner login still needs an MCP client)")
        return 0
    except RuntimeError as exc:
        # RuntimeError messages above are fixed operator guidance, not payloads.
        print(str(exc), file=sys.stderr)
        return 1
    except (ValueError, OSError, httpx.HTTPError, subprocess.SubprocessError):
        # Never echo config contents, tokens, request URLs or subprocess errors.
        print("GoodMCP check/start failed. Verify Blender, .env, Access and your private Tunnel config.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
