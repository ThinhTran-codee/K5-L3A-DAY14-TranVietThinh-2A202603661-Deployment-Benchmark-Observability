# Deployment Information — Day 14

## Public URL
https://k5-l3a-day14-tranvietthinh-2a202603661-deploymen-production.up.railway.app

## Platform
Railway (Docker deployment từ thư mục `06-lab-complete/` + managed Redis service trong cùng project)

## Test Commands

Đặt `BASE` là Public URL và `AGENT_API_KEY` là key đã cấu hình trên Railway Variables:

```bash
export BASE="https://k5-l3a-day14-tranvietthinh-2a202603661-deploymen-production.up.railway.app"
export AGENT_API_KEY="<YOUR_AGENT_API_KEY>"

# 1. Health check (liveness) -> 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"

# 2. Readiness check (Redis connected) -> 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"

# 3. Protected endpoint without API key -> 401
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -d '{"question":"Hello"}'

# 4. Protected endpoint with valid API key -> 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H 'Content-Type: application/json' \
  -H "X-API-Key: $AGENT_API_KEY" \
  -d '{"question":"Hello"}'
```

## Environment Variables Set (trên Railway Dashboard, không lưu trong code)
- `ENVIRONMENT` (`production`)
- `AGENT_API_KEY` (secret tự đặt trên Railway Variables)
- `REDIS_URL` (`${{Redis.REDIS_URL}}` — Variable Reference tới service Redis cùng project)
- `RATE_LIMIT_PER_MINUTE` (`10`)
- `DAILY_BUDGET_USD` (`1.0`)
- `PORT` (do Railway tự động cấp — `8080`, `Dockerfile` lắng nghe qua `${PORT:-8000}`)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
