# Review ba PR GoodMCP

Theo chỉ dẫn bổ sung của chủ sở hữu: dùng repository `sontakmtp-cell/mcp-for-blender` hiện tại, **không fork**, máy đích **Windows**. Kế hoạch gốc vẫn được lưu nguyên để đối chiếu; chỉ dẫn mới này thay bước fork. Email Access cấu hình ngoài Git.

Ba Draft PR đã mở, được xác minh trạng thái OPEN và base/head qua GitHub API. Các nhánh nối tiếp để mỗi diff chỉ gồm giai đoạn tương ứng; chưa merge vào `main`.

| PR | Base | Head | Nội dung review |
|---|---|---|---|
| [#1](https://github.com/sontakmtp-cell/mcp-for-blender/pull/1) | `main` | `feat/goodmcp-remote` | [PR1](pr/PR1.md), Ticket A/B |
| [#2](https://github.com/sontakmtp-cell/mcp-for-blender/pull/2) | `feat/goodmcp-remote` | `feat/goodmcp-access` | [PR2](pr/PR2.md), Ticket C |
| [#3](https://github.com/sontakmtp-cell/mcp-for-blender/pull/3) | `feat/goodmcp-access` | `feat/goodmcp-operations` | [PR3](pr/PR3.md), Ticket D–F |

Phép kiểm tra `/user` ban đầu trả Forbidden; thao tác tạo/đọc PR trong repository bằng binding GitHub hiện có vẫn thành công. Không cần fork, token mới hoặc người dùng tạo PR thủ công.

Sau khi merge một PR, đổi base của PR kế tiếp về `main` nếu GitHub chưa tự đổi, kiểm tra lại diff và chạy regression trước merge. Giữ PR-2/3 ở draft khi các gate Cloudflare thật còn chưa nghiệm thu. Không nối Internet từ riêng nhánh PR-1. Xem [kết quả test và blocker](TEST_RESULTS.md).
