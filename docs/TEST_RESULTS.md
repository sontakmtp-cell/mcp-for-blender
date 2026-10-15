# GoodMCP — kết quả kiểm thử

## PR-1 — Ticket A/B

- Baseline upstream: `7a0373ec9199183cb460068c4f96aed9c579fb4f`, Python 3.11.17, SDK `mcp==1.29.0` từ `uv.lock`, Blender 4.3.2, addon 1.8 / protocol 13.
- Baseline trước sửa: **467 passed, 6 failed, 1 skipped** (40.78s). Cả 6 lỗi ở `test_compat_matrix::test_addon_status_always_answers`: telemetry import module private `blender_mcp.config` không được cung cấp trong Git.
- Sửa hẹp: status vẫn trả dữ liệu Blender, `telemetry_consent=null` khi duy nhất module config này thiếu. Không tạo config giả hoặc vô hiệu assertions.
- Test transport: mặc định stdio, HTTP chỉ loopback, parser tách biệt socket Blender, SDK initialize/list/call thực qua subprocess cho cả stdio và HTTP, Blender offline trả lỗi rõ ràng.
- Socket: test hai thread không trộn response, tạo kết nối đầu tiên một lần, connect timeout 5s ở remote; response deadline 180s và tối đa 32 MiB (request HTTP tối đa 1 MiB).
- Chấp nhận thực tế tại Linux: Streamable HTTP `2025-11-25`, 9 tools không cần MCP Apps, `get_addon_status`, `get_scene_info`, `look` (ảnh 256px) thành công; tạo `GoodMCP_Test_Cube`, đổi màu và lưu file thử riêng; hai call đồng thời trả đúng query.
- Backup baseline và scene thử nằm ngoài Git tại `/workspace/.cloud-blender/artifacts/`; không dùng file 3D của người dùng.
- Đây là test bằng MCP Python SDK, **chưa phải MCP Inspector hoặc web-client acceptance**. Windows chưa được chạy trên máy người dùng.
- PR-1 chỉ cho phép local: **không nối Tunnel trước PR-2**.

## Quy trình test

```bash
UV_CACHE_DIR=/workspace/.cache/uv UV_PYTHON_INSTALL_DIR=/workspace/.python uv sync --frozen
UV_CACHE_DIR=/workspace/.cache/uv uv pip install --python .venv/bin/python pytest==8.4.2
DISABLE_TELEMETRY=true .venv/bin/python -m pytest -q
```

`uv sync` gỡ pytest vì upstream không khai báo dev dependencies; cài lại pytest bằng lệnh trên, không thay lockfile để giả test thành công.

## Rollback

Dừng GoodMCP/cloudflared trước. Dùng stdio như cũ (`mcp-for-blender`, không có `--transport`). Để quay lại mã cũ, lưu thay đổi cá nhân, checkout SHA baseline ở trên, `uv sync --frozen`. Không reset/xóa file `.blend`; mở lại bản backup thử khi cần. Addon không bị thay đổi.

Kết quả toàn suite sau PR-1: **486 passed, 1 skipped** (39.88s). Skip có sẵn được giữ nguyên.

## PR-1 — sửa review P1/P2 (2026-10-15)

Review: https://github.com/sontakmtp-cell/mcp-for-blender/pull/1#pullrequestreview-5529087100

- Tái hiện trên bản gốc `f1cd848`: test HTTP thật khởi chạy tool socket chậm và gửi `tools/list` độc lập thất bại bằng **TimeoutError** (1 failed, 4 deselected). Không dùng test hai Python thread thay cho kiểm thử event loop.
- Chuyển I/O đồng bộ trong async tools, callback generation/telemetry/consent sang AnyIO worker; session/progress/elicitation vẫn chạy trên event loop ban đầu. Tool/resource sync được đăng ký bằng async adapter, giữ API sync dùng nội bộ và schemas cũ.
- Giữ send/receive lock trong worker. Khi client hủy request, worker không bị abandon giữa phản hồi: drain response rồi mới nhả lock. Không tự retry lệnh ghi. Timeout đóng socket cũ và lệnh kế tiếp kết nối mới. Không hứa rollback lệnh Blender đã gửi khi hủy request.
- Lifecycle Blender chạy một lần ở process scope, không đóng socket sau từng request HTTP stateless. Shutdown chờ exchange đang chạy trước khi đóng. Mỗi screenshot dùng tên file riêng để request đồng thời không đè/xóa ảnh nhau.
- Sáu regression mới: ba tool chậm (`get_scene_info`, `execute_blender_code`, `look`) vẫn cho HTTP `tools/list` trả trong 0.8s; cancel rồi gọi tiếp không lẫn response; timeout/reconnect không replay write; hai capture có file/kết quả riêng. Timeout test rút ngân sách socket xuống 0.2s chỉ trong subprocess test, production vẫn 180s.
- Frozen install rồi toàn suite: **492 passed, 1 skipped** (43.63s). Dependency artifacts/checksums giữ nguyên; thêm AnyIO vào khai báo trực tiếp, không nâng phiên bản.
- Thêm GitHub Actions chạy frozen install + toàn suite cho PR/push, pin SHA action từ repository chính thức. Chưa coi workflow đạt trước khi GitHub trả kết quả.

### Inspector chạy trực tiếp trên nhánh PR-1 sau sửa

Dùng Inspector CLI **1.0.2**, `--transport http`, URL local `/mcp`; server chỉ bind loopback. CLI tự initialize trước discovery/call:

```text
Inspector 1.0.2 initialize/tools-list: PASS (9 tools, no Apps)
Inspector get_scene_info: PASS
Inspector look: PASS (image)
Inspector execute_blender_code/create/save disposable scene: PASS
```

Lệnh: `npx @modelcontextprotocol/inspector@1.0.2 --cli http://127.0.0.1:8765/mcp --transport http --method tools/list`; các call dùng `--method tools/call --tool-name ...`. Scene thử `GoodMCP_PR1_Review` được lưu riêng ngoài Git tại `/workspace/.cloud-blender/artifacts/pr1-review.blend`. Server HTTP đã dừng sau nghiệm thu. Đây là kết quả Inspector local, không phải xác nhận OAuth/web client/Windows.

Hostname public vẫn thuộc PR-2/3: allowlist Host/Origin dựa trên `GOODMCP_PUBLIC_URL`, giữ DNS rebinding protection. Chưa có Tunnel/Access thật để nghiệm thu xuyên Internet.

## PR-2 — Ticket C

- Origin kiểm tra Access JWT RS256 với JWKS HTTPS cố định theo team, issuer, audience, exp/iat/sub/email; so khớp đúng một email. Không dùng header email hoặc bearer tự khai làm danh tính.
- Mọi path/method HTTP đi qua auth trước dispatch. Thiếu/sai token: 401; tài khoản khác: 403; lỗi kết nối JWKS: fail closed. Không trả token hoặc stack trace.
- Remote buộc safe mode và tắt telemetry/context log, tắt log upstream có chứa raw Python; uvicorn không trust proxy headers và không access-log.
- Remote không chạy nếu thiếu cấu hình; `--local-test` chỉ dùng loopback, từ chối forwarding/Cloudflare headers. Không nối Tunnel vào chế độ này.
- Chỉ đọc mặc định: `get_addon_status`, `get_scene_info`, `look`; cả `tools/list` và `tools/call` đều áp dụng allowlist. Bật `GOODMCP_ALLOW_WRITE=1` mới cho execute/import/generate/search. UI/telemetry tool không có trong remote allowlist.
- Sửa lifecycle stateless: giữ một socket/process, không đóng kết nối dùng chung sau mỗi HTTP request; stdio giữ nguyên lifecycle cũ.
- `pyjwt[crypto]` được khai báo trực tiếp; giữ nguyên phiên bản và checksum các dependency trong lockfile. Chỉ cập nhật metadata package gốc vốn lệch 2.1.8/2.1.9.
- **Chưa nghiệm thu Cloudflare thật:** không có công cụ/account Cloudflare trong phiên này; Managed OAuth, email Allow policy, HTTPS, thu hồi phiên và RFC 8707 theo từng web client chưa được kiểm chứng. Không tự viết OAuth fallback khi chưa có lỗi tương thích thực tế.

PR-2 toàn suite: **514 passed, 1 skipped** (41.49s); sau đó thêm test tích hợp JWT→MCP→policy, toàn file auth **25 passed** (1.46s). Blender thật qua local-test: 7 tools ở write mode; status/scene/image/write/save/concurrency đều đạt. Đây không phải JWT Cloudflare thật.

## PR-3 — Ticket D/F và phần chuẩn bị Ticket E

- Máy đích do chủ sở hữu xác nhận: **Windows**. Mã được chạy/test tại Linux; không đánh tráo kết quả này thành đã chạy trên desktop Windows.
- Có `scripts/start-goodmcp.ps1`, `scripts/check-goodmcp.ps1`, `.env.example`, named-Tunnel config mẫu và README tiếng Việt. Start giữ cửa sổ mở; Ctrl+C dừng các tiến trình của chính nó, không đóng Blender. Không thêm service/dashboard/database.
- Cấu hình Tunnel phải đúng UUID + credentials path, duy nhất hostname đã chọn → `http://127.0.0.1:8765` + catch-all 404. Test chặn mọi route tới 9876, thêm hostname bypass và config sai kiểu.
- Start kiểm tra Blender trước; từ chối local-test kết hợp Tunnel; bắt buộc public Managed OAuth challenge trước chạy cloudflared. Check phân biệt addon/origin auth/public challenge. Test mô phỏng Tunnel chết, cleanup origin và startup thất bại.
- Kiểm tra log thực phát hiện uvicorn mặc định re-enable logger đã disable: truyền `log_config=None` để giữ tắt log raw Python. Đây là hiệu chỉnh sau PR-2, không coi thuộc tính logger trước startup là bằng chứng đủ.
- PowerShell **7.6.7** portable chính thức được xác minh SHA256 theo asset `hashes.sha256`, chạy trên Linux: cả hai script parse được; thử wrapper bằng fake `uv` xác minh cwd từ `/tmp`, argv chính xác và giữ exit code 17. Chưa thử PowerShell 5.1/desktop Windows thật.
- Kiểm tra socket thực: HTTP **127.0.0.1:8765**, addon **127.0.0.1:9876**; không có bind `0.0.0.0` ở hai cổng.

### Nghiệm thu bên ngoài còn chặn

| Client | Protocol works | Account/region eligible | Read/write usable | Quan sát |
|---|---|---|---|---|
| MCP Python SDK 1.29.0 | Đạt local, protocol 2025-11-25 | Không áp dụng | Đạt trên scene thử | status, scene, ảnh, execute/save, concurrency |
| MCP Inspector | Xem transcript local bên dưới | Không áp dụng | Xem transcript | Không đại diện web-client acceptance |
| Grok Web | Chưa thử | Chưa xác minh | Chưa thử | Không có phiên đăng nhập/browser hoặc connector tài khoản |
| ChatGPT Web | Chưa thử | Chưa xác minh gói/workspace | Chưa thử | Không suy ra quyền write từ Inspector |
| Gemini Web | Chưa thử | Chưa xác minh khu vực/tài khoản | Chưa thử | Không suy ra eligibility từ timezone; không thay bằng Gemini API |

Cloudflare Access policy, Managed OAuth, DNS và named Tunnel **chưa được tạo/đổi** vì phiên không có công cụ truy cập Cloudflare. Chưa biết apex đang dùng dịch vụ nào; README yêu cầu kiểm tra trước khi chọn apex/subdomain. HTTPS thật, owner login, người lạ bị chặn ở edge, revoke/refresh, Tunnel mất mạng, restart Windows và khôi phục Blender cần thử trên máy/chủ tài khoản thực. Không có bằng chứng cho phép đánh dấu các gate này đạt.

### Transcript local — Inspector và vận hành

MCP Inspector CLI **1.0.2** (nhánh v1 dành cho SDK upstream 1.x); local test, không OAuth thật:

```text
Readonly tools/list: get_addon_status, get_scene_info, look
Direct execute_blender_code in readonly: isError=true, Tool is not allowed by the GoodMCP remote policy
Inspector 1.0.2 Streamable HTTP: tools/list PASS (7 write-mode tools)
Inspector get_scene_info PASS
Inspector look PASS (image returned)
Inspector write/material/save PASS (disposable file)
Remote log payload suppression PASS
Operator start/SIGINT cleanup PASS; Blender stays running
```

Write test dùng `bpy` tạo `GoodMCP_Inspector_Test`, vật liệu Principled màu đỏ, lưu `/workspace/.cloud-blender/artifacts/inspector-test.blend`. File và backup chỉ là generated artifacts ngoài Git. Không dùng scene cá nhân. Test log xác minh chuỗi riêng trong mã Python không xuất hiện sau khi uvicorn khởi động thật; regression tự động dùng fake addon TCP để kiểm tra lại điều này qua HTTP.

Bộ kiểm tra tự động còn xác minh request >1 MiB nhận 413, Host lạ nhận 421, malformed Tunnel config bị từ chối. Diff addon gốc/bundled rỗng; mọi package dependency, version và artifact checksum ngoài metadata package gốc giữ nguyên baseline.

Kết quả PR-3 giai đoạn nghiệm thu local: **535 passed, 1 skipped** (42.28s), `git diff --check` đạt. Sau các test bổ sung, GitHub Actions tại SHA `3bf5822` xác nhận **559 passed, 1 skipped** (50.32s): https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38697398048. Các số trước là mốc lịch sử, không phải kết quả CI mới nhất. Skip có sẵn từ baseline; thay đổi addon bằng 0. HTTP local-test đã dừng; Blender thử vẫn ở loopback. Chưa mở public endpoint. PR1 đã vào `main`, PR2 đã được đưa vào `main` qua PR4; PR3 vẫn Draft và chưa merge.

### Trạng thái review

**Tình trạng ngày 2026-10-15:** [PR1](https://github.com/sontakmtp-cell/mcp-for-blender/pull/1) merged vào `main`; [PR2](https://github.com/sontakmtp-cell/mcp-for-blender/pull/2) ban đầu merged vào nhánh phụ, sau đó được đưa vào `main` bằng [PR4](https://github.com/sontakmtp-cell/mcp-for-blender/pull/4), merge SHA `6b429b0`. [PR3](https://github.com/sontakmtp-cell/mcp-for-blender/pull/3) đã đổi base về `main`, vẫn OPEN/Draft; diff so với `main` hiện còn 17 file riêng của PR3. Chưa nghiệm thu các gate Cloudflare/Windows/web AI.

### Kết quả xác minh sau review PR-1

- PR-1 commit `16a2337`: **492 passed, 1 skipped** local; GitHub Actions **success** cho chính SHA này: https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38694224302 (push) và https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38694224280 (pull_request).
- **Tại thời điểm kiểm thử lịch sử này (trước khi hợp nhất về main):** đã đưa bản sửa vào các nhánh phụ thuộc bằng merge thông thường, không force-push: PR-2 **521 passed, 1 skipped**; PR-3 frozen install + toàn suite **541 passed, 1 skipped** (47.06s). Trạng thái merge hiện tại được ghi ở mục trên.
- Cấu hình auth/allowlist Host-Origin ở PR-2/3 được giữ nguyên; sáu test concurrency mới ở các nhánh này chạy trong local-test có chủ đích. Gate Cloudflare/Windows/web AI thật vẫn chưa nghiệm thu.

## PR-2 — sửa review bảo mật P1/P2 (2026-10-15)

Review: https://github.com/sontakmtp-cell/mcp-for-blender/pull/2#pullrequestreview-5529290530

- **Tái hiện trước sửa:** HTTP `tools/call look(image=<PNG thử ngoài scene>)` trả ảnh từ Blender thật khi `GOODMCP_ALLOW_WRITE=0`. PNG được tạo cho kiểm thử trong thư mục tạm, không dùng ảnh cá nhân.
- **Boundary sau sửa:** remote dispatch đặt quyền ảnh bằng request-local ContextVar, không phải tham số client. Worker kế thừa quyền này; server ghi đè `allow_disk_images` khi tạo script. Trong Blender, nếu `bpy.data.images.get(name)` không có datablock thì từ chối trước `abspath/isfile/images.load`. Không preflight tách rời, không blacklist ký tự đường dẫn và không fallback từ ảnh bị từ chối sang viewport.
- Viewport, ảnh trong Blender (kể cả tên có slash/Unicode/giống đường dẫn) và `Render Result` vẫn hoạt động. Ảnh/datablock đã liên kết với Blender thuộc phạm vi cho phép, gồm ảnh file-backed; đây không phải sandbox filesystem của toàn Blender.
- Stdio giữ hành vi cũ. Remote bật rõ ràng `GOODMCP_ALLOW_WRITE=1` mới có quyền đọc ảnh từ đường dẫn đĩa, ngoài quyền execute/import/generate đã có. `.env.example` ghi rõ quyền này.
- Resources có allowlist riêng cho cả discovery và dispatch: HTML viewport tĩnh đi kèm và ba template `blender://object/{name}`, `blender://material/{name}`, `blender://collection/{name}`. URI khác không được liệt kê; gọi trực tiếp bị từ chối bằng lỗi -32602. Đây là dữ liệu scene/static UI, không phải file reader tùy ý.
- `.env.example` có ví dụ export các biến bắt buộc cho PowerShell: CLI PR-2 không tự nạp `.env`; Start script PR-3 có nạp, biến process hiện có được ưu tiên. Không nhúng email chủ sở hữu hay credentials vào Git.
- Thêm 18 test: HTTP thật qua policy + script LOOK thật với bpy backend tối thiểu trong CI; đường dẫn ảnh tạm bị từ chối ở readonly dù client giả `allow_disk_images=true`, write opt-in được phép; viewport/ảnh datablock/render được giữ; discovery/read resource có positive/negative controls; 11 dạng path/encoding không chạm hàm resolve/load; stdio script mặc định vẫn đọc ảnh đĩa.
- Import/syntax (`compileall`) và `git diff --check` đạt; focused suite **61 passed**. Toàn suite PR-2: **539 passed, 1 skipped** (50.56s), skip có sẵn. Review độc lập không tìm thấy đường bypass hoặc regression cụ thể trong boundary đã thay đổi.

### Kiểm chứng Blender thật sau sửa

```text
Real Blender private file: PASS denied readonly (even with forged argument)
Real Blender viewport/existing datablock/Render Result: PASS
Real Blender private file: PASS explicit write opt-in
Real Blender viewport/existing datablock/Render Result: PASS
Real stdio private test-file image access unchanged: PASS
```

`Render Result` được tạo bằng render thử 64x64 trên scene thử và khôi phục engine/resolution sau khi chuẩn bị. HTTP test chỉ dùng loopback, không có Tunnel. Gate triển khai Cloudflare/Windows/web AI thật vẫn chưa được nghiệm thu; kết quả này không xác nhận end-to-end OAuth.

### Kết quả CI và nhánh phụ thuộc sau review PR-2

- PR-2 `bcc61dd`: **539 passed, 1 skipped**; GitHub Actions **SUCCESS** cho đúng SHA: https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38697066804 và https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38697061180.
- Các file của fix: `src/blender_mcp/remote_policy.py`, `src/blender_mcp/server.py`, `src/blender_mcp/blender_scripts.py`, `tests/test_remote_image_policy.py`, `.env.example`, `docs/TEST_RESULTS.md`.
- Lệnh chính: `.venv/bin/python -m compileall -q src/blender_mcp/remote_policy.py src/blender_mcp/server.py src/blender_mcp/blender_scripts.py`; `.venv/bin/python -m pytest tests/test_access_auth.py tests/test_remote_image_policy.py tests/test_consolidated_tools.py tests/test_remote_protocol.py -q`; `DISABLE_TELEMETRY=true .venv/bin/python -m pytest -q`; `git diff --check`.
- Đã merge bản sửa vào nhánh PR-3, giữ cấu hình startup/auth/logging hiện có. Frozen install + toàn suite trên nhánh kết hợp: **559 passed, 1 skipped** (53.05s). README bổ sung phạm vi ảnh/resources. Lúc ghi kết quả này các PR chưa về `main`; nay PR1 và PR2 đã tích hợp, PR3 vẫn chờ.

### Kiểm tra tích hợp sau review PR-3

- PR4 (mang riêng 15 file PR2 vào `main`) đã merge thành công ở commit `6b429b0477f1a3bd143b00b2bb8391f90f5e92f4`; CI cho [PR tích hợp](https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38698925556) báo **success** trước merge.
- PR3 hiện base là `main`, chỉ còn 17 file khác biệt phục vụ vận hành Windows và tài liệu. Việc đổi base và cập nhật tài liệu kích hoạt kiểm tra GitHub Actions mới; kết quả từng lần kiểm tra cần xem ở tab **Checks** của [PR3](https://github.com/sontakmtp-cell/mcp-for-blender/pull/3).
- Đây là xác minh tích hợp source code. Chưa có Cloudflare Tunnel public, Windows thực tế hoặc web-client E2E; không coi pass CI là nghiệm thu dịch vụ trực tuyến.
