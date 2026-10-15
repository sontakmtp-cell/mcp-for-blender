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
