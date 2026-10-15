Adds a foreground Start/Check workflow for the owner's Windows Blender machine, strict named-Tunnel routing validation, Vietnamese setup and recovery instructions, and an acceptance matrix that distinguishes protocol, account eligibility, and read/write access.

The launcher refuses Tunnel startup without a Managed OAuth challenge, binds the origin only to loopback, checks Blender before starting, and cleans up only its own processes. Uvicorn's default logging reconfiguration is disabled so it cannot re-enable the upstream payload logger.

Validation includes operator safety/cleanup tests, complete regression suite, real MCP Inspector discovery/read/image/write/save against a disposable Blender scene, and PowerShell parsing/argument/directory/exit-status tests on Linux. These do not establish native Windows or web-client acceptance.

Blocked external acceptance: Cloudflare account configuration and public HTTPS, real owner/non-owner authentication and revocation, Windows desktop startup/restart, and Grok/ChatGPT/Gemini account-specific flows. No public Tunnel or DNS change was made.

Earlier local regression result: 535 passed, 1 pre-existing skip (42.28s). The latest verified GitHub Actions run [38697398048](https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38697398048) at commit `3bf5822` reports **559 passed, 1 skipped (50.32s)**. All dependency artifacts/checksums outside root package metadata and both addon copies are unchanged from baseline. Native Windows and real Cloudflare/web-client acceptance are still pending.
