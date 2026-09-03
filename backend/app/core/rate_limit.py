from __future__ import annotations

import time
from collections import defaultdict, deque

import redis

from app.core.config import settings


class RateLimiter:
    def __init__(self) -> None:
        self._local = defaultdict(deque)
        self._redis = None

        redis_url = getattr(settings, "redis_url", None)
        if redis_url:
            try:
                self._redis = redis.Redis.from_url(
                    redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                self._redis.ping()
            except Exception:
                self._redis = None

    def allow(self, key: str, limit: int, window: int) -> bool:
        now = int(time.time())

        if self._redis is not None:
            redis_key = f"repopilot:rate:{key}"
            pipe = self._redis.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window)
            count, _ = pipe.execute()
            return int(count) <= limit

        q = self._local[key]
        cutoff = now - window

        while q and q[0] <= cutoff:
            q.popleft()

        if len(q) >= limit:
            return False

        q.append(now)
        return True
