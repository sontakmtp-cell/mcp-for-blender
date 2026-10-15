# GoodMCP — Kế hoạch triển khai cho coding agent

**Ngày lập:** 2026-10-15  
**Upstream:** https://github.com/sontakmtp-cell/mcp-for-blender  
**Mục tiêu:** Biến MCP for Blender thành **một remote MCP server** ở `https://goodmcp.si/mcp`, dùng máy tính đang chạy Blender, có thể được các web AI có hỗ trợ custom MCP kết nối. **Chỉ một người dùng**.

## 0. Điều kiện thực tế và giới hạn sản phẩm

- **ChatGPT Web:** Custom MCP hỗ trợ trên web, nhưng tính năng viết/chỉnh sửa qua custom MCP hiện dành cho Business, Enterprise/Edu; Pro chủ yếu đọc/fetch. Không coi việc server chạy tốt là bằng chứng ChatGPT cá nhân được phép chỉnh Blender. Nguồn: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt
- **Gemini Web:** Custom MCP Connected Apps hiện yêu cầu đủ 18 tuổi, ở Mỹ, tài khoản Google cá nhân, Keep Activity bật, giao diện tiếng Anh. Nếu tài khoản không đủ điều kiện, đánh dấu **blocked by platform**, không tìm cách lách. Nguồn: https://support.google.com/gemini/answer/17209137
- **Grok Web:** Hỗ trợ custom MCP URL và xác thực, yêu cầu endpoint từ Internet. Nguồn: https://docs.x.ai/grok/connectors
- **Cloudflare Managed OAuth:** Ưu tiên thay tự viết OAuth. Yêu cầu client tương thích RFC 8707 và **origin xác minh JWT**; phải thử riêng từng web client, không giả định tương thích. Nguồn: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/managed-oauth/
- DNS đã kết nối Cloudflare nhưng **chưa đồng nghĩa đã có Cloudflare Tunnel**. Cần tạo named tunnel ổn định.

## 1. Phạm vi và nguyên tắc

**Trong phạm vi:** giữ Blender addon hiện tại, giữ các Blender tool hiện có, thêm Streamable HTTP, bảo vệ bằng Cloudflare Access + Managed OAuth nếu tương thích, Cloudflare Tunnel, một lệnh khởi động, test và README tiếng Việt.

**Ngoài phạm vi:** VPS, Docker bắt buộc, Kubernetes, database ngoài, dashboard quản trị, tính năng nhiều người dùng, thu phí, viết lại Blender addon, làm 3 server khác nhau, xây website mới, vượt giới hạn tài khoản/khu vực từ nền tảng AI.

**Ưu tiên:** tương thích stdio cũ > an toàn local > số dòng code mới ít > vận hành đơn giản. Không push trực tiếp upstream; làm trên fork riêng và mở PR theo giai đoạn. Chủ repo upstream hiện không cấp quyền ghi cho kết nối hiện tại.

## 2. Kiến trúc mục tiêu

```text
ChatGPT Web / Gemini Web / Grok Web (nền tảng đủ điều kiện)
                   |
                   | HTTPS + OAuth
                   v
           https://goodmcp.si/mcp
                   |
      Cloudflare Access (allowlist 1 email)
      Cloudflare Managed OAuth (nếu client tương thích)
                   |
            Cloudflare Named Tunnel
                   |
             127.0.0.1:8765
             Python FastMCP server
                   |
          TCP 127.0.0.1:9876
                   |
              Blender addon
                   |
              Blender desktop
```

- **9876**: cổng socket giữa Blender addon và MCP server, như upstream. Chỉ local.
- **8765**: cổng HTTP mới cho remote MCP, chỉ bind `127.0.0.1`.
- **/mcp**: endpoint Streamable HTTP. Không dùng deprecated SSE làm nền tảng mới.
- Giữ **một phiên Blender** trong bản đầu. Máy tắt/Blender đóng thì yêu cầu có lỗi rõ ràng, không cố khởi động Blender từ cloud.
- Nếu domain apex `goodmcp.si` đang chạy dịch vụ khác, dùng `https://mcp.goodmcp.si/mcp` và cập nhật tất cả cấu hình/tài liệu cho nhất quán; không phá DNS sẵn có.

## 3. Kết quả kiểm tra mã nguồn upstream

- `pyproject.toml`: phiên bản kiểm tra là **2.1.9**, dùng `mcp>=1.26.0,<2`; script CLI `mcp-for-blender = blender_mcp.server:main`.
- `src/blender_mcp/server.py`: dùng `mcp.server.fastmcp.FastMCP`; `mcp.run()` mặc định stdio tại cuối `main()`; có `BlenderConnection` và lock cho socket; `parse_connection_args()` dành cho `--host/--port` **của Blender**, không được tái sử dụng những tên này cho HTTP.
- `addon.py`: Blender addon và TCP listener; không cần sửa nếu giao tiếp TCP cũ chạy ổn.
- `src/blender_mcp/openai_apps.py`: có viewport/ứng dụng bổ sung cho các client hỗ trợ; **không** coi tương thích UI là điều kiện tiên quyết. MCP tools phải chạy được không cần UI.
- `src/blender_mcp/safe_mode.py`: có `BLENDER_MCP_SAFE_MODE=1`, hiện **opt-in**, không phải sandbox bảo đảm an toàn tuyệt đối. `execute_blender_code` có khả năng chạy Python trong Blender.
- `tests/`: đã có test kết nối, an toàn, OpenAI UI, threading. Bắt buộc chạy baseline trước khi sửa.

## 4. Backlog triển khai — agent làm theo thứ tự

### Ticket A — Baseline, phương án quay lại

**Đầu vào:** upstream, commit SHA pin tại thời điểm bắt đầu, hệ điều hành thật đang chạy Blender.

**Agent thực hiện:**
1. Kiểm tra quyền GitHub.
2. Tạo nhánh `feat/goodmcp-remote` và tệp `docs/GOODMCP_PLAN.md` từ kế hoạch này.
3. `uv sync --frozen` và `uv run pytest -q` (hoặc lệnh test phù hợp mà repo khai báo). Lưu kết quả baseline; nếu upstream test fail, ghi rõ lỗi có sẵn, không che giấu.
4. Sao lưu `.blend` thử nghiệm và ghi phiên bản Blender + addon; không test bằng dự án 3D quan trọng.

**Hoàn thành khi:** có nhánh làm việc, SHA baseline, test baseline, không sửa upstream và có chỉ dẫn rollback về tag/commit cũ.

### Ticket B — Thêm remote Streamable HTTP, không phá stdio

**File chính:** `src/blender_mcp/server.py`; thêm test `tests/test_remote_transport.py`.

**Agent thực hiện:**
1. Thêm `--transport stdio|streamable-http` (mặc định `stdio`), `--http-host` (mặc định `127.0.0.1`), `--http-port` (mặc định `8765`). Có thể thêm biến môi trường `GOODMCP_TRANSPORT`, `GOODMCP_HTTP_HOST`, `GOODMCP_HTTP_PORT` nếu thực sự đơn giản.
2. Giữ nguyên `--host`, `--port`, `BLENDER_HOST`, `BLENDER_PORT` cho socket Blender; cập nhật parser tránh xung đột.
3. Dùng **MCP Python SDK đã pin trong repo** để chạy Streamable HTTP tại `/mcp`; ưu tiên stateless HTTP phù hợp, kiểm tra phiên bản SDK thực tế, không bịa API.
4. Tái sử dụng **cùng một FastMCP instance, các tools, resources, metadata, socket manager**. Không nhân đôi business logic hoặc tạo nhiều socket trùng lặp.
5. Xem lại lifecycle, lỗi mất kết nối, lock socket, timeout 180 giây, xử lý các tool lâu; không để HTTP requests đồng thời làm lệch phản hồi socket.
6. Đảm bảo không phụ thuộc MCP Apps UI: tool list, `get_addon_status`, `get_scene_info`, `look`, `execute_blender_code` vẫn chạy ở client thông thường.
7. Các tool tạo file/render/generate lâu cần giới hạn payload, lỗi rõ ràng; không thêm background queue ở MVP nếu chưa cần.

**Kiểm thử:**
- Lệnh CLI mặc định vẫn giao tiếp stdio; test cũ không regress.
- Chạy remote, Inspector Streamable HTTP kết nối `http://127.0.0.1:8765/mcp`, `initialize`, `tools/list`, `tools/call` thành công.
- Không có HTTP listener ở `0.0.0.0` theo mặc định.
- Hai yêu cầu đồng thời không trộn kết quả; đóng Blender sẽ báo lỗi có nghĩa, không treo vô hạn.

**Hoàn thành khi:** `uv run pytest -q` xanh và Inspector gọi được tool local.

### Ticket C — Bảo vệ remote endpoint (bắt buộc trước khi nối Internet)

**Khuyến nghị chính: Cloudflare Access + Managed OAuth**, không tự viết OAuth nếu chưa cần.

**Agent thực hiện:**
1. Chuẩn bị tài liệu thiết lập Cloudflare Access **self-hosted application** bảo vệ `goodmcp.si` (hoặc subdomain MCP), policy Allow **duy nhất email của chủ sở hữu**, Deny còn lại; bật MFA nếu có.
2. Bật **Managed OAuth** theo tài liệu Cloudflare; xác minh client hỗ trợ RFC 8707. Tất cả endpoint `GET/POST/DELETE /mcp` phải được bảo vệ; không mở đường bypass qua path khác.
3. Thêm middleware tại origin để **xác minh `Cf-Access-Jwt-Assertion`** (chữ ký/JWKS, audience, issuer, expiration, email cho phép), không chỉ tin vào header tự khai hoặc email do client gửi. Nếu chạy local direct không có Access JWT thì remote mode từ chối, trừ chế độ test local rõ ràng chỉ trên loopback.
4. Không ghi token, mã xác thực, header Authorization, mã Python nhạy cảm vào log công khai. Không hardcode email/token vào repo; dùng `.env.example`, tệp bí mật thực đưa vào `.gitignore`.
5. Bật `BLENDER_MCP_SAFE_MODE=1` cho chế độ remote. Kiểm tra giới hạn: code an toàn theo AST nhưng vẫn có thể save/import/export bằng `bpy`; đây không phải hệ thống cách ly file thực sự. Cân nhắc chế độ đầu `read-only`, chỉ bật `execute_blender_code` sau khi kiểm tra và sao lưu cảnh.
6. Nếu cần danh sách tool được phép, **kiểm soát ở cả discovery và thực thi `tools/call`**, không chỉ ẩn khỏi `tools/list`.
7. Xử lý lỗi 401/403 rõ ràng. Tự xác minh bằng test: không token, token giả, hết hạn, sai audience, email không được phép đều bị từ chối.

**Fallback chỉ khi Managed OAuth thất bại với client cần thiết:** sử dụng một thư viện OAuth MCP được duy trì (ví dụ FastMCP OAuth Proxy tích hợp nhà cung cấp danh tính), có OAuth discovery, DCR, PKCE S256, token/refresh token và hạn chế đăng nhập chỉ một tài khoản. Không tự hand-roll OAuth từ đầu. Tránh chạy đồng thời Managed OAuth và OAuth riêng cho cùng URL.

**Hoàn thành khi:** endpoint công khai trả từ chối cho người lạ; chủ sở hữu đăng nhập được; không có con đường thực thi Blender không xác thực.

### Ticket D — Cloudflare Named Tunnel + domain

**Agent thực hiện cùng chủ sở hữu (không yêu cầu gửi mật khẩu/secret vào chat):**
1. Trên Cloudflare dashboard tạo **named tunnel `goodmcp-blender`**, cài `cloudflared` trên đúng máy đang chạy Blender.
2. Public hostname `goodmcp.si` (hoặc `mcp.goodmcp.si`) -> HTTP service `http://127.0.0.1:8765`; giữ Cloudflare proxied. Không forward cổng router, không public cổng socket 9876.
3. Đặt Cloudflare Access policy **trước khi mở cho các web client**; kiểm tra HTTPS và endpoint `/mcp`.
4. Chọn chế độ chạy `cloudflared` ổn định (service nền theo OS) và server Python khởi động bằng script. Máy tắt là offline bình thường.
5. Tạo các script theo OS đã phát hiện: `scripts/start-goodmcp.ps1` hoặc `scripts/start-goodmcp.sh`, `scripts/check-goodmcp.*`; không bắt buộc Docker.

**Hoàn thành khi:** địa chỉ HTTPS ổn định sau khởi động lại, không yêu cầu IP tĩnh, kiểm tra unauthorized bị chặn, máy tính tắt thì endpoint không truy cập được Blender.

### Ticket E — Tương thích từng web AI (cổng nghiệm thu tách biệt)

**Grok Web:** https://grok.com/connectors -> New Connector -> Custom -> nhập URL `https://goodmcp.si/mcp`, hoàn tất đăng nhập. Kiểm tra get_scene_info -> look -> thay đổi cube (nếu write được). Ghi lại trạng thái thực tế.

**ChatGPT Web:** Nếu tài khoản/workspace được quyền: Plugins -> Add custom MCP server -> URL, auth -> test. Với tài khoản chỉ có read/fetch, không hứa chạy tạo/chỉnh mô hình; ghi `blocked by plan for write`. Nguồn: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

**Gemini Web:** Chỉ thử giao diện Gemini Connected Apps -> Custom apps nếu tài khoản đủ điều kiện khu vực/tính năng. Nếu tính năng không hiện, ghi `blocked by geographic/account eligibility`, không sửa MCP vô ích. Có thể thử **Gemini API Interactions remote MCP** như lựa chọn **khác Gemini Web**, phải ghi rõ là API, không được đánh tráo nghiệm thu. Nguồn: https://support.google.com/gemini/answer/17209137 và https://ai.google.dev/gemini-api/docs/function-calling

**Test case chung:**
1. Hỏi danh sách object/scene hiện có.
2. Chụp `look`/viewport để kiểm tra kết quả phản hồi ảnh.
3. Tạo cube mới, đặt tên `GoodMCP_Test_Cube`, thay đổi màu (chỉ khi nền tảng cấp quyền write).
4. Save bản thử vào thư mục riêng, không ghi đè file thật.
5. AI khác đọc lại cùng một scene sau khi client đầu tiên sửa, kiểm tra đồng bộ.
6. Đóng Blender rồi gọi tool -> thông báo rõ; mở lại Blender -> kết nối được.
7. Thu hồi phiên/Access -> yêu cầu tiếp theo bị từ chối.
8. Thử hai lệnh đồng thời -> không trộn kết quả; tool bị giới hạn không bị gọi lén qua `tools/call`.

**Bảng nghiệm thu** phải có 3 cột độc lập `Protocol works`, `Account/region eligible`, `Read/write usable` + lỗi quan sát thực tế và ảnh chụp thử nghiệm. **Không coi test MCP Inspector là chứng minh web client hoạt động.**

### Ticket F — Vận hành một người dùng + bàn giao

**File yêu cầu:** `README_GOODMCP_VI.md`, `.env.example`, script theo OS, `docs/TEST_RESULTS.md`; test tự động của các phần đã thay đổi.

**README cần có:**
1. Điều kiện trước khi chạy (Blender, addon, Python/uv, cloudflared, domain/Cloudflare).
2. Cách cài 1 lần và cách Start/Stop mỗi ngày.
3. URL duy nhất dùng trên các web AI; danh sách tính năng khả dụng theo gói/địa lý.
4. Các trạng thái thường gặp: Blender offline, tunnel offline, auth fail, tool call timeout, OAuth login lại.
5. Sao lưu `.blend`, cách tắt quyền truy cập nhanh (disable Access app/tunnel), cách rollback.
6. Ảnh chụp hoặc transcript chứng minh Inspector + mỗi web client được thử.

**Hoàn thành khi:** người không biết lập trình đọc README vẫn có thể bật Blender + GoodMCP và xác định dịch vụ hoạt động hay không.

## 5. Bộ tiêu chí chấp nhận tổng thể

- [ ] Tồn tại một MCP Streamable HTTP endpoint `https://goodmcp.si/mcp` (hoặc subdomain thống nhất).
- [ ] Stdio upstream vẫn chạy bình thường (regression tests).
- [ ] Blender addon và socket 9876 không bị đưa lên Internet.
- [ ] Cloudflare Access chỉ cho phép chủ sở hữu; local origin có JWT verification đúng.
- [ ] `BLENDER_MCP_SAFE_MODE=1` trên remote; giải thích rõ giới hạn an toàn.
- [ ] MCP Inspector thực thi được read + thay đổi an toàn trên **file thử**.
- [ ] Tối thiểu Grok Web được thử; ChatGPT/Gemini được kiểm tra tính đủ điều kiện và ghi rõ kết quả, không báo thành công giả.
- [ ] Test invalid auth/expired/wrong audience, concurrent calls, Blender down, tunnel down.
- [ ] Có hướng dẫn tiếng Việt, quy trình Start/Stop/rollback và không lộ secrets lên GitHub.

## 6. Thứ tự PR đề xuất

| PR | Nội dung | Không nên làm kèm |
|---|---|---|
| PR-1 | Baseline + transport Streamable HTTP + tests; giữ stdio | Không kết nối Internet khi chưa có auth |
| PR-2 | Origin JWT validation + Cloudflare Access/Managed OAuth + security tests | Không tự viết OAuth trừ khi test xác nhận cần |
| PR-3 | Tunnel cấu hình, startup scripts, README, end-to-end test results | Không tạo thêm dashboard/web app |

Chạy test và review mỗi PR. Chỉ merge nếu test xanh và đáp ứng check bảo mật.

## 7. Prompt giao agent (dán nguyên đoạn này)

> Bạn là coding agent phụ trách dự án GoodMCP. Hãy đọc `docs/GOODMCP_PLAN.md` trước. Fork `sontakmtp-cell/mcp-for-blender` vào repo có quyền ghi, pin commit upstream, chạy baseline. Thực hiện tuần tự Ticket A → F; giữ nguyên stdio và Blender addon tối đa; thêm Streamable HTTP tại `/mcp` trên `127.0.0.1:8765` và dùng `goodmcp.si` với Cloudflare Named Tunnel. Chỉ mở Internet sau khi Cloudflare Access + Managed OAuth và xác thực JWT ở origin đạt test. Tuyệt đối không để cổng Blender TCP 9876 trên Internet và không commit secrets. Tận dụng `BLENDER_MCP_SAFE_MODE=1`, không coi nó là sandbox tuyệt đối. Kiểm tra ChatGPT/Gemini/Grok Web theo giới hạn tài khoản và khu vực thật; đánh dấu blocked nếu nền tảng không cho dùng, tuyệt đối không báo thành công giả. Mỗi ticket có test, đầu ra, ghi chú thay đổi và điều kiện nghiệm thu. Không tạo VPS, database, dashboard hay hệ thống đa người dùng. Bắt đầu bằng PR-1, báo cáo kết quả mỗi PR trước khi tiếp tục.

## 8. Link tham khảo

- Upstream: https://github.com/sontakmtp-cell/mcp-for-blender
- OpenAI custom MCP: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt
- Gemini custom apps: https://support.google.com/gemini/answer/17209137
- Grok custom connectors: https://docs.x.ai/grok/connectors
- Cloudflare Tunnel: https://developers.cloudflare.com/tunnel/get-started/
- Cloudflare Managed OAuth: https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/managed-oauth/
- MCP remote transport: https://developers.cloudflare.com/agents/model-context-protocol/protocol/transport/
- MCP Inspector: https://github.com/modelcontextprotocol/inspector
