Adds loopback-only Streamable HTTP at /mcp using the existing FastMCP instance while preserving default stdio and Blender --host/--port flags. Blender socket I/O runs in workers so a slow tool does not block discovery or other HTTP requests. The shared socket retains its exchange lock and process-scoped lifecycle; cancelled requests drain their reply, timeouts reconnect without replaying writes, and concurrent screenshots use separate files.

Baseline had six failures because private telemetry config was missing; addon status reports unknown consent without losing Blender status. The addon is unchanged. Remote request/response sizes and socket time are bounded.

Validation: 492 passed, 1 pre-existing skip on PR-1; GitHub Actions passed. Real HTTP regressions cover slow get_scene_info/execute_blender_code/look alongside responsive tools/list, cancellation, timeout/reconnect, and concurrent capture files. The slow-tool regression fails with TimeoutError on the original f1cd848 commit.

MCP Inspector CLI 1.0.2 initialize/list/read/image/write/save passed against Blender 4.3.2 on a disposable scene, in addition to real SDK stdio/HTTP checks. Transcript: docs/TEST_RESULTS.md. Native Windows, public Tunnel/OAuth and web-client acceptance remain pending. No Tunnel may be connected before PR-2 authentication.

CI: https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38694224302
