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
