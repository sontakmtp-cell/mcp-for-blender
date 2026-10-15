# Review ba PR GoodMCP

Theo chỉ dẫn bổ sung của chủ sở hữu: dùng repository `sontakmtp-cell/mcp-for-blender` hiện tại, **không fork**, máy đích **Windows**. Kế hoạch gốc vẫn được lưu nguyên để đối chiếu; chỉ dẫn mới này thay bước fork. Email Access cấu hình ngoài Git.

Ba nhánh được xếp nối tiếp để mỗi diff chỉ gồm giai đoạn tương ứng. Chưa merge vào `main`.

| PR dự kiến | Base | Head | Nội dung review |
|---|---|---|---|
| 1 | `main` | `feat/goodmcp-remote` | [PR1](pr/PR1.md), Ticket A/B |
| 2 | `feat/goodmcp-remote` | `feat/goodmcp-access` | [PR2](pr/PR2.md), Ticket C |
| 3 | `feat/goodmcp-access` | `feat/goodmcp-operations` | [PR3](pr/PR3.md), Ticket D–F |

Git HTTPS đọc/push nhánh thành công. GitHub API bị proxy mạng từ chối CONNECT 403 cho `api.github.com`; chưa thể tạo đối tượng Pull Request hoặc lấy số PR. Các link dưới đây là **link tạo/review diff**, không phải PR đã mở:

1. https://github.com/sontakmtp-cell/mcp-for-blender/compare/main...feat/goodmcp-remote?expand=1
2. https://github.com/sontakmtp-cell/mcp-for-blender/compare/feat/goodmcp-remote...feat/goodmcp-access?expand=1
3. https://github.com/sontakmtp-cell/mcp-for-blender/compare/feat/goodmcp-access...feat/goodmcp-operations?expand=1

Khi GitHub API được phép và binding hiện có hoạt động, chạy lần lượt từ repository:

```bash
gh pr create --draft --base main --head feat/goodmcp-remote --title 'GoodMCP 1/3: loopback Streamable HTTP, preserve stdio' --body-file docs/pr/PR1.md
gh pr create --draft --base feat/goodmcp-remote --head feat/goodmcp-access --title 'GoodMCP 2/3: single-owner Cloudflare Access verification' --body-file docs/pr/PR2.md
gh pr create --draft --base feat/goodmcp-access --head feat/goodmcp-operations --title 'GoodMCP 3/3: Windows operations and Vietnamese handoff' --body-file docs/pr/PR3.md
```

Sau khi merge một PR, đổi base của PR kế tiếp về `main` nếu GitHub chưa tự đổi, kiểm tra lại diff và chạy regression trước merge. Không merge PR-2/3 khi các gate Cloudflare thật còn chưa nghiệm thu. Không nối Internet từ riêng nhánh PR-1.
