"""Single-owner Cloudflare Access verification, before any MCP dispatch.

OAuth is handled by Cloudflare, never by this origin. Only signed Access app
JWTs from the configured team/audience and owner are accepted here.
"""
from dataclasses import dataclass
import ipaddress
import os
import re
from urllib.parse import urlsplit

import anyio
import jwt
from starlette.responses import JSONResponse


class OwnerDenied(Exception):
    pass


@dataclass(frozen=True)
class AccessConfig:
    issuer: str
    audience: str
    email: str
    public_url: str

    @classmethod
    def from_env(cls):
        team = os.environ.get("GOODMCP_ACCESS_TEAM_DOMAIN", "").strip().lower()
        audience = os.environ.get("GOODMCP_ACCESS_AUD", "").strip()
        email = os.environ.get("GOODMCP_ALLOWED_EMAIL", "").strip().casefold()
        public_url = os.environ.get("GOODMCP_PUBLIC_URL", "").strip()
        url = urlsplit(public_url)
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.cloudflareaccess\.com", team):
            raise ValueError("Set GOODMCP_ACCESS_TEAM_DOMAIN to your team.cloudflareaccess.com hostname")
        if not audience or not re.fullmatch(r"[^\s@,]+@[^\s@,]+\.[^\s@,]+", email):
            raise ValueError("Set GOODMCP_ACCESS_AUD and exactly one GOODMCP_ALLOWED_EMAIL")
        if (url.scheme != "https" or not url.hostname or url.path != "/mcp"
                or url.username or url.password or url.port or url.query or url.fragment
                or not re.fullmatch(r"[a-z0-9.-]+", url.hostname)):
            raise ValueError("GOODMCP_PUBLIC_URL must be https://your-hostname/mcp without credentials or port")
        return cls(f"https://{team}", audience, email, public_url)


class AccessVerifier:
    def __init__(self, config):
        self.config = config
        # TLS verification stays enabled. Never follow jku/x5u supplied by a token.
        self.keys = jwt.PyJWKClient(
            config.issuer + "/cdn-cgi/access/certs", timeout=5,
            cache_keys=False, cache_jwk_set=True, lifespan=300,
        )

    def verify(self, token):
        key = self.keys.get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"],
            audience=self.config.audience, issuer=self.config.issuer,
            options={"require": ["exp", "iat", "iss", "aud", "email", "sub"]})
        if not isinstance(claims["email"], str) or claims["email"].casefold() != self.config.email:
            raise OwnerDenied()
        return claims


class AccessMiddleware:
    def __init__(self, app, verifier=None, local_test=False):
        self.app, self.verifier, self.local_test = app, verifier, local_test
        if not local_test and verifier is None:
            raise ValueError("Access verifier is required")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = scope.get("headers", [])
        if self.local_test:
            client = scope.get("client")
            try:
                local = bool(client and ipaddress.ip_address(client[0]).is_loopback)
            except ValueError:
                local = False
            # Refuse traffic forwarded by a Tunnel/reverse proxy in test mode.
            forwarded = any(k.lower() in {
                b"forwarded", b"x-forwarded-for", b"x-forwarded-host",
                b"cf-connecting-ip", b"cf-ray", b"cf-access-jwt-assertion",
            } for k, _ in headers)
            if not local or forwarded:
                await self.reject(scope, receive, send, 403)
                return
        else:
            assertions = [v for k, v in headers if k.lower() == b"cf-access-jwt-assertion"]
            if len(assertions) != 1 or not 0 < len(assertions[0]) <= 16384:
                await self.reject(scope, receive, send, 401)
                return
            try:
                token = assertions[0].decode("ascii")
                await anyio.to_thread.run_sync(self.verifier.verify, token)
            except OwnerDenied:
                await self.reject(scope, receive, send, 403)
                return
            except jwt.PyJWKClientConnectionError:
                await self.reject(scope, receive, send, 503)
                return
            except (jwt.InvalidTokenError, jwt.PyJWKClientError, UnicodeError, ValueError):
                await self.reject(scope, receive, send, 401)
                return
            except Exception:
                # Fail closed on JWKS/network problems; never expose token/error text.
                await self.reject(scope, receive, send, 503)
                return
        await self.app(scope, receive, send)

    @staticmethod
    async def reject(scope, receive, send, status):
        message = {401: "Cloudflare Access authentication required", 403: "Owner access denied",
                   503: "Access verification temporarily unavailable"}[status]
        headers = {"Cache-Control": "no-store"}
        if status == 401:
            headers["WWW-Authenticate"] = "Bearer"
        await JSONResponse({"error": message}, status_code=status, headers=headers)(scope, receive, send)
