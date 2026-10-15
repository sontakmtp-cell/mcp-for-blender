Protects the loopback HTTP adapter with Cloudflare Access JWT signature/JWKS, issuer, audience, expiry and single-owner email validation on all HTTP routes/methods. Remote refuses missing configuration; explicit loopback-only test mode rejects proxy headers. Read-only policy is enforced at discovery and dispatch, safe mode is mandatory, and logs containing upstream Python payloads are suppressed.

The stateless SDK request lifecycle now preserves one process-scoped Blender connection. Stdio and the Blender addon remain unchanged.

Security tests cover real RSA signatures, missing/forged/expired/wrong-issuer/wrong-audience/wrong-owner tokens, fail-closed key errors, direct tools/call denial, Host validation, and process lifecycle. Live Blender read/image/write/save/concurrent checks also passed in explicit local test mode.

Cloudflare Access application, Managed OAuth, public HTTPS, session revocation, and web-client RFC 8707 compatibility remain unverified: no Cloudflare account tools are connected. This change must not be treated as a completed Internet deployment.
