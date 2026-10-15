"""Real RSA/JWKS verification and HTTP denial before tool dispatch."""
import json
import time

from cryptography.hazmat.primitives.asymmetric import rsa
import jwt
import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from blender_mcp.access import AccessConfig, AccessMiddleware, AccessVerifier


@pytest.fixture
def signed_access():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="test-key", alg="RS256", use="sig")
    config = AccessConfig("https://test.cloudflareaccess.com", "test-audience",
                          "owner@example.com", "https://mcp.example.com/mcp")
    verifier = AccessVerifier(config)
    verifier.keys.fetch_data = lambda: {"keys": [jwk]}

    def token(**overrides):
        claims = {"iss": config.issuer, "aud": [config.audience], "email": config.email,
                  "sub": "one-owner", "iat": int(time.time()) - 1,
                  "exp": int(time.time()) + 60}
        claims.update(overrides)
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})
    return verifier, token


def client_for(verifier=None, local=False, peer="127.0.0.1"):
    async def endpoint(request):
        return JSONResponse({"dispatched": True})
    app = Starlette(routes=[Route("/{path:path}", endpoint, methods=["GET", "POST", "DELETE"])])
    return TestClient(AccessMiddleware(app, verifier, local), client=(peer, 12345))


@pytest.mark.parametrize("method", ["get", "post", "delete"])
@pytest.mark.parametrize("path", ["/mcp", "/mcp/", "/other"])
def test_every_path_and_method_require_auth(signed_access, method, path):
    verifier, _ = signed_access
    with client_for(verifier) as client:
        response = getattr(client, method)(path)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["www-authenticate"] == "Bearer"


def test_valid_owner_token_passes(signed_access):
    verifier, token = signed_access
    with client_for(verifier) as client:
        assert client.post("/mcp", headers={"Cf-Access-Jwt-Assertion": token()}).json() == {"dispatched": True}


@pytest.mark.parametrize("overrides,status", [
    ({"exp": 1}, 401), ({"aud": "other"}, 401),
    ({"iss": "https://attacker.example"}, 401),
    ({"email": "stranger@example.com"}, 403), ({"email": None}, 401),
    ({"nbf": int(time.time()) + 3600}, 401),
])
def test_invalid_claims_are_rejected(signed_access, overrides, status):
    verifier, token = signed_access
    with client_for(verifier) as client:
        assert client.post("/mcp", headers={"Cf-Access-Jwt-Assertion": token(**overrides)}).status_code == status


def test_forged_unsigned_and_oversized_tokens_are_rejected(signed_access):
    verifier, token = signed_access
    parts = token().split(".")
    parts[2] = "AAAA"
    values = [".".join(parts), jwt.encode({"email": "owner@example.com"}, "", algorithm="none"), "x"*16385]
    with client_for(verifier) as client:
        for value in values:
            response = client.post("/mcp", headers={"Cf-Access-Jwt-Assertion": value})
            assert response.status_code == 401
            assert value not in response.text
        assert client.post("/mcp", headers={"Authorization": "Bearer " + token()}).status_code == 401
        assert client.post("/mcp", headers=[("Cf-Access-Jwt-Assertion", token()), ("Cf-Access-Jwt-Assertion", token())]).status_code == 401


def test_missing_required_claims_rejected(signed_access):
    verifier, token = signed_access
    with pytest.raises(jwt.InvalidTokenError):
        verifier.verify(token(exp=None))


def test_jwks_failure_fails_closed_and_does_not_leak(signed_access):
    verifier, token = signed_access
    def failure(_):
        raise RuntimeError("sensitive internal failure")
    verifier.verify = failure
    with client_for(verifier) as client:
        response = client.post("/mcp", headers={"Cf-Access-Jwt-Assertion": token()})
        assert response.status_code == 503
        assert "sensitive" not in response.text


@pytest.mark.parametrize("peer,headers,status", [
    ("127.0.0.1", {}, 200), ("192.0.2.1", {}, 403),
    ("127.0.0.1", {"CF-Connecting-IP": "192.0.2.1"}, 403),
    ("127.0.0.1", {"X-Forwarded-For": "127.0.0.1"}, 403),
])
def test_local_test_cannot_accept_proxy_traffic(peer, headers, status):
    with client_for(local=True, peer=peer) as client:
        assert client.post("/mcp", headers=headers).status_code == status


def test_config_requires_one_owner_and_cloudflare_issuer(monkeypatch):
    for key in ("GOODMCP_ACCESS_TEAM_DOMAIN", "GOODMCP_ACCESS_AUD", "GOODMCP_ALLOWED_EMAIL", "GOODMCP_PUBLIC_URL"):
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(ValueError):
        AccessConfig.from_env()
    monkeypatch.setenv("GOODMCP_ACCESS_TEAM_DOMAIN", "test.cloudflareaccess.com")
    monkeypatch.setenv("GOODMCP_ACCESS_AUD", "app-audience")
    monkeypatch.setenv("GOODMCP_ALLOWED_EMAIL", "owner@example.com")
    monkeypatch.setenv("GOODMCP_PUBLIC_URL", "https://mcp.example.com/mcp")
    assert AccessConfig.from_env().email == "owner@example.com"
    monkeypatch.setenv("GOODMCP_ACCESS_TEAM_DOMAIN", "attacker.example")
    with pytest.raises(ValueError):
        AccessConfig.from_env()


def test_authenticated_mcp_dispatch_and_direct_write_denial(signed_access):
    from mcp.server.fastmcp import FastMCP
    from blender_mcp.remote import configure_http, parse_transport_args, process_http_app
    from blender_mcp.remote_policy import install_tool_policy
    verifier, token = signed_access
    invoked = []
    mcp = FastMCP("secured")

    @mcp.tool()
    def get_scene_info() -> str:
        invoked.append("read")
        return "test scene"

    @mcp.tool()
    def execute_blender_code(code: str) -> str:
        invoked.append("write")
        return code

    args, _ = parse_transport_args([])
    configure_http(mcp, args)
    install_tool_policy(mcp)
    app = AccessMiddleware(process_http_app(mcp), verifier)
    headers = {"Cf-Access-Jwt-Assertion": token(), "Accept": "application/json, text/event-stream"}
    def rpc(method, params=None):
        return {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}

    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        payload = rpc("tools/call", {"name": "get_scene_info", "arguments": {}})
        assert client.post("/mcp", json=payload).status_code == 401
        assert not invoked
        result = client.post("/mcp", json=payload, headers=headers)
        assert result.status_code == 200
        assert "test scene" in result.text
        assert invoked == ["read"]
        listed = client.post("/mcp", json=rpc("tools/list"), headers=headers).json()
        assert [t["name"] for t in listed["result"]["tools"]] == ["get_scene_info"]
        denied = client.post("/mcp", headers=headers, json=rpc("tools/call", {
            "name": "execute_blender_code", "arguments": {"code": "private payload"}})).json()
        assert denied["result"]["isError"]
        assert invoked == ["read"]
        bad_host = {**headers, "Host": "attacker.example"}
        assert client.post("/mcp", json=payload, headers=bad_host).status_code == 421
