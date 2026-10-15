"""Loopback Streamable HTTP adapter; the existing FastMCP owns every tool."""
import argparse
from contextlib import asynccontextmanager


def parse_transport_args(argv):
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--http-host", choices=("127.0.0.1",), default="127.0.0.1")
    parser.add_argument("--http-port", type=int, default=8765)
    args, remaining = parser.parse_known_args(argv)
    if not 1 <= args.http_port <= 65535:
        parser.error("--http-port must be between 1 and 65535")
    return args, remaining


def configure_http(mcp, args):
    from mcp.server.transport_security import TransportSecuritySettings

    mcp.settings.host = args.http_host
    mcp.settings.port = args.http_port
    mcp.settings.stateless_http = True
    mcp.settings.json_response = True
    mcp.settings.streamable_http_path = "/mcp"
    mcp.settings.max_request_body_size = 1024 * 1024
    mcp.settings.transport_security = TransportSecuritySettings(
        allowed_hosts=[f"127.0.0.1:{args.http_port}", f"localhost:{args.http_port}"],
        allowed_origins=[f"http://127.0.0.1:{args.http_port}", f"http://localhost:{args.http_port}"],
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
    configure_http(mcp, args)
    import uvicorn
    uvicorn.run(process_http_app(mcp), host=args.http_host, port=args.http_port)
