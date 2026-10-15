"""Loopback Streamable HTTP adapter; the existing FastMCP owns every tool."""
import argparse
import logging
import os
from contextlib import asynccontextmanager
from urllib.parse import urlsplit


def parse_transport_args(argv):
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--http-host", choices=("127.0.0.1",), default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8765)
    parser.add_argument("--local-test", action="store_true")
    args, remaining = parser.parse_known_args(argv)
    if not 1 <= args.http_port <= 65535:
        parser.error("--http-port must be between 1 and 65535")
    return args, remaining


def configure_http(mcp, args, public_url=None):
    from mcp.server.transport_security import TransportSecuritySettings

    mcp.settings.host = args.http_host
    mcp.settings.port = args.http_port
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True
    mcp.settings.streamable_http_path = "/mcp"
    mcp.settings.max_request_body_size = 1024 * 1024
    mcp.settings.transport_security = TransportSecuritySettings(
        allowed_hosts=[f"127.0.0.1:{args.http_port}", f"localhost:{args.http_port}"]
            + ([urlsplit(public_url).netloc] if public_url else []),
        allowed_origins=[f"http://127.0.0.1:{args.http_port}", f"http://localhost:{args.http_port}"]
            + ([f"https://{urlsplit(public_url).netloc}"] if public_url else []),
    )


def process_http_app(mcp):
    """Keep the shared Blender socket alive across stateless HTTP requests.

    SDK 1.29 runs low-level lifespan per request in stateless mode; the
    upstream lifespan closes the socket, so run it once at ASGI process scope.
    """
    original_lifespan = mcp._mcp_server.lifespan

    @asynccontextmanager
    async def request_lifespan(_):
        yield {}

    mcp._mcp_server.lifespan = request_lifespan
    app = mcp.streamable_http_app()
    sdk_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def process_lifespan(application):
        async with original_lifespan(mcp._mcp_server):
            async with sdk_lifespan(application):
                yield

    app.router.lifespan_context = process_lifespan
    return app


def run_http(mcp, args):
    import uvicorn
    from .access import AccessConfig, AccessMiddleware, AccessVerifier
    from .remote_policy import install_tool_policy

    config = None if args.local_test else AccessConfig.from_env()
    # Never expose an off-machine Blender socket in remote mode.
    from . import server
    blender_host, _ = server.resolve_connection(server.CLI_HOST, server.CLI_PORT)
    if blender_host not in {"localhost", "127.0.0.1"}:
        raise ValueError("Remote mode requires Blender on loopback")
    os.environ["BLENDER_MCP_SAFE_MODE"] = "1"
    os.environ["DISABLE_TELEMETRY"] = "true"
    os.environ["BLENDER_MCP_CONTEXT_LOG"] = "0"
    # Upstream INFO logs include raw Python; suppress that logger for remote.
    logging.getLogger("BlenderMCPServer").disabled = True
    configure_http(mcp, args, config.public_url if config else None)
    install_tool_policy(mcp, allow_write=os.environ.get("GOODMCP_ALLOW_WRITE") == "1")
    app = AccessMiddleware(process_http_app(mcp),
        verifier=AccessVerifier(config) if config else None, local_test=args.local_test)
    uvicorn.run(app, host="127.0.0.1", port=args.http_port,
                proxy_headers=False, access_log=False, log_level="warning", log_config=None)
