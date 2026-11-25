# Benchmark & Observability Report — Day 14

> Mọi con số dưới đây đều lấy trực tiếp từ các file JSON trong `reports/` và CSV trong `benchmark-results/`.

**Họ tên:** Trần Việt Thịnh — MSSV: `2A202603661`  
**Ngày chạy:** 2026-11-25  
**Môi trường:** Windows + WSL2 (`Ubuntu-22.04`, Python `3.12.16`), Docker Desktop `28.3.2`

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | `< 500 ms` | Đảm bảo 95% người dùng nhận phản hồi dưới nửa giây (mock LLM base ~120–180 ms + retrieval ~20 ms), tránh cảm giác trễ khó chịu. |
| Error rate `/ask` | `< 2%` | Mock upstream có tỉ lệ lỗi nền `MOCK_ERROR_RATE=0.01` (1%), đặt SLO `< 2%` cho phép sai số thống kê nhẹ nhưng bắt được ngay khi upstream suy thoái. |
| Accuracy trên golden dataset | `≥ 80%` (mục tiêu sau sửa KB: `100%`) | Ngưỡng tối thiểu `80%` làm quality gate chặn regression khi thay đổi prompt/KB; sau khi bổ sung đủ kiến thức, mục tiêu `100%` (23/23) trên golden dataset. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.00 | 192.5 | 221.3 | 1701.2 | 0.67% | PASS |
| 10 | 37.21 | 189.3 | 223.4 | 1700.5 | 0.33% | PASS |
| 50 | 101.33 | 203.1 | 390.9 | 1715.1 | 1.33% | PASS |
| 100 | 56.14 | 659.7 | 4021.9 | 4303.9 | 1.00% | FAIL |

**Nhận xét:** RPS có tăng tuyến tính theo concurrency không? Vì sao?

RPS **không tăng tuyến tính** theo concurrency. Từ `c=1` đến `c=10`, RPS tăng gần tuyến tính (`4.00 → 37.21` RPS) vì I/O async còn dư năng lực xử lý. Đến `c=50`, RPS tăng lên `101.33` nhưng `p95` đã bắt đầu tăng từ `223.4 ms` lên `390.9 ms`. Tại `c=100`, hệ thống bước vào vùng **bão hòa (saturation)**: hàng đợi (queuing) trên 1 process uvicorn + event loop/socket tích tụ mạnh khiến `p50` nhảy lên `659.7 ms`, `p95` vọt lên `4021.9 ms` (vi phạm SLO `< 500 ms`), và thông lượng thực tế thậm chí **giảm ngược** xuống còn `56.14` RPS.

---

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 191.4 | 220.4 | 234.1 |
| 0.03 (mặc định) | 230.3 | 224.8 | 1689.2 |
| 0.1 | 317.1 | 1687.3 | 1716.4 |

**Nhận xét:** Chỉ số nào nhạy nhất với request chậm? Vì sao SLO không nên đặt theo average?

- **Chỉ số nhạy nhất là `p99` (và tiếp theo là `p95`):** Khi `MOCK_SLOW_RATE` tăng từ `0` lên `0.03` (chỉ 3% request chậm), `avg` chỉ nhích nhẹ `191.4 → 230.3 ms` và `p95` gần như đứng yên (`220.4 → 224.8 ms`), nhưng **`p99` nhảy vọt gấp 7 lần từ `234.1 ms` lên `1689.2 ms`**. Khi tăng lên `0.1` (10% request chậm), cả `p95` (`1687.3 ms`) lẫn `p99` (`1716.4 ms`) đều phá vỡ SLO, trong khi `avg` vẫn chỉ là `317.1 ms` (nhìn có vẻ vẫn `< 500 ms`!).
- **Vì sao không đặt SLO theo average:** Giá trị trung bình làm "phẳng" các ngoại lệ và che giấu hoàn toàn **tail latency** — 10% người dùng phải chờ ~1.7 giây nhưng `avg = 317.1 ms` vẫn trông rất đẹp. Đặt SLO theo `p95`/`p99` phản ánh đúng trải nghiệm tệ nhất mà một tỷ lệ đáng kể người dùng thực sự gặp phải.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.35% (1/23) | 91.30% (21/23) | 100.00% (23/23) |
| Avg tokens / câu | 57.6 | 109.0 | 114.6 |
| Tổng cost (USD) | $0.000411 | $0.000760 | $0.000799 |
| Cost / câu đúng (USD) | $0.00041115 | $0.00003619 | $0.00003472 |
| Quality gate | FAIL | PASS (`min=0.8`) | PASS (`min=1.0`, 0 regression) |

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| `security-02` | `token`, `hết hạn`, `chữ ký` | Bổ sung entry vào `KNOWLEDGE_BASE` trong `develop/utils/mock_llm.py` (và đồng bộ sang `production/utils/mock_llm.py`) với từ khóa `["jwt", "api key"]`, giải thích JWT là token stateless có thời gian hết hạn (`exp`) và chữ ký số (`signature`). |
| `scaling-03` | `cpu`, `memory`, `custom metrics` | Bổ sung entry vào `KNOWLEDGE_BASE` với từ khóa `["kubernetes", "hpa", "autoscal"]`, giải thích Kubernetes HPA tự động scale dựa trên `CPU`, `memory` và `custom metrics`. |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- So với v1, agent v2 thêm bước retrieval (~20 ms) và chèn context vào prompt nên `avg_tokens` tăng gần gấp đôi (`57.6 → 114.6` tokens), `p50` nhích nhẹ (`169.1 → 191.9 ms`) và tổng chi phí 23 câu tăng gần gấp đôi (`$0.000411 → $0.000799`).
- Tuy nhiên, độ chính xác tăng vọt từ **`4.35%` lên `100%`**. Nếu tính theo chỉ số **Cost / câu đúng** (thước đo hiệu quả thật trong production), v2 sau khi sửa KB chỉ tốn **`$0.00003472 / câu đúng`**, **rẻ hơn gần 12 lần** so với v1 (`$0.00041115 / câu đúng`) vì v1 tốn tiền sinh ra 22 câu trả lời sai vô ích.

**Cách dùng exit code của `run_eval.py` làm Quality Gate trong CI/CD để chặn merge:**

Script `eval/run_eval.py` trả về **exit code `0`** khi đạt `--min-accuracy` và không có câu nào bị regression so với `--baseline`, ngược lại trả về **exit code `1`**. Trong GitHub Actions (chạy trên mỗi Pull Request trước khi merge vào `main`), chỉ cần thêm step chạy:
```yaml
- name: Run Eval Quality Gate
  run: |
    python eval/run_eval.py \
      --url http://localhost:8002 \
      --min-accuracy 1.0 \
      --baseline reports/eval_v2.json \
      --out reports/eval_ci.json
```
Khi accuracy tụt dưới ngưỡng hoặc bất kỳ câu nào trước đó PASS nay bị FAIL (regression), step trả về exit code `1` → CI job chuyển đỏ và GitHub Branch Protection tự động **chặn merge PR**.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) — `screenshots/grafana-dashboard.png`
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) — `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (có event `exception`) — `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với ít nhất 2 alert đang **firing** (thực tế 3 alert đang firing: `AgentHighErrorRate`, `AgentHighLatencyP95`, `LLMCostBurnRateHigh`) — `screenshots/prometheus-alert-firing.png`

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` (`value ≈ 19.4% > 5%`) | ~1 phút 15 giây (`scrape 5s` + `for: 1m`) | **Error rate** & **Requests/s theo status code** (`503` tăng vọt) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` (`value ≈ 1.90s > 1s`) | ~2 phút 15 giây (`scrape 5s` + `for: 2m`) | **Latency p95** & **Latency /ask — p50 / p95 / p99** |
| C | `LLM_MODEL=mock-llm-large` *(hoặc tải cao kéo dài)* | `LLMCostBurnRateHigh` (`value ≈ $2.97/giờ > $2/giờ`) | ~2 phút 15 giây (`for: 2m`) | **LLM cost** & **Cost burn rate / Token usage** |
| D | `docker pause` 1 instance | `AgentInstanceDown` (`up{job="agent"} == 0`) | ~35–40 giây (`scrape 5s` + `for: 30s`) | **Instances** (tụt xuống) & trạng thái Targets trong Prometheus |
| E | `AGENT_VERSION=v1` | *Không có alert nào firing* | Không firing | **Tokens / request** và **LLM latency** giảm nhẹ (do bỏ bước retrieval), nhưng lỗi chất lượng không xuất hiện ở hạ tầng |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

Chuyển sang `AGENT_VERSION=v1` không làm tăng lỗi HTTP (`200 OK` vẫn bình thường), không làm tăng latency hay chi phí — thậm chí còn nhanh và rẻ hơn — nên các alert hạ tầng (4 Golden Signals) hoàn toàn im lặng. Để phát hiện sự suy giảm chất lượng trả lời (silent quality regression) trong production, cần kết hợp:
1. **Eval Quality Gate tự động trong CI/CD** trên golden dataset trước mọi lần deploy (chặn merge nếu accuracy giảm hoặc có regression).
2. **Online evaluation / LLM-as-a-Judge định kỳ** trên mẫu (sampling) traffic thật + theo dõi các **business/product metrics** (tỉ lệ thumbs-down của người dùng, tỉ lệ người dùng hỏi lại ngay lập tức, tỉ lệ retrieval hit-rate hoặc độ dài câu trả lời sụt giảm bất thường).

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được trong Jaeger:

- `trace_id`: `fbf66218a0cea61b4489bfe3ff8263a6`
- Tổng thời gian: **`1827.87 ms`** (trên span gốc `POST /ask`; log HTTP ghi `1832.3 ms`)
- Span chiếm nhiều thời gian nhất: **`chat mock-llm-small`** (**`1672.29 ms`**, chiếm **91.5%** tổng thời gian request; trong khi `agent.retrieve_context` chỉ mất `81.38 ms` — 4.5%)
- Trace lỗi tương ứng để tham khảo: `trace_id = 5a0eb940134c48b28836d4ea5dc032ca` (`status: 503`, `ms: 100.5`)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T10:45:29.470081+00:00", "level": "INFO", "service": "observable-agent", "instance": "967339977c46", "event": "http_request", "trace_id": "fbf66218a0cea61b4489bfe3ff8263a6", "span_id": "91a4c4c2da3c9ca1", "request_id": "283ddebbf551", "method": "POST", "route": "/ask", "status": 200, "ms": 1832.3}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Số liệu lấy trực tiếp từ `benchmark-results/scale_1_stats.csv` và `benchmark-results/scale_3_stats.csv` (dòng `POST /ask`; trong ngoặc là dòng `Aggregated` gồm cả `/health`):

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 58.32 *(Agg: 64.14)* | 200 *(Agg: 200)* | **670** *(Agg: 610)* | 1700 *(Agg: 1700)* | 61 / 6929 — 0.88% *(Agg: 61 / 7621 — 0.80%)* |
| 3 | 59.75 *(Agg: 65.67)* | 200 *(Agg: 190)* | **270** *(Agg: 260)* | 1700 *(Agg: 1700)* | 71 / 7092 — 1.00% *(Agg: 71 / 7795 — 0.91%)* |

**Giải thích kết quả:** Scale có cải thiện p95 không? Nút thắt nằm ở đâu?

- **Scale từ 1 lên 3 instance cải thiện rõ rệt `p95`:** `p95` của `POST /ask` giảm mạnh hơn **2.4 lần** (từ **`670 ms`** — vi phạm SLO `< 500 ms` — xuống còn **`270 ms`**, đạt SLO!), và thời gian phản hồi trung bình của `/health` giảm từ `23 ms` xuống `7.9 ms`. Lý do là mỗi container agent bị giới hạn `0.5 CPU / 256M RAM` trong `docker-compose.yml`: ở 1 instance với 100 users đồng thời, CPU và hàng đợi request bị nghẽn nhẹ nên kéo `p95` lên `670 ms`; khi scale lên 3 instance, Nginx chia đều tải giúp triệt tiêu độ trễ xếp hàng.
- **Tại sao `p99` vẫn giữ nguyên `1700 ms` và `RPS` chỉ tăng nhẹ (`58.32 → 59.75`)?**
  - **`p99` không giảm** vì nút thắt ở đuôi phân phối nằm ở **upstream LLM (`MOCK_SLOW_RATE = 0.03`, `MOCK_SLOW_MS = 1500 ms`)** — scale thêm backend instance không thể làm model LLM bên ngoài trả lời nhanh hơn. Để giảm tail latency ở lớp này phải dùng caching, timeout/hedge request hoặc chọn model nhanh hơn.
  - **`RPS` chỉ tăng nhẹ** vì kịch bản Locust có `wait_time` giữa các request của 100 virtual users, nên ở 3 instance hệ thống đã đủ dư tải để phục vụ hết tốc độ sinh tải của 100 users (nếu tăng số users lên 200–300, bản 3 instance sẽ thể hiện mức RPS vượt trội rõ rệt hơn nữa).

---

## 6. Kết luận

- **3 điều học được về benchmark & observability:**
  1. **Đo bằng phân vị (`p95`/`p99`) và đặt SLO rõ ràng thay vì tin vào giá trị trung bình:** `avg` che giấu hoàn toàn tail latency (ví dụ với `MOCK_SLOW_RATE=0.1`, `avg = 317 ms` trông rất ổn nhưng `p95` đã vọt lên `1687 ms`).
  2. **Đánh giá AI Agent phải tách riêng Hiệu năng (load test) và Chất lượng (eval + cost/câu đúng):** Hạ tầng xanh mượt không đảm bảo câu trả lời đúng (Thí nghiệm E); cần golden dataset + Quality Gate trong CI/CD để chặn regression và so sánh hiệu quả bằng *cost / câu đúng*.
  3. **3 trụ cột Metrics – Traces – Logs phải liên kết chặt chẽ:** Prometheus/Grafana phát hiện bất thường và bắn alert → Jaeger chỉ ra đúng span gây chậm (`chat mock-llm-small` chiếm 91.5%) → `trace_id` nối thẳng sang dòng JSON log để điều tra chi tiết.
- **Nếu đưa agent này lên production thật, sẽ thêm metric / alert nào nữa?**
  - **Metrics:** `llm_ttft_seconds` (Time To First Token cho streaming), `retrieval_hit_rate` (tỉ lệ tìm thấy tài liệu liên quan), `rate_limit_rejected_total` (`429`) & `cost_guard_rejected_total` (`402`), và `redis_operation_duration_seconds`.
  - **Alerts:** Alert khi `retrieval_hit_rate` tụt mạnh hoặc `eval_accuracy` định kỳ giảm (bắt lỗi chất lượng như Thí nghiệm E), alert khi `429`/`402` tăng đột biến (dấu hiệu bị lạm dụng API), và kết nối **Alertmanager** định tuyến cảnh báo tới Slack/PagerDuty theo mức độ `warning`/`critical`.
