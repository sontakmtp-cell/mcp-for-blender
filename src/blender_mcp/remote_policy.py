"""Conservative remote tool policy; enforced at discovery AND dispatch."""
from mcp.types import (CallToolRequest, CallToolResult, ListToolsRequest,
                       ServerResult, TextContent)

READ_TOOLS = frozenset({"get_addon_status", "get_scene_info", "look"})
WRITE_TOOLS = READ_TOOLS | {"execute_blender_code", "search_assets", "import_asset", "generate_3d"}


def install_tool_policy(mcp, allow_write=False):
    allowed = WRITE_TOOLS if allow_write else READ_TOOLS
    handlers = mcp._mcp_server.request_handlers
    list_handler, call_handler = handlers[ListToolsRequest], handlers[CallToolRequest]

    async def list_tools(request):
        result = await list_handler(request)
        result.root.tools = [tool for tool in result.root.tools if tool.name in allowed]
        return result

    async def call_tool(request):
        if request.params.name not in allowed:
            return ServerResult(CallToolResult(isError=True, content=[TextContent(
                type="text", text="Tool is not allowed by the GoodMCP remote policy")]))
        return await call_handler(request)

    handlers[ListToolsRequest] = list_tools
    handlers[CallToolRequest] = call_tool
