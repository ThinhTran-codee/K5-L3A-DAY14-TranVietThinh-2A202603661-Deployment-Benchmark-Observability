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

## Part 3: Cloud Deployment

### Exercise 3.1: Deploy agent Part 6 lên Railway
- **Public URL:** `https://k5-l3a-day14-tranvietthinh-2a202603661-deploymen-production.up.railway.app`
- **Cấu hình triển khai:** Deploy trực tiếp thư mục `06-lab-complete/` bằng `Dockerfile` multi-stage + `railway.toml`, kết nối thêm service managed **Redis** trong cùng project qua biến tham chiếu `REDIS_URL=${{Redis.REDIS_URL}}`, đặt `AGENT_API_KEY` trong Railway Variables (không ghi vào code), và cấu hình Public Networking port khớp với `PORT` do Railway cấp (`8080`).
- **Tự kiểm tra 4 lệnh CP6:**
  - `GET /health` → `200`
  - `GET /ready` → `200` (xác nhận kết nối Redis thành công)
  - `POST /ask` (không có `X-API-Key`) → `401`
  - `POST /ask` (có `X-API-Key`) → `200`
- **Screenshots:** `screenshots/dashboard.png`, `screenshots/running.png`, `screenshots/test.png` (chi tiết xem [DEPLOYMENT.md](DEPLOYMENT.md)).

### Exercise 3.2: So sánh `railway.toml` vs `render.yaml`

| Tiêu chí | `railway.toml` (Railway) | `render.yaml` (Render Blueprint) |
| :--- | :--- | :--- |
| **Định dạng & phạm vi** | TOML, mô tả cấu hình build/deploy cho **1 service** cụ thể (project & database thường tạo riêng trên dashboard/CLI rồi nối bằng Variable Reference `${{Redis.REDIS_URL}}`). | YAML (Infrastructure-as-Code Blueprint), có thể khai báo **cả danh sách nhiều service** (`services:`, `databases:`) trong cùng 1 file. |
| **Build & Healthcheck** | `[build] builder = "DOCKERFILE"`, `[deploy] healthcheckPath = "/health"`, `restartPolicyType = "ON_FAILURE"`. | `type: web`, `runtime: docker`, `dockerfilePath: ./Dockerfile`, `healthCheckPath: /health`. |
| **Quản lý biến môi trường & Secret** | Biến thường được quản lý tách biệt trên Dashboard / `railway variables set` thay vì khai báo trong `railway.toml`. | Khai báo trực tiếp danh sách `envVars` trong `render.yaml`; secret dùng `generateValue: true` (Render tự sinh) hoặc `sync: false` (nhập tay trên dashboard, không lộ vào Git). |
| **Vì sao khác nhau?** | Railway ưu tiên trải nghiệm nhanh, linh hoạt theo từng service gắn liền giao diện Canvas/CLI. | Render Blueprint hướng tới khai báo trọn bộ hạ tầng lặp lại được (reproducible IaC) từ một file duy nhất trong repo Git. |

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline (`03-cloud-deployment/production-cloud-run/`)

Đọc `cloudbuild.yaml` và `service.yaml`, pipeline CI/CD tự động khi push lên nhánh `main` đi qua **4 bước tuần tự**:
1. **`test` (`python:3.11-slim`):** Cài `requirements.txt` + `pytest` và chạy toàn bộ bộ kiểm thử `pytest tests/ -v`; nếu fail sẽ chặn deploy ngay.
2. **`build` (`gcr.io/cloud-builders/docker`):** Build Docker image có tận dụng `--cache-from` từ bản `latest`, gắn 2 tag là `$COMMIT_SHA` (để truy vết/rollback) và `latest`.
3. **`push`:** Đẩy các tag image lên Google Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **`deploy` (`gcloud run deploy`):** Triển khai image `$COMMIT_SHA` lên Cloud Run (`asia-southeast1`), cấu hình autoscaling `min-instances=1` (tránh cold start) đến `max-instances=10`, giới hạn tài nguyên (`1 CPU`, `512Mi RAM`, `concurrency=80`, `timeout=60s`), đọc secret từ **Secret Manager** (`--set-secrets` / `secretKeyRef`) và tách riêng `livenessProbe` (`/health`) với `startupProbe` (`/ready`) như định nghĩa IaC trong `service.yaml`.

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication (`04-api-gateway/develop/app.py`)

- **API key được kiểm tra ở đâu?**
  - Trong hàm dependency `verify_api_key` (`04-api-gateway/develop/app.py:39-54`) sử dụng `APIKeyHeader(name="X-API-Key", auto_error=False)`, và được gắn vào endpoint `POST /ask` thông qua `Depends(verify_api_key)` (dòng 70). Giá trị chuẩn đọc từ biến môi trường `AGENT_API_KEY`.
- **Điều gì xảy ra nếu thiếu hoặc sai key?**
  - Thiếu header `X-API-Key` → trả về **`401 Unauthorized`** (`Missing API key`).
  - Sai giá trị key → trả về **`403 Forbidden`** (`Invalid API key.`).
- **Làm sao rotate key an toàn (không downtime)?**
  - Không hardcode key trong code mà đọc từ biến môi trường / secret manager. Khi rotate, hỗ trợ tạm thời cả key cũ và key mới (ví dụ danh sách `AGENT_API_KEYS`), cập nhật client sang key mới, sau đó thu hồi key cũ.

**Kết quả test thực tế (`curl -i`):**

1. Thiếu API key → `401 Unauthorized`:
```http
HTTP/1.1 401 Unauthorized
date: Wed, 25 Nov 2026 08:35:08 GMT
server: uvicorn
content-length: 67
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

2. Sai API key → `403 Forbidden`:
```http
HTTP/1.1 403 Forbidden
date: Wed, 25 Nov 2026 08:34:54 GMT
server: uvicorn
content-length: 29
content-type: application/json

{"detail":"Invalid API key."}
```

3. Đúng API key (`X-API-Key: secret-key-123`) → `200 OK`:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:35:09 GMT
server: uvicorn
content-length: 114
content-type: application/json

{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

---

### Exercise 4.2 & 4.3: JWT Authentication & Rate Limiting (`04-api-gateway/production/`)

- **JWT Flow (`auth.py`):** Client gửi `username`/`password` (`student`/`demo123`) tới `POST /auth/token` → server xác thực và ký JWT bằng `HS256` (chứa `sub`, `role`, `iat`, `exp` 60 phút) → client gửi `Authorization: Bearer <REDACTED_TOKEN>` trong mọi request tới `POST /ask` → server verify chữ ký và hạn dùng (stateless, không cần query DB mỗi request).
- **Rate Limiting (`rate_limiter.py`):**
  - **Thuật toán:** **Sliding Window Counter** — mỗi user có một `deque` lưu timestamps của các request trong cửa sổ `60` giây; mỗi lần gọi, xóa các timestamp cũ hơn `now - 60`, kiểm tra `len(window) >= max_requests` thì trả `429 Too Many Requests` kèm các header `X-RateLimit-*` và `Retry-After`.
  - **Giới hạn:** `10 requests/phút` cho `user` (`rate_limiter_user`) và `100 requests/phút` cho `admin` (`rate_limiter_admin`).
  - **Cách bypass / nới limit cho admin:** Phân tách limiter theo `user["role"]` trong `app.py:141` (`limiter = rate_limiter_admin if role == "admin" else rate_limiter_user`), hoặc bỏ qua bước gọi `limiter.check()` khi `role == "admin"`.

**Kết quả test thực tế (`curl -i`, đã che JWT token):**

- Lấy token tại `POST /auth/token` (`student`/`demo123`): `access_token = eyJhbGciOiJIUzI1NiIs...<REDACTED>`.
- Gọi `POST /ask` có JWT hợp lệ (Request 1 / 10) → `200 OK`:
```http
HTTP/1.1 200 OK
date: Wed, 25 Nov 2026 08:41:44 GMT
server: uvicorn
content-length: 210
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"question":"Test 1","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":9,"budget_remaining_usd":4.2e-05}}
```

- Gọi liên tiếp đến Request 11 (vượt ngưỡng 10 req/phút) → `429 Too Many Requests`:
```http
HTTP/1.1 429 Too Many Requests
date: Wed, 25 Nov 2026 08:41:45 GMT
server: uvicorn
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
x-ratelimit-reset: 1795596166
retry-after: 59
content-length: 98
content-type: application/json
x-content-type-options: nosniff
x-frame-options: DENY
x-xss-protection: 1; mode=block
referrer-policy: strict-origin-when-cross-origin

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}
```

---

### Exercise 4.4: Cost Guard

- **Cách thiết kế Cost Guard trong production (dùng Redis):**
  - Mỗi user (hoặc toàn hệ thống) có một key theo chu kỳ ngày/tháng, ví dụ `budget:{user_id}:{YYYY-MM}` (hoặc `YYYY-MM-DD`).
  - **Trước khi gọi LLM (`check_budget`):** đọc tổng chi phí hiện tại từ Redis (`GET`); nếu `current >= budget_limit` thì chặn ngay bằng **`402 Payment Required`** (hoặc `503` nếu vượt ngân sách toàn cục `global_daily_budget_usd`), đồng thời log cảnh báo khi đạt `80%` ngân sách.
  - **Sau khi gọi LLM (`record_usage`):** tính chi phí thực tế theo số `input_tokens` và `output_tokens`, cộng dồn nguyên tử vào Redis bằng `INCRBYFLOAT` và đặt TTL bằng `EXPIRE` (ví dụ 32 ngày cho budget tháng) để tự động reset sang chu kỳ mới.
  - Lưu trong Redis thay vì `dict` trong RAM giúp trạng thái chi phí đồng bộ giữa nhiều instance/worker và không bị mất khi container restart.
- **Vì sao cần cả Rate Limit và Cost Guard?**
  - **Rate Limit** bảo vệ **tốc độ & tài nguyên hạ tầng** (chống spam/DDoS quá nhiều request/phút → `429`).
  - **Cost Guard** bảo vệ **ngân sách tiền API LLM** (chống cháy ví → `402`).
  - Cần cả hai vì: một user có thể gửi ít request (không vi phạm rate limit) nhưng mỗi request kèm prompt/output cực dài làm chi phí tăng vọt; ngược lại, nhiều request rất ngắn có thể làm quá tải server dù tổng tiền vẫn thấp.

---

## Part 5: Scaling & Reliability

### Exercise 5.1 & 5.2: Health Checks (`/health` vs `/ready`) và Graceful Shutdown (`05-scaling-reliability/develop/app.py`)

- **Phân biệt Liveness (`/health`) và Readiness (`/ready`):**
  - **`GET /health` (Liveness probe):** Hỏi *"process/container còn sống không?"*. Luôn trả `200 OK` miễn là tiến trình vẫn hoạt động bình thường (kể cả khi một dependency bên ngoài như Redis đang tạm mất kết nối). Nếu `/health` trả non-200 hoặc timeout, platform (Docker, Railway, Kubernetes) sẽ **restart container**.
  - **`GET /ready` (Readiness probe):** Hỏi *"instance này đã sẵn sàng nhận traffic chưa?"*. Kiểm tra trạng thái khởi tạo (`_is_ready`) và kết nối tới các dependency quan trọng (như `redis.ping()`). Nếu chưa sẵn sàng hoặc đang shutdown, trả **`503 Service Unavailable`** để Load Balancer tạm thời **ngừng đẩy traffic mới** vào instance đó mà không cần kill/restart oan container.
- **Graceful Shutdown (`SIGTERM`):**
  - Khi orchestrator muốn dừng hoặc rolling-deploy container, nó gửi tín hiệu **`SIGTERM`** (khác với `SIGKILL` giết tiến trình ngay lập tức).
  - Trong `develop/app.py`, `lifespan` chuyển `_is_ready = False` (để `/ready` trả `503`), chờ biến `_in_flight_requests` giảm về `0` (hoàn thành các request đang xử lý, tối đa `timeout_graceful_shutdown=30` giây) rồi mới thoát sạch với exit code `0`.

---

### Exercise 5.3–5.5: Stateless Design & Load Balancing (`05-scaling-reliability/production/`)

- **Vì sao state trong RAM (in-memory) bị hỏng khi scale nhiều instance?**
  - Khi chạy 3 instance agent phía sau Nginx Load Balancer, request 1 của user có thể rơi vào `instance-1` (lưu lịch sử hội thoại trong RAM của `instance-1`), nhưng request 2 lại được Nginx điều phối sang `instance-2` — nơi hoàn toàn không có dữ liệu của session đó. Ngoài ra, nếu container restart, toàn bộ dữ liệu trong RAM cũng mất sạch.
  - **Giải pháp Stateless:** Đẩy toàn bộ state (session, conversation history, rate limit, cost guard) sang kho lưu trữ dùng chung bên ngoài là **Redis** (`save_session` / `load_session` bằng `SETEX` và `GET` trong `05-scaling-reliability/production/app.py:59-74`). Nhờ đó bất kỳ instance nào cũng phục vụ được mọi user mà không mất ngữ cảnh.

**Kết quả thực tế khi chạy stack 3 instance (`docker compose -p k5-day14-scaling up -d --build --scale agent=3`):**

```text
NAME                       IMAGE                    COMMAND                  SERVICE   CREATED          STATUS                    PORTS
k5-day14-scaling-agent-1   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     30 seconds ago   Up 19 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-2   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     30 seconds ago   Up 18 seconds (healthy)   8000/tcp
k5-day14-scaling-agent-3   k5-day14-scaling-agent   "python -m uvicorn a…"   agent     30 seconds ago   Up 18 seconds (healthy)   8000/tcp
k5-day14-scaling-nginx-1   nginx:alpine             "/docker-entrypoint.…"   nginx     30 seconds ago   Up 18 seconds             0.0.0.0:8080->80/tcp, [::]:8080->80/tcp
k5-day14-scaling-redis-1   redis:7-alpine           "docker-entrypoint.s…"   redis     31 seconds ago   Up 29 seconds (healthy)   6379/tcp
```

**Kết quả chạy `python3 test_stateless.py`:**

```text
Session ID: e954c80c-05a3-4f79-9243-2d8c8b69755c

Request 1: [instance-ffb11c]  Q: What is Docker?
Request 2: [instance-d657aa]  Q: Why do we need containers?
Request 3: [instance-7f4ef8]  Q: What is Kubernetes?
Request 4: [instance-ffb11c]  Q: How does load balancing work?
Request 5: [instance-d657aa]  Q: What is Redis used for?

Total requests: 5
Instances used: {'instance-ffb11c', 'instance-d657aa', 'instance-7f4ef8'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

**Giải thích kết quả:**
- Nginx phân tải đều 5 request liên tiếp của cùng 1 `session_id` (`e954c80c-05a3-4f79-9243-2d8c8b69755c`) qua cả **3 instance khác nhau** (`instance-ffb11c`, `instance-d657aa`, `instance-7f4ef8`) theo cơ chế round-robin.
- Khi gọi `GET /chat/{session_id}/history`, toàn bộ **10 messages** (5 câu hỏi `user` + 5 câu trả lời `assistant`) vẫn đầy đủ và đúng thứ tự, chứng minh hệ thống **stateless** hoạt động chính xác nhờ chia sẻ trạng thái qua **Redis**.

---

## Part 6: Final Project — Kết quả `check_production_ready.py`

Chạy đầy đủ (có Docker) trong `06-lab-complete/` trên WSL2 `Ubuntu-22.04` (`os.name == 'posix'`):

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: PASS 12/12
================================================================
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
3. **Part 4 — API Security (CP3):**
   - **Hỏi gì:** Nhờ AI hướng dẫn các bước chạy thử bản `develop` (API Key) và `production` (JWT + Rate Limit), xử lý lỗi `python` vs `python3` khi trích xuất JWT token, và tổng hợp ghi vào `MISSION_ANSWERS.md`.
   - **Nhận gì:** Bộ lệnh `curl -i` kiểm thử cho 401/403/200/429 và giải thích thuật toán Sliding Window + thiết kế Cost Guard với Redis.
   - **Tự kiểm tra:** Tự chạy server và toàn bộ lệnh `curl -i` trên 2 terminal WSL, xác nhận thực tế 401/403/200 ở Exercise 4.1, 200 OK ở Exercise 4.2, và đếm ngược `requests_remaining` từ 9 về 0 rồi trả `429 Too Many Requests` (`retry-after: 59`) ở Request 11.
4. **Part 5 — Scaling & Reliability (CP4):**
   - **Hỏi gì:** Nhờ AI hướng dẫn chạy thử health/readiness/graceful shutdown và stack 3 instance agent + Redis + Nginx, sau đó tổng hợp kết quả vào `MISSION_ANSWERS.md`.
   - **Nhận gì:** Lệnh chạy stack với `-p k5-day14-scaling --scale agent=3` và kịch bản kiểm chứng stateless.
   - **Tự kiểm tra:** Tự bật stack 3 instance (`healthy`), chạy `python3 test_stateless.py` xác nhận 5 request đi qua cả 3 instance khác nhau nhưng vẫn bảo toàn đủ 10 messages trong Redis, sau đó dọn stack bằng `docker compose down`.
5. **Part 6 — Final Project (CP5):**
   - **Hỏi gì:** Nhờ AI hỗ trợ hoàn thiện các file `TODO` trong `06-lab-complete/` (`app/config.py`, `app/redis_client.py`, `app/auth.py`, `app/rate_limiter.py`, `app/cost_guard.py`, `app/main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`) và xử lý lỗi timeout khởi động `uvicorn --workers 2` trên WSL2.
   - **Nhận gì:** Code đầy đủ 12 tiêu chí production-ready (image multi-stage 69 MB, Redis sliding-window rate limit & cost guard, JSON logging, lifespan graceful shutdown) và tối ưu `load_dotenv(".env")` tránh quét thư mục cha trên `/mnt/d/`.
   - **Tự kiểm tra:** Tự chạy `python check_production_ready.py` bản đầy đủ có Docker trong WSL2 `Ubuntu-22.04` và đạt **`PASS 12/12`**.
6. **Part 3 — Cloud Deployment (CP6):**
   - **Hỏi gì:** Nhờ AI hướng dẫn từng bước deploy `06-lab-complete/` kèm Redis lên Railway, xử lý lỗi `502` do lệch cổng `8000` vs `8080`, và tổng hợp `DEPLOYMENT.md` + so sánh `railway.toml`/`render.yaml` + phân tích Cloud Run pipeline (`cloudbuild.yaml`, `service.yaml`).
   - **Nhận gì:** Hướng dẫn cấu hình Root Directory `06-lab-complete`, Variable Reference `${{Redis.REDIS_URL}}`, sửa Public Networking port về `8080`, và hoàn thiện tài liệu nộp CP6.
   - **Tự kiểm tra:** Tự thao tác deploy trên Railway Dashboard, kiểm chứng cả 2 service Agent + Redis đều Online và chạy 4 lệnh `curl` tới Public URL.
7. **Part 7 Bước 1 — Benchmark local & Eval (CP7):**
   - **Hỏi gì:** Nhờ AI hướng dẫn lệnh chạy load test (4 mức concurrency + 3 mức `MOCK_SLOW_RATE`) và eval v1 vs v2, đọc file JSON kết quả để chỉ ra các câu bị fail trong `eval_v2.json` và bổ sung `KNOWLEDGE_BASE`.
   - **Nhận gì:** Phát hiện `load_v2_slow_0.1.json` lần đầu chưa restart server, bổ sung 2 entry `security-02` và `scaling-03` vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` và `production/utils/mock_llm.py`, và điền số liệu khớp JSON vào Phần 1–3 của `BENCHMARK_REPORT.md`.
   - **Tự kiểm tra:** Tự chạy lại toàn bộ lệnh `load_test.py` và `eval/run_eval.py`, xác nhận `load_v2_slow_0.1.json` có `p95 = 1687.3 ms`, `p99 = 1716.4 ms`, và `eval_v2_fixed.json` đạt `23/23 (100%)` với `Quality gate ✅ PASS` (0 regression).
8. **Part 7 Bước 2 — Observability stack & Đóng gói (CP8):**
   - **Hỏi gì:** Nhờ AI chẩn đoán lỗi `ModuleNotFoundError: No module named 'uvicorn'` trong `production/Dockerfile`, chạy Locust scale 1 vs scale 3, trích xuất trace chậm/lỗi từ Jaeger + dòng log JSON khớp `trace_id`, kích hoạt các Prometheus alerts và hoàn thiện `BENCHMARK_REPORT.md`.
   - **Nhận gì:** Sửa `production/Dockerfile` thêm `ENV PYTHONUSERBASE=/home/agent/.local`, xuất 2 file `scale_1_stats.csv` và `scale_3_stats.csv` ra `benchmark-results/`, trích xuất trace chậm `fbf66218a0cea61b4489bfe3ff8263a6` (`1827.87 ms`, span `chat mock-llm-small` `1672.29 ms` = 91.5%) + trace lỗi `5a0eb940134c48b28836d4ea5dc032ca` (`503`), kích hoạt đồng thời 3 alert (`AgentHighErrorRate`, `AgentHighLatencyP95`, `LLMCostBurnRateHigh`) đang `firing`, và điền đầy đủ Phần 4–6 của `BENCHMARK_REPORT.md`.
   - **Tự kiểm tra:** Tự mở 4 giao diện (Grafana, Jaeger slow/error traces, Prometheus Alerts) chụp 4 ảnh vào `screenshots/`, đối chiếu số liệu CSV và dọn sạch stack Docker trước khi nộp.
