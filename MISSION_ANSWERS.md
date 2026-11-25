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

## Part 2: Docker Containerization

### Exercise 2.1: Câu hỏi về `02-docker/develop/Dockerfile`

1. **Base image là gì?**
   - `python:3.11` (bản đầy đủ trên nền Debian, đi kèm nhiều công cụ hệ thống và thư viện build nên dung lượng rất lớn ~1+ GB).
2. **Working directory là gì?**
   - `WORKDIR /app` — mọi lệnh `COPY`, `RUN`, `CMD` phía sau đều chạy trong thư mục `/app` bên trong container.
3. **Tại sao `COPY requirements.txt` đứng trước `COPY app.py`?**
   - Để tận dụng **Docker layer cache**. File `requirements.txt` ít thay đổi hơn mã nguồn `app.py`. Khi chỉ sửa code mà không đổi dependencies, Docker tái sử dụng cache của layer `RUN pip install -r requirements.txt` thay vì cài lại toàn bộ thư viện từ đầu, giúp build nhanh hơn rất nhiều.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**
   - `CMD` định nghĩa lệnh mặc định (hoặc tham số mặc định cho `ENTRYPOINT`) và **có thể bị ghi đè hoàn toàn** khi truyền lệnh mới lúc `docker run <image> <lệnh>`.
   - `ENTRYPOINT` định nghĩa tiến trình thực thi cố định của container; các tham số truyền thêm khi `docker run` sẽ được **nối vào sau** `ENTRYPOINT` (chỉ bị ghi đè nếu dùng cờ `--entrypoint`).

---

### Exercise 2.2: Build và chạy bản `develop`

Build từ gốc repo (`docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .`), chạy container (`docker run -d -p 8000:8000 my-agent:develop`) và gọi thử (`curl -sS -i -X POST "http://localhost:8000/ask?question=What%20is%20Docker%3F"`):

```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:15:30 GMT
server: uvicorn
content-length: 103
content-type: application/json

{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
```

---

### Exercise 2.3: Multi-stage build (`02-docker/production/Dockerfile`) và so sánh dung lượng

- **Stage 1 (`builder` — `FROM python:3.11-slim AS builder`):** Cài công cụ biên dịch (`gcc`, `libpq-dev`) rồi `pip install --no-cache-dir --user -r requirements.txt` vào `/root/.local`.
- **Stage 2 (`runtime` — `FROM python:3.11-slim AS runtime`):** Tạo non-root user (`appuser`), chỉ copy thư viện đã cài từ `/root/.local` của stage `builder` cùng mã nguồn (`main.py`, `utils/mock_llm.py`), thêm `HEALTHCHECK` và chạy `uvicorn` dưới quyền `appuser`.
- **Tại sao image nhỏ hơn?**
  1. Dùng base image tối giản `python:3.11-slim` thay vì `python:3.11` full.
  2. Toàn bộ công cụ biên dịch (`gcc`, `libpq-dev`, apt lists) ở stage `builder` bị bỏ lại, không đi vào image cuối cùng.

**Kết quả đo thực tế bằng `docker images my-agent`:**

```text
REPOSITORY   TAG        SIZE
my-agent     develop    1.67GB
my-agent     advanced   240MB
```

- **Develop:** `1.67 GB` (~1,670 MB)
- **Production (`advanced`):** `240 MB` (< 500 MB)
- **Chênh lệch:** giảm `~1,430 MB`, tương đương **nhỏ hơn 85.6%** (~7 lần).

---

### Exercise 2.4: Docker Compose Stack (`02-docker/production/docker-compose.yml`)

**Các service được khởi chạy & cách giao tiếp:**
Stack gồm 4 service chạy chung trên bridge network nội bộ `internal`:
1. **`nginx`** (`nginx:alpine`): Reverse proxy / load balancer, là service duy nhất mở cổng ra ngoài (`80:80`, `443:443`), chuyển tiếp request tới `http://agent:8000`.
2. **`agent`** (build từ `02-docker/production/Dockerfile`, target `runtime`): FastAPI AI agent chạy cổng nội bộ `8000` (không expose ra host), chỉ khởi động sau khi `redis` và `qdrant` đều ở trạng thái `healthy`. Giao tiếp với Redis qua `REDIS_URL=redis://redis:6379/0` và Qdrant qua `QDRANT_URL=http://qdrant:6333` (Docker DNS nội bộ).
3. **`redis`** (`redis:7-alpine`): Cache session & rate limiting, gắn volume `redis_data`.
4. **`qdrant`** (`qdrant/qdrant:v1.9.0`): Vector database cho RAG, gắn volume `qdrant_data`.

**Sơ đồ kiến trúc:**

```text
                ┌──────────────────────────────┐
  Client ──────▶│  Nginx (ports 80/443 -> host)│
                └──────────────┬───────────────┘
                               │ (internal bridge network)
                               ▼
                     ┌───────────────────┐
                     │  Agent (:8000)    │
                     └────┬─────────┬────┘
                          │         │
                          ▼         ▼
                ┌──────────────┐  ┌────────────────┐
                │ Redis (:6379)│  │ Qdrant (:6333) │
                │ [redis_data] │  │ [qdrant_data]  │
                └──────────────┘  └────────────────┘
```

**Kết quả test qua Nginx (`docker compose -p k5-day14-docker up -d --build`):**

- `curl -sS -i http://localhost/health`:
```http
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
X-XSS-Protection: 1; mode=block

{"status":"ok","uptime_seconds":0.6,"version":"2.0.0","timestamp":"2026-11-25T08:16:46.450605"}
```

- `curl -sS -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question": "Explain microservices"}'`:
```http
HTTP/1.1 200 OK
Server: nginx
Content-Type: application/json

{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

## AI Log (Cập nhật dần trong quá trình làm lab)

1. **Setup môi trường (CP0) & Part 1 (CP1):**
   - **Hỏi gì:** Nhờ AI kiểm tra môi trường WSL2/Python/Docker, setup Python 3.12 trên WSL2 `Ubuntu-22.04`, và đối chiếu các anti-pattern giữa `develop/app.py` và `production/app.py`.
   - **Nhận gì:** Đã tạo môi trường ảo Python `3.12.16` (`os.name: posix`), xác nhận Docker `28.3.2` chạy `hello-world` thành công, và chạy thực tế cả 2 server Part 1 với `curl`.
   - **Tự kiểm tra:** Đã kiểm chứng trực tiếp output `HTTP/1.1 200 OK` từ bản `develop` và `production`, đối chiếu số dòng code trong cả 2 file.
2. **Part 2 — Docker Containerization (CP2):**
   - **Hỏi gì:** Nhờ AI hướng dẫn chạy build image `develop` và `advanced`, chạy Docker Compose stack và tổng hợp giải thích Dockerfile / kiến trúc Compose.
   - **Nhận gì:** Build thực tế từ gốc repo và đo dung lượng `my-agent:develop` (1.67 GB) vs `my-agent:advanced` (240 MB), chạy stack 4 service qua Nginx trả về 200 OK rồi dọn sạch bằng `docker compose down`.
   - **Tự kiểm tra:** Đối chiếu trực tiếp output `docker images my-agent` và phản hồi `curl` qua Nginx.
