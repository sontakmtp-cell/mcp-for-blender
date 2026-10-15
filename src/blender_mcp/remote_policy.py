"""Conservative remote policy; enforced at discovery AND dispatch."""
from contextvars import ContextVar
from urllib.parse import urlsplit

from mcp.shared.exceptions import McpError
from mcp.types import (CallToolRequest, CallToolResult, ListToolsRequest,
                       ListResourcesRequest, ListResourceTemplatesRequest,
                       ReadResourceRequest, ErrorData, INVALID_PARAMS, ServerResult, TextContent)

from .openai_apps import VIEWPORT_URI

READ_TOOLS = frozenset({"get_addon_status", "get_scene_info", "look"})
WRITE_TOOLS = READ_TOOLS | {"execute_blender_code", "search_assets", "import_asset", "generate_3d"}

# Default preserves stdio. Only trusted remote dispatch sets this; it is not a
# tool argument. AnyIO copies its request context into the Blender I/O worker.
disk_images_allowed = ContextVar("goodmcp_disk_images_allowed", default=True)
RESOURCE_TEMPLATES = frozenset({f"blender://{kind}/{{name}}" for kind in ("object", "material", "collection")})


def resource_allowed(uri):
    if str(uri) == VIEWPORT_URI:
        return True  # Bundled static viewport HTML, not a caller-chosen file.
    try:
        parsed = urlsplit(str(uri))
    except ValueError:
        return False
    return (parsed.scheme == "blender" and parsed.netloc in {"object", "material", "collection"}
            and parsed.path.startswith("/") and len(parsed.path) > 1
            and not parsed.query and not parsed.fragment)


def install_tool_policy(mcp, allow_write=False):
    allowed = WRITE_TOOLS if allow_write else READ_TOOLS
    handlers = mcp._mcp_server.request_handlers
    list_handler, call_handler = handlers[ListToolsRequest], handlers[CallToolRequest]
    resource_list_handler = handlers[ListResourcesRequest]
    template_list_handler = handlers[ListResourceTemplatesRequest]
    resource_read_handler = handlers[ReadResourceRequest]

    async def list_tools(request):
        result = await list_handler(request)
        result.root.tools = [tool for tool in result.root.tools if tool.name in allowed]
        return result

    async def call_tool(request):
        if request.params.name not in allowed:
            return ServerResult(CallToolResult(isError=True, content=[TextContent(
                type="text", text="Tool is not allowed by the GoodMCP remote policy")]))
        token = disk_images_allowed.set(allow_write)
        try:
            return await call_handler(request)
        finally:
            disk_images_allowed.reset(token)

    async def list_resources(request):
        result = await resource_list_handler(request)
        result.root.resources = [r for r in result.root.resources if resource_allowed(r.uri)]
        return result

    async def list_templates(request):
        result = await template_list_handler(request)
        result.root.resourceTemplates = [r for r in result.root.resourceTemplates if r.uriTemplate in RESOURCE_TEMPLATES]
        return result

    async def read_resource(request):
        if not resource_allowed(request.params.uri):
            raise McpError(ErrorData(code=INVALID_PARAMS, message="Resource is not allowed by the GoodMCP remote policy"))
        return await resource_read_handler(request)

    handlers[ListToolsRequest] = list_tools
    handlers[CallToolRequest] = call_tool
    handlers[ListResourcesRequest] = list_resources
    handlers[ListResourceTemplatesRequest] = list_templates
    handlers[ReadResourceRequest] = read_resource
