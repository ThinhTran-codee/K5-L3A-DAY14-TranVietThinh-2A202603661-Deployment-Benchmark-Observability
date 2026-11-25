"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

App vẫn khởi động được khi Redis chưa sẵn sàng (không ping lúc import).
"""
import redis

from app.config import settings

r: redis.Redis | None = (
    redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    if settings.redis_url
    else None
)


def redis_healthy() -> bool:
    """Dùng cho GET /ready: Redis không kết nối được → False."""
    if r is None:
        return False
    try:
        return bool(r.ping())
    except Exception:
        return False
