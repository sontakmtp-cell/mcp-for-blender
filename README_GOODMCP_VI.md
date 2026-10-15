# GoodMCP — Blender cá nhân qua Remote MCP

GoodMCP bổ sung Streamable HTTP cho MCP for Blender, giữ addon và cách dùng stdio cũ. Một người dùng, một máy Windows chạy Blender, một scene dùng chung. Không cần VPS, Docker, database hoặc website mới.

**Trạng thái bàn giao:** mã nguồn và kiểm thử local đã có. Domain/Tunnel/Access, đăng nhập OAuth và các web AI chưa được nghiệm thu trên tài khoản thật. Xem [kết quả và phần còn chặn](docs/TEST_RESULTS.md). Chưa có bằng chứng `https://goodmcp.si/mcp` đã được triển khai.

## 1. Cần chuẩn bị

Trên **chính máy Windows đang chạy Blender**:

- Blender 3.0+, khuyến nghị phiên bản đang dùng với addon upstream; Python 3.11 do uv quản lý.
- `uv` từ [trình cài chính thức](https://docs.astral.sh/uv/getting-started/installation/), Git và PowerShell.
- `cloudflared` từ [Cloudflare](https://developers.cloudflare.com/tunnel/get-started/).
- Quyền quản lý domain và Cloudflare Zero Trust; email chủ sở hữu dùng được với nhà cung cấp đăng nhập.
- Addon MCP for Blender đã bật, **Start MCP Server**, cổng socket `127.0.0.1:9876`.

Máy cloud kiểm thử Linux không thay thế máy Windows của bạn. GoodMCP không tự mở Blender từ cloud. Khi máy ngủ/tắt hoặc Blender đóng, mô hình 3D không truy cập được.

## 2. Cài một lần

Sau khi review và merge lần lượt 3 PR, clone repository vào máy Windows rồi mở PowerShell tại thư mục đó:

```powershell
uv sync --frozen
Copy-Item .env.example .env
notepad .env
```

Điền cấu hình **chỉ trên máy bạn**:

| Biến | Giá trị cần điền |
|---|---|
| `GOODMCP_PUBLIC_URL` | `https://goodmcp.si/mcp` |
| `GOODMCP_ACCESS_TEAM_DOMAIN` | Hostname tổ chức, ví dụ `my-team.cloudflareaccess.com`, không có `https://` |
| `GOODMCP_ACCESS_AUD` | Application Audience (AUD) của ứng dụng Access |
| `GOODMCP_ALLOWED_EMAIL` | Duy nhất email chủ sở hữu đã chọn |
| `GOODMCP_ALLOW_WRITE` | Ban đầu giữ `0` |
| `GOODMCP_TUNNEL_CONFIG` | Đường dẫn tuyệt đối đến config Tunnel riêng trên Windows |

Giữ `BLENDER_HOST=127.0.0.1`, `BLENDER_PORT=9876`. Remote luôn buộc `BLENDER_MCP_SAFE_MODE=1` và tắt telemetry, bất kể biến cũ. Biến môi trường có sẵn ưu tiên hơn `.env`; kiểm tra không còn giá trị cũ khi đổi tài khoản/domain.

`.env`, `.goodmcp/`, `.cloudflared/` bị Git bỏ qua. Không đưa JWT, OAuth token, tunnel token, `cert.pem`, credential JSON hoặc scene thật vào commit/PR/ảnh chụp. Trình chạy không cần API token Cloudflare.

## 3. Đặt Access trước khi mở Tunnel

Trong **Zero Trust → Access controls → Applications**:

1. Tạo **Self-hosted application** cho **toàn hostname** `goodmcp.si`, không giới hạn riêng path `/mcp`. Mọi GET/POST/DELETE và path phụ đều phải được bảo vệ.
2. Thêm một policy **Allow → Emails → duy nhất email chủ sở hữu**, cùng email trong `.env`. Mọi email không khớp bị Access từ chối mặc định. Không thêm Bypass, Everyone hoặc Service Auth.
3. Bật MFA tại nhà cung cấp danh tính nếu có. Chọn phiên ngắn khi nghiệm thu.
4. Trong **Advanced settings → Managed OAuth**, bật tính năng và Save. Giới hạn redirect URI theo từng client thực tế; chỉ bật localhost/loopback cho Inspector local khi cần. Không dùng wildcard redirect cho mọi dịch vụ.
5. Sao chép **AUD** và team domain vào `.env`. Mỗi request origin kiểm tra chữ ký RS256/JWKS, issuer, audience, exp/iat/sub và email. Chỉ gửi `Authorization` trực tiếp tới origin không đủ để đăng nhập.

Cloudflare cấp **opaque OAuth access token** cho client và đổi nó thành `Cf-Access-Jwt-Assertion` đã ký khi forward về origin. Không dán opaque token vào header JWT, không tự tạo OAuth server khác. Managed OAuth yêu cầu client hỗ trợ RFC 8707.

Nguồn chính thức: [Managed OAuth](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/managed-oauth/); nội dung cũng được kiểm tra qua [source tài liệu Cloudflare](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/cloudflare-one/access-controls/applications/http-apps/managed-oauth.mdx). Policy thật vẫn cần kiểm tra bằng tài khoản của bạn.

## 4. Tạo named Tunnel trên máy Windows

Trước khi thay DNS, xem hostname hiện tại trong Cloudflare. Nếu apex `goodmcp.si` đang phục vụ dịch vụ khác, chọn **`mcp.goodmcp.si`** và đổi đồng thời `GOODMCP_PUBLIC_URL`, hostname Access và hostname config Tunnel. Chỉ nhập một URL đã chọn vào mọi web AI. Không ghi đè DNS đang hoạt động.

```powershell
cloudflared tunnel login
cloudflared tunnel create goodmcp-blender
```

Lệnh mở trình duyệt đăng nhập, lưu credential tại máy bạn và hiển thị UUID. Không gửi credential vào chat. Sao chép `docs/cloudflared/config.example.json` tới `$HOME\.cloudflared\goodmcp.json`, sửa UUID, đường dẫn credential JSON do lệnh create sinh ra, và hostname đã chọn. JSON là một tập con của YAML mà cloudflared đọc; giữ đuôi `.json` cho bộ kiểm tra GoodMCP.

Config chỉ gồm:

- `tunnel`: UUID thật của named tunnel `goodmcp-blender`.
- `credentials-file`: file riêng do cloudflared tạo, ngoài repository.
- `ingress`: hostname đã chọn → `http://127.0.0.1:8765`, cuối cùng `http_status:404`.

Điền đường dẫn config vào `.env`, rồi kiểm tra cấu hình:

```powershell
cloudflared tunnel --config "$HOME\.cloudflared\goodmcp.json" ingress validate
cloudflared tunnel route dns goodmcp-blender goodmcp.si
```

Nếu đã chọn subdomain, dùng `mcp.goodmcp.si` trong lệnh DNS. Không dùng tùy chọn ghi đè record sẵn có. Giữ DNS proxied. Không forward cổng router, không dùng Quick Tunnel; không đặt service `tcp://...:9876` hoặc `http://...:9876`.

Trình Start kiểm tra Access/Managed OAuth challenge của hostname **trước** khi chạy connector. Nếu Access chưa trả 401 kèm `resource_metadata`, trình Start sẽ dừng. Một challenge chưa chứng minh policy email đúng: vẫn phải thử chủ sở hữu và email khác.

## 5. Start, Check và Stop hằng ngày

Mở bản sao `.blend` dùng thử, bật addon/Start MCP Server, sau đó:

```powershell
.\scripts\start-goodmcp.ps1
```

Lệnh giữ cửa sổ PowerShell mở, kiểm tra Blender, chạy origin chỉ tại `127.0.0.1:8765`, kiểm tra origin chặn thiếu JWT rồi chạy named Tunnel. Chỉ một phiên GoodMCP; hãy dừng phiên cũ trước. **Ctrl+C** dừng origin/Tunnel do cửa sổ này mở, để Blender tiếp tục chạy. Không chạy thêm cloudflared service trùng cùng config trong chế độ này.

Ở cửa sổ PowerShell khác:

```powershell
.\scripts\check-goodmcp.ps1
```

Ba phép kiểm tra: addon trả lời trên loopback; origin từ chối người chưa xác thực; public endpoint trả Managed OAuth challenge. Sau đó phải đăng nhập bằng Inspector để xác minh tools thật. Log riêng ở `.goodmcp/server.log`; không đăng log/ảnh chứa thông tin cá nhân công khai.

Named Tunnel giữ UUID/hostname qua lần khởi động tiếp theo, không cần IP tĩnh. Khi Windows restart, mở Blender và chạy lại Start. Chưa cấu hình Windows Service/Task Scheduler và chưa nghiệm thu tự khởi động lại; MVP dùng một cửa sổ chủ động để bật/tắt.

### Thử local trước, chưa nối Internet

```powershell
.\scripts\start-goodmcp.ps1 -LocalTest -NoTunnel
```

Chế độ này không cần Access và chỉ bind loopback; từ chối request có forwarding/Cloudflare headers. Không nối Tunnel/reverse proxy vào chế độ này. Dùng Inspector tại `http://127.0.0.1:8765/mcp`; chỉ đọc mặc định.

Muốn thử origin có xác thực nhưng chưa bật connector:

```powershell
.\scripts\start-goodmcp.ps1 -NoTunnel
.\scripts\check-goodmcp.ps1 -LocalOnly
```

## 6. Nghiệm thu bằng Inspector, rồi từng web AI

Tạo backup `.blend` riêng trước khi bật quyền ghi. Cài/chạy MCP Inspector hỗ trợ SDK 1.x, chọn **Streamable HTTP**, URL đã cấu hình, hoàn tất OAuth. Nếu dùng bản CLI 1.x để thử local:

```powershell
npx @modelcontextprotocol/inspector@1.0.2 --cli http://127.0.0.1:8765/mcp --transport http --method tools/list
```

Chạy `initialize`, `tools/list`, `get_addon_status`, `get_scene_info`, `look`. Chỉ sau khi Access đúng và bản backup có thể mở lại, đổi `GOODMCP_ALLOW_WRITE=1` trong `.env`, Stop/Start để áp dụng. Tạo `GoodMCP_Test_Cube`, đổi màu và lưu vào **file thử riêng**. Không ghi đè scene thật. Safe mode là bộ lọc AST, **không cách ly filesystem**: `bpy` vẫn có thể save/import/export. Tool execute được cấp khả năng chỉnh Blender mạnh; chỉ bật khi cần.

Trong remote chỉ đọc, `look(image=...)` chỉ nhận tên ảnh đã có trong Blender, gồm `Render Result`; tên không có trong datablock bị từ chối trước khi đọc đĩa. Ảnh đã liên kết với Blender vẫn thuộc phạm vi được xem. Muốn đọc ảnh từ đường dẫn file, phải bật rõ ràng `GOODMCP_ALLOW_WRITE=1`; stdio giữ hành vi cũ.

Remote resources chỉ gồm HTML viewport đi kèm và dữ liệu object/material/collection trong scene. Các URI khác bị chặn ở cả discovery và thực thi `resources/read`.

Giữ 3 phép nghiệm thu độc lập cho mỗi nền tảng:

| Client | Protocol works | Account/region eligible | Read/write usable |
|---|---|---|---|
| Grok Web | Chưa thử | Chưa xác minh | Chưa thử |
| ChatGPT Web | Chưa thử | Chưa xác minh gói/workspace | Chưa thử |
| Gemini Web | Chưa thử | Chưa xác minh khu vực/tài khoản | Chưa thử |

- **Grok:** Connectors → New Connector → Custom → URL, đăng nhập rồi chạy các ca thử. Không coi là đã đạt khi chỉ Inspector chạy được.
- **ChatGPT:** kiểm tra quyền custom MCP và quyền write thực tế của tài khoản/workspace theo [tài liệu OpenAI](https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt). Nếu chỉ đọc/fetch: ghi `blocked by plan for write`.
- **Gemini:** kiểm tra Custom apps có hiện và tài khoản đáp ứng [điều kiện Google](https://support.google.com/gemini/answer/17209137). Không đủ điều kiện: ghi `blocked by geographic/account eligibility`. Gemini API là phép thử khác, không thay nghiệm thu Gemini Web.

Ở mỗi client đủ điều kiện: đọc scene → ảnh `look` → tạo/đổi màu cube nếu có quyền ghi → save thử → client thứ hai đọc cùng scene → đóng/mở Blender và gọi lại → thu hồi Access và gọi lại → hai call đồng thời → gọi lén tool không được phép. Ghi lỗi thật và ảnh/transcript đã che thông tin nhạy cảm vào `docs/TEST_RESULTS.md`. Không thay OAuth bằng token không xác thực nếu client không tương thích; chỉ cân nhắc thư viện OAuth proxy khi có bằng chứng thất bại.

## 7. Khi có lỗi

| Hiện tượng | Cách xử lý |
|---|---|
| `Blender offline` | Mở Blender, enable addon, Start MCP Server; bảo đảm 9876 chỉ local. Không dùng `blender -b` cho addon có timer. |
| Port 8765 đã dùng | Ctrl+C phiên GoodMCP trước, không kill tiến trình lạ. |
| Origin 401 | Bình thường nếu thiếu JWT. Khi qua Cloudflare, kiểm tra team/AUD/email/JWKS và đồng hồ máy. |
| 403 | Email không được phép hoặc local-test nhận proxy traffic; dùng đúng owner và chế độ auth khi nối Tunnel. |
| Public 302, thiếu OAuth discovery | Bật Managed OAuth, kiểm tra policy, hostname và redirect URI. |
| Tunnel offline / 502 / máy tắt | Kiểm tra cửa sổ Start, log riêng, kết nối Internet; mở máy, Blender và Start lại. |
| Timeout | Tool có ngân sách response socket 180s; giảm độ phân giải/payload. Tạo mô hình bên ngoài có thể phải poll lại qua tool upstream. Kiểm tra scene trước khi retry lệnh ghi để tránh tạo trùng. |
| Ảnh/payload quá lớn | Request tối đa 1 MiB, response Blender tối đa 32 MiB; giảm kích thước ảnh/scene. |
| OAuth hết phiên | Đăng nhập lại client, kiểm tra grant/access token lifetime tại Access. |

JWT được kiểm tra mỗi request, nhưng JWT đã ký có thể còn hợp lệ đến hạn hết hạn. Việc thu hồi phiên tại edge phải được nghiệm thu riêng; JWKS cache 5 phút không phải danh sách thu hồi phiên.

## 8. Tắt truy cập và rollback

Để tắt ngay: Ctrl+C để dừng connector, hoặc stop/disable Tunnel trên Cloudflare, hoặc đặt policy **Block** cho ứng dụng. **Không xóa/disable Access app trong lúc Tunnel vẫn phục vụ**, vì việc gỡ lớp Access có thể bỏ bảo vệ ở edge. Origin vẫn xác minh JWT nhưng không dựa vào đó làm quy trình tắt chính.

Giữ bản backup `.blend` trước mỗi thử nghiệm. Rollback về stdio: dừng GoodMCP/Tunnel, dùng config MCP cũ với command `mcp-for-blender` không có `--transport`. Nếu cần quay lại mã nguồn, lưu thay đổi cá nhân và checkout baseline `7a0373ec9199183cb460068c4f96aed9c579fb4f`, chạy `uv sync --frozen`. Addon và cổng 9876 giữ nguyên. Không reset/xóa scene người dùng.

## 9. Kiểm thử cho người phát triển

```powershell
uv sync --frozen
uv pip install --python .venv/Scripts/python.exe pytest==8.4.2
$env:DISABLE_TELEMETRY = 'true'
.\.venv\Scripts\python.exe -m pytest -q
```

`uv sync` có thể gỡ pytest (upstream chưa khai báo dev dependency); cài lại bằng lệnh trên. Kiểm thử không yêu cầu API key hay Tunnel thật. [Kế hoạch gốc](docs/GOODMCP_PLAN.md) và [kết quả có bằng chứng](docs/TEST_RESULTS.md) ghi rõ ranh giới local, Windows và public acceptance.
