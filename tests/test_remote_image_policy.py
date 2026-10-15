"""Real HTTP dispatch and the real observation script against a minimal bpy backend."""
import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import time
import types
import zlib

import httpx
import pytest


def png_bytes():
    def chunk(tag, data):
        return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!IIBBBBB', 2, 2, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + b'\xff\0\0\xff' * 2) * 2)) + chunk(b'IEND', b''))


def fake_modules():
    loads, resolutions = [], []

    class Image:
        def __init__(self, name, data=None):
            self.name, self.data = name, data or png_bytes()
            self.size, self.type, self.is_float = (2, 2), 'IMAGE', False

        def copy(self):
            return Image(self.name, self.data)

        def save(self):
            Path(self.filepath_raw).write_bytes(self.data)

        def save_render(self, path, scene=None):
            Path(path).write_bytes(self.data)

    class Images(dict):
        def load(self, path, check_existing=False):
            loads.append(path)
            return Image(Path(path).name, Path(path).read_bytes())

        def remove(self, image):
            pass

    images = Images({name: Image(name) for name in (
        'Scene Texture', 'Render Result', 'folder/Ảnh.png', '%2e%2e/private.png', r'C:\textures\wood.png')})
    images['Render Result'].type, images['Render Result'].is_float = 'RENDER_RESULT', True
    def resolve(ref):
        resolutions.append(ref)
        return ref
    scene = types.SimpleNamespace(render=types.SimpleNamespace(image_settings=types.SimpleNamespace(
        file_format='PNG', color_mode='RGBA', color_depth='8')))
    bpy = types.SimpleNamespace(data=types.SimpleNamespace(images=images), path=types.SimpleNamespace(abspath=resolve),
        context=types.SimpleNamespace(scene=scene, evaluated_depsgraph_get=lambda: None))
    return {'bpy': bpy, 'gpu': types.ModuleType('gpu'), 'numpy': types.ModuleType('numpy'),
            'mathutils': types.SimpleNamespace(Vector=object, Matrix=object)}, loads, resolutions


def configure_fake_blender():
    """Child-process backend: execute the unchanged script, including its actual sink."""
    from blender_mcp import server
    modules, _, _ = fake_modules()
    sys.modules.update(modules)
    lock = threading.Lock()

    class Connection:
        def send_command(self, kind, params=None, **kwargs):
            params = params or {}
            if kind == 'get_addon_info':
                return {'protocol_version': 13, 'addon_version': [1, 8], 'capabilities': []}
            if kind == 'get_object_info':
                return {'name': params['name']}
            if kind == 'list_scene_items':
                return {'items': [{'kind': 'material', 'name': 'Mat Blue'},
                                  {'kind': 'collection', 'name': 'Collection'}]}
            if kind == 'get_viewport_screenshot':
                Path(params['filepath']).write_bytes(png_bytes())
                return {'success': True, 'width': 2, 'height': 2}
            if kind == 'execute_code':
                with lock, redirect_stdout(io.StringIO()) as captured:
                    exec(params['code'], {})
                return {'result': captured.getvalue()}
            return {'enabled': False}
        def disconnect(self):
            pass
    server.get_blender_connection = lambda: Connection()
    server._maybe_handshake_addon(Connection())

    @server.mcp.resource('private://debug')
    def forbidden():
        return 'PRIVATE_RESOURCE_EXECUTED'


@pytest.fixture(params=[False, True], ids=['readonly', 'write-opt-in'])
def image_http(request, tmp_path):
    private = tmp_path / 'private.png'
    private.write_bytes(png_bytes())
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    env = {'GOODMCP_ALLOW_WRITE': '1' if request.param else '0', 'DISABLE_TELEMETRY': 'true',
           'XDG_CONFIG_HOME': str(tmp_path), 'XDG_CACHE_HOME': str(tmp_path)}
    if 'SYSTEMROOT' in os.environ:
        env['SYSTEMROOT'] = os.environ['SYSTEMROOT']
    bootstrap = (f'import sys; sys.path.insert(0, {str(Path(__file__).parent)!r}); '
                 'from test_remote_image_policy import configure_fake_blender; configure_fake_blender(); '
                 'from blender_mcp.server import main; main()')
    with (tmp_path / 'http.log').open('w+') as log:
        process = subprocess.Popen([sys.executable, '-c', bootstrap, '--transport', 'streamable-http',
                                    '--local-test', '--http-port', str(port)], env=env, stdout=log, stderr=log)
        url = f'http://127.0.0.1:{port}/mcp'
        try:
            for _ in range(100):
                if process.poll() is not None:
                    log.seek(0)
                    pytest.fail(log.read())
                try:
                    if httpx.get(url, trust_env=False, timeout=.1).status_code in (405, 406):
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.05)
            else:
                pytest.fail('HTTP startup timeout')
            yield url, private, request.param
        finally:
            process.terminate()
            try:
                process.wait(10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def rpc(url, method, params=None):
    return httpx.post(url, trust_env=False, timeout=10,
        headers={'Accept': 'application/json, text/event-stream'},
        json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}).json()


def test_private_image_read_is_explicit_opt_in_at_http_dispatch(image_http):
    url, private, write = image_http
    result = rpc(url, 'tools/call', {'name': 'look', 'arguments': {
        'image': str(private), 'allow_disk_images': True}})['result']
    if write:
        assert not result.get('isError')
        assert any(c['type'] == 'image' and base64.b64decode(c['data']) == private.read_bytes() for c in result['content'])
    else:
        assert result['isError']
        assert not any(c['type'] == 'image' for c in result['content'])
        assert 'local image files are not allowed' in str(result)
    # A rejected request cannot poison the next request's context or viewport.
    viewport = rpc(url, 'tools/call', {'name': 'look', 'arguments': {}})['result']
    assert not viewport.get('isError') and any(c['type'] == 'image' for c in viewport['content'])


def test_remote_still_shows_existing_images_and_render_result(image_http):
    url, _, _ = image_http
    for name in ('Scene Texture', 'Render Result', 'folder/Ảnh.png', '%2e%2e/private.png', r'C:\textures\wood.png'):
        result = rpc(url, 'tools/call', {'name': 'look', 'arguments': {'image': name}})['result']
        assert not result.get('isError'), result
        assert any(c['type'] == 'image' for c in result['content'])


def test_remote_resource_discovery_and_dispatch_are_allowlisted(image_http):
    from blender_mcp.openai_apps import VIEWPORT_URI
    url, _, _ = image_http
    listed = rpc(url, 'resources/list')['result']['resources']
    assert {r['uri'] for r in listed} == {VIEWPORT_URI}
    templates = rpc(url, 'resources/templates/list')['result']['resourceTemplates']
    assert {r['uriTemplate'] for r in templates} == {
        'blender://object/{name}', 'blender://material/{name}', 'blender://collection/{name}'}
    assert 'contents' in rpc(url, 'resources/read', {'uri': VIEWPORT_URI})['result']
    assert 'Cube' in str(rpc(url, 'resources/read', {'uri': 'blender://object/Cube'})['result'])
    for uri, expected in (('blender://material/Mat%20Blue', 'Mat Blue'),
                          ('blender://collection/Collection', 'Collection')):
        assert expected in str(rpc(url, 'resources/read', {'uri': uri})['result'])
    for uri in ('private://debug', 'file:///tmp/private.png', 'blender://object@attacker/Cube',
                'blender://object:123/Cube', 'blender://object/Cube?path=/tmp/private.png'):
        response = rpc(url, 'resources/read', {'uri': uri})
        assert response['error']['code'] == -32602
        assert 'PRIVATE_RESOURCE_EXECUTED' not in str(response)


@pytest.mark.parametrize('reference', [
    '/tmp/private.png', '../private.png', 'private.png', '//private.png', '~/private.png',
    r'C:\Users\owner\private.png', r'\\server\share\private.png', 'file:///tmp/private.png',
    '%2e%2e/private.png.missing', 'ảnh-riêng.png', '\x00private.png',
])
def test_script_refuses_missing_datablocks_before_path_resolution(monkeypatch, reference):
    from blender_mcp import blender_scripts
    modules, loads, resolutions = fake_modules()
    with monkeypatch.context() as patch:
        for name, module in modules.items():
            patch.setitem(sys.modules, name, module)
        with redirect_stdout(io.StringIO()) as captured:
            exec(blender_scripts.build(blender_scripts.LOOK, {
                'mode': 'image', 'image': reference, 'allow_disk_images': False}), {})
    result = blender_scripts.parse_result(captured.getvalue())
    assert 'local image files are not allowed' in result['error']
    assert not loads and not resolutions


def test_stdio_default_keeps_disk_images_available(monkeypatch, tmp_path):
    from blender_mcp import blender_scripts
    private = tmp_path / 'private.png'
    private.write_bytes(png_bytes())
    modules, loads, _ = fake_modules()
    with monkeypatch.context() as patch:
        for name, module in modules.items():
            patch.setitem(sys.modules, name, module)
        with redirect_stdout(io.StringIO()) as captured:
            exec(blender_scripts.build(blender_scripts.LOOK, {
                'mode': 'image', 'image': str(private), 'filepath': str(tmp_path / 'out.png')}), {})
    assert blender_scripts.parse_result(captured.getvalue())['mode'] == 'image'
    assert loads == [str(private)]
