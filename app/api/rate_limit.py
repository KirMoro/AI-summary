"""Lightweight in-memory rate limiting dependencies."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Callable

from fastapi import HTTPException, Request

_BUCKETS: dict[str, deque[float]] = defaultdict(deque)
_LOCK = Lock()


def rate_limit(limit: int, window_seconds: int, scope: str) -> Callable[[Request], None]:
    """Create a dependency enforcing N requests per time window per client IP."""

    def _dep(request: Request) -> None:
        ip = (request.client.host if request.client else "unknown").strip()
        key = f"{scope}:{ip}"
        now = time.time()
        cutoff = now - window_seconds

        with _LOCK:
            q = _BUCKETS[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for {scope}. Try again later.",
                )
            q.append(now)

    return _dep
