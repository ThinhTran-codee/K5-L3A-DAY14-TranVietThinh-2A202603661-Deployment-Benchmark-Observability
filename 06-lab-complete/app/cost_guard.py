"""
Cost guard (tiêu chí 8) — Cộng dồn chi phí LLM trong Redis theo ngày.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006
BUDGET_TTL_SECONDS = 2 * 24 * 3600


def _today_key() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:daily:{day}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    if r is None:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable")

    try:
        current = float(r.get(_today_key()) or 0.0)
    except RedisError:
        raise HTTPException(status_code=503, detail="Cost guard storage unavailable")

    if current >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=402,
            detail="Daily budget exceeded",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí vào Redis, trả về chi phí request."""
    cost = (
        (input_tokens / 1000.0) * PRICE_INPUT_PER_1K
        + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    )
    if r is not None:
        try:
            key = _today_key()
            r.incrbyfloat(key, cost)
            r.expire(key, BUDGET_TTL_SECONDS)
        except RedisError:
            pass
    return cost
