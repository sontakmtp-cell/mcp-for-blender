Adds loopback-only Streamable HTTP at /mcp using the existing FastMCP instance while preserving default stdio and Blender --host/--port flags. Serializes first socket creation and bounds remote connection time, request size, and responses.

Baseline had six failures because private telemetry config was missing; addon status now reports unknown consent without losing Blender status. The addon is unchanged.

Validation: 486 passed, 1 skipped. Real SDK stdio/HTTP initialize/list/call tested; live Blender 4.3.2 scene/status/image/write/save and concurrent queries passed on a disposable scene. Inspector and Windows/web-client acceptance remain pending. No Tunnel may be connected before PR-2 authentication.
