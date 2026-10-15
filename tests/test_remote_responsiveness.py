"""Real HTTP requests while the shared Blender TCP socket is deliberately slow."""
import asyncio
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import httpx
import pytest

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aC1sAAAAASUVORK5CYII=')


class SlowAddon:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.stop = threading.Event()
        self.connections = 0
        self.delayed = False
        self.listener = socket.socket()
        self.listener.bind(('127.0.0.1', 0))
        self.listener.listen()
        self.listener.settimeout(.1)
        self.port = self.listener.getsockname()[1]
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            self.connections += 1
            with conn:
                conn.settimeout(.1)
                buffer = b''
                while not self.stop.is_set():
                    try:
                        data = conn.recv(65536)
                    except socket.timeout:
                        continue
                    except OSError:
                        break
                    if not data:
                        break
                    buffer += data
                    try:
                        command = json.loads(buffer)
                    except ValueError:
                        continue
                    buffer = b''
                    kind, params = command['type'], command.get('params', {})
                    if kind in {'execute_code', 'get_viewport_screenshot'} and not self.delayed:
                        self.delayed = True
                        self.started.set()
                        self.release.wait(5)
                    result = {'name': 'fake scene', 'objects': []}
                    if kind == 'get_addon_info':
                        result = {'protocol_version': 13, 'addon_version': [1, 8], 'capabilities': []}
                    elif kind == 'execute_code':
                        result = {'result': params['code']}
                    elif kind == 'get_viewport_screenshot':
                        Path(params['filepath']).write_bytes(PNG)
                        result = {'success': True, 'width': 1, 'height': 1}
                    try:
                        conn.sendall(json.dumps({'status': 'success', 'result': result}).encode())
                    except OSError:
                        break

    def close(self):
        self.stop.set()
        self.release.set()
        self.thread.join(2)
        self.listener.close()


@pytest.fixture
def slow_http(tmp_path):
    addon = SlowAddon()
    processes = []

    @contextmanager
    def launch(timeout=180):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        log = (tmp_path / 'http.log').open('w+')
        env = {'DISABLE_TELEMETRY': 'true', 'XDG_CONFIG_HOME': str(tmp_path), 'XDG_CACHE_HOME': str(tmp_path)}
        if 'SYSTEMROOT' in os.environ:
            env['SYSTEMROOT'] = os.environ['SYSTEMROOT']
        process = subprocess.Popen([sys.executable, '-c',
            f'from blender_mcp import server; server.REMOTE_RESPONSE_TIMEOUT={timeout}; server.main()',
            '--transport', 'streamable-http', '--http-port', str(port), '--port', str(addon.port)],
            stdout=log, stderr=log, env=env)
        processes.append(process)
        url = f'http://127.0.0.1:{port}/mcp'
        try:
            for _ in range(100):
                if process.poll() is not None:
                    log.seek(0)
                    pytest.fail(log.read())
                try:
                    if httpx.get(url, timeout=.1, trust_env=False).status_code in (405, 406):
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.05)
            else:
                pytest.fail('HTTP startup timeout')
            yield url
        finally:
            addon.release.set()
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            log.close()

    try:
        yield addon, launch
    finally:
        addon.close()


async def rpc(client, url, method, params=None):
    response = await client.post(url, json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}},
        headers={'Accept': 'application/json, text/event-stream'})
    response.raise_for_status()
    return response.json()['result']


async def wait_started(addon):
    for _ in range(200):
        if addon.started.is_set():
            return
        await asyncio.sleep(.01)
    pytest.fail('Tool never reached the blocking socket')


@pytest.mark.parametrize('name,arguments', [
    ('get_scene_info', {}), ('execute_blender_code', {'code': "print('slow')"}), ('look', {'max_size': 200}),
])
def test_slow_tool_does_not_block_independent_http_request(slow_http, name, arguments):
    addon, launch = slow_http
    with launch() as url:
        async def run():
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                slow = asyncio.create_task(rpc(client, url, 'tools/call', {'name': name, 'arguments': arguments}))
                try:
                    await wait_started(addon)
                    # This deadline is below the fake socket's five-second wait.
                    listed = await asyncio.wait_for(rpc(client, url, 'tools/list'), timeout=.8)
                    assert any(t['name'] == 'get_scene_info' for t in listed['tools'])
                    assert not slow.done()
                finally:
                    addon.release.set()
                result = await slow
                assert not result.get('isError')
                assert addon.connections == 1
        asyncio.run(run())


def test_cancelled_request_drains_socket_before_next_command(slow_http):
    addon, launch = slow_http
    with launch() as url:
        async def run():
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                first = asyncio.create_task(rpc(client, url, 'tools/call', {
                    'name': 'execute_blender_code', 'arguments': {'code': "print('slow-cancelled')"}}))
                await wait_started(addon)
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                second = asyncio.create_task(rpc(client, url, 'tools/call', {
                    'name': 'execute_blender_code', 'arguments': {'code': "print('next-command')"}}))
                listed = await asyncio.wait_for(rpc(client, url, 'tools/list'), timeout=.8)
                assert listed['tools']
                addon.release.set()
                result = await second
                assert 'next-command' in str(result)
                assert 'slow-cancelled' not in str(result)
                assert addon.connections == 1
        asyncio.run(run())


def test_socket_timeout_reconnects_without_replaying_write(slow_http):
    addon, launch = slow_http
    with launch(timeout=.2) as url:
        async def run():
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                result = await rpc(client, url, 'tools/call', {
                    'name': 'execute_blender_code', 'arguments': {'code': "print('timed-out')"}})
                assert 'Timeout waiting for Blender response' in str(result)
                addon.release.set()
                result = await rpc(client, url, 'tools/call', {
                    'name': 'execute_blender_code', 'arguments': {'code': "print('after-reconnect')"}})
                assert 'after-reconnect' in str(result)
                assert 'timed-out' not in str(result)
                assert addon.connections == 2
        asyncio.run(run())


def test_concurrent_viewport_captures_use_separate_files(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from blender_mcp import server
    barrier = threading.Barrier(2)
    paths = []
    lock = threading.Lock()

    class CaptureAddon:
        def send_command(self, command, params):
            with lock:
                index = len(paths)
                paths.append(params['filepath'])
            Path(params['filepath']).write_bytes(f'image-{index}'.encode())
            barrier.wait(timeout=3)
            return {'success': True}

    monkeypatch.setattr(server, 'get_blender_connection', lambda: CaptureAddon())
    with ThreadPoolExecutor(2) as workers:
        results = list(workers.map(server._capture_viewport, [200, 200]))
    assert len(set(paths)) == 2
    assert sorted(image for image, _ in results) == [b'image-0', b'image-1']
    assert all(not Path(path).exists() for path in paths)
