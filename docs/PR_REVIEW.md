# GoodMCP — tình trạng review và nhánh GitHub

Cập nhật **2026-10-15**. Repository sử dụng: `sontakmtp-cell/mcp-for-blender`; máy đích **Windows**. Mọi thông tin đăng nhập, Cloudflare credential và email chủ sở hữu đều nằm ngoài Git.

| PR | Trạng thái | Đích/đầu ra thực tế | Nội dung |
|---|---|---|---|
| [#1](https://github.com/sontakmtp-cell/mcp-for-blender/pull/1) | Đã merge | `main`, merge SHA `aa8074e` | Streamable HTTP, vẫn giữ stdio; [chi tiết](pr/PR1.md) |
| [#2](https://github.com/sontakmtp-cell/mcp-for-blender/pull/2) | Đã merge vào nhánh phụ | `feat/goodmcp-remote`, merge SHA `fdd44b8` | Cloudflare Access JWT, phân quyền remote, các test bảo mật; [chi tiết](pr/PR2.md) |
| [#4](https://github.com/sontakmtp-cell/mcp-for-blender/pull/4) | **Đã merge vào main** | `main`, merge SHA `6b429b0` | PR tích hợp riêng 15 file từ PR2 để sửa sai đích merge |
| [#3](https://github.com/sontakmtp-cell/mcp-for-blender/pull/3) | **OPEN / Draft**, chưa merge | Base đã đổi về `main`; head `feat/goodmcp-operations` | Launcher Windows, Tunnel, tài liệu và nghiệm thu; [chi tiết](pr/PR3.md) |

Sau khi merge PR4, so sánh `main...feat/goodmcp-operations` còn **17 file** thuộc giai đoạn PR3; mã của PR2 (`access.py`, `remote_policy.py`) đã ở `main`. Không merge PR3 nếu CI sau cập nhật không xanh hoặc diff phát sinh nội dung ngoài phạm vi.

**CI có bằng chứng:** PR1 [492 passed / 1 skipped](https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38694224302); PR2 [539 passed / 1 skipped](https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38697066804); PR3 tại SHA `3bf5822` [559 passed / 1 skipped](https://github.com/sontakmtp-cell/mcp-for-blender/actions/runs/38697398048). Những số 486, 514, 535 trong [lịch sử test](TEST_RESULTS.md) là lần chạy **trước khi cập nhật** chứ không phải báo cáo CI cuối cùng.

**Chưa triển khai public:** Cloudflare Access policy, Managed OAuth trên tài khoản thật, Windows desktop, HTTPS/Tunnel và kết nối ChatGPT/Gemini/Grok Web chưa có kết quả E2E. Không bật Tunnel hoặc chuyển PR3 thành công bố production-ready chỉ vì kiểm thử local xanh.
