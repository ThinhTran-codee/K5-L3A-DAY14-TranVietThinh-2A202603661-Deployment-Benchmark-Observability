# Day 14 Lab — Mission Answers

> **Môn học:** AICB-P1 · VinUniversity 2026  
> **Sinh viên:** Trần Việt Thịnh — MSSV: `2A202603661`

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns phát hiện trong `01-localhost-vs-production/develop/app.py`

1. **Hardcode secrets ngay trong mã nguồn (`develop/app.py:17-18`):**
   - `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"`.
   - Rủi ro: khi push lên Git (đặc biệt repo public), key và mật khẩu DB bị lộ ngay lập tức và vẫn nằm trong lịch sử commit dù có xóa file sau đó.
2. **In secret ra log bằng `print()` (`develop/app.py:33-34, 38`):**
   - `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` làm rò rỉ secret vào log hệ thống; đồng thời dùng `print()` dạng plain text khiến các hệ thống thu thập log (Loki, Datadog, Cloud Logging) khó parse/tìm kiếm theo level hay field.
3. **Hardcode cấu hình & bật chế độ debug/reload (`develop/app.py:21-22, 51-53`):**
   - `DEBUG = True`, `MAX_TOKENS = 500`, `host="localhost"`, `port=8000`, `reload=True`.
   - Khi chạy trong container hoặc cloud (Railway/Render), bind `localhost` khiến bên ngoài container không kết nối vào được; cứng `port=8000` không tương thích biến môi trường `PORT` do cloud inject; `reload=True` tốn tài nguyên và không an toàn ở production.
4. **Không có endpoint Health Check & Readiness (`develop/app.py:42-43`):**
   - Không có `GET /health` hay `GET /ready`, nên container orchestrator / load balancer không biết process còn sống hay đã sẵn sàng nhận traffic để restart hoặc định tuyến.
5. **Không có Graceful Shutdown (`develop/app.py:47-54`):**
   - Không xử lý `SIGTERM` hay vòng đời `lifespan` của FastAPI; khi platform tắt container, các request đang xử lý bị cắt ngang đột ngột và kết nối không được đóng an toàn.
6. **Không có validation input và cấu hình CORS:**
   - Endpoint `/ask` nhận `question` qua query string, không giới hạn CORS, không kiểm soát ngoại lệ rõ ràng.

---

### Exercise 1.2: Kết quả chạy thử bản `develop` và `production`

- **Gọi bản `develop`** (`curl -sS -i -X POST "http://localhost:8000/ask?question=Hello"`):

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:01:47 GMT
server: uvicorn
content-length: 126
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

- **Gọi bản `production`**:
  - `GET /health`: `{"status":"ok","uptime_seconds":1.7,"version":"1.0.0","environment":"development","timestamp":"2026-11-25T08:01:51.276899+00:00"}`
  - `GET /ready`: `{"ready":true}`
  - `POST /ask` (`{"question": "Hello"}`): `{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","model":"gpt-4o-mini"}`

---

### Exercise 1.3: Bảng so sánh `develop` vs `production`

| Feature | Develop (`develop/app.py`) | Production (`production/app.py` & `config.py`) | Tại sao quan trọng? |
| :--- | :--- | :--- | :--- |
| **Config & Secrets** | Hardcode trực tiếp (`OPENAI_API_KEY`, `DATABASE_URL`, `DEBUG`, `port=8000` ở dòng 17–22, 51–53) | Đọc từ biến môi trường qua `Settings` (`production/config.py:14-50`), có `validate()` fail-fast khi thiếu `AGENT_API_KEY` ở production | Tránh lộ secret lên Git; dùng chung 1 artifact code cho dev/staging/prod chỉ bằng cách đổi env vars (12-Factor). |
| **Host / Port / Reload** | `host="localhost"`, `port=8000`, `reload=True` (dòng 51–53) | `host=settings.host` (`0.0.0.0`), `port=settings.port` (từ `PORT`), `reload=settings.debug` (`production/app.py:194-199`) | Container/cloud cần bind `0.0.0.0` và đọc `PORT` động; tắt auto-reload ở production để ổn định và an toàn. |
| **Health & Readiness** | Không có | Có `GET /health` (liveness, dòng 135–149) và `GET /ready` (readiness trả `503` khi chưa sẵn sàng, dòng 152–161) | Orchestrator biết khi nào restart container hỏng (`/health`) và load balancer biết khi nào mới được đẩy traffic vào (`/ready`). |
| **Logging** | `print()` plain text và in cả `OPENAI_API_KEY` (dòng 33–38) | `logging` định dạng JSON có cấu trúc (`production/app.py:28-32`), chỉ log metadata (`question_length`, `client_ip`), tuyệt đối không log secret (dòng 111–122) | Dễ lọc/truy vấn log tập trung (Loki, Datadog) và tránh rò rỉ dữ liệu nhạy cảm. |
| **Shutdown** | Tắt đột ngột | Có `lifespan` context manager (`production/app.py:39-67`) set `is_ready = False` trước khi tắt và đăng ký handler `SIGTERM` (dòng 180–189) | Cho phép hoàn tất các request đang xử lý (in-flight) và đóng tài nguyên sạch sẽ, không gây lỗi 502 cho người dùng khi deploy/restart. |
| **CORS & Metrics** | Không có | Cấu hình `CORSMiddleware` theo `ALLOWED_ORIGINS` (dòng 77–82) và có `GET /metrics` (dòng 164–173) | Kiểm soát nguồn gọi API từ trình duyệt và hỗ trợ theo dõi tình trạng dịch vụ. |

**Ví dụ cụ thể 1 anti-pattern đã được sửa (kèm dòng code):**
- Trong `01-localhost-vs-production/develop/app.py` (dòng 17 và 34), secret bị hardcode `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và bị in trực tiếp ra console bằng `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`.
- Trong `01-localhost-vs-production/production/config.py` (dòng 27) và `production/app.py` (dòng 111–115), key được đọc từ `os.getenv("OPENAI_API_KEY", "")` và log chỉ ghi dạng JSON chứa `event`, `question_length`, `client_ip`, không hề in giá trị key.

---

## AI Log (Cập nhật dần trong quá trình làm lab)

1. **Setup môi trường (CP0) & Part 1 (CP1):**
   - **Hỏi gì:** Nhờ AI kiểm tra môi trường WSL2/Python/Docker, setup Python 3.12 trên WSL2 `Ubuntu-22.04`, và đối chiếu các anti-pattern giữa `develop/app.py` và `production/app.py`.
   - **Nhận gì:** Đã tạo môi trường ảo Python `3.12.16` (`os.name: posix`), xác nhận Docker `28.3.2` chạy `hello-world` thành công, và chạy thực tế cả 2 server Part 1 với `curl`.
   - **Tự kiểm tra:** Đã kiểm chứng trực tiếp output `HTTP/1.1 200 OK` từ bản `develop` và `production`, đối chiếu số dòng code trong cả 2 file.
