"""In-memory sliding-window rate limiter keyed by (limit name, client IP)."""

from __future__ import annotations

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from app.config import settings
from app.core.deps import client_ip
from app.core.errors import RateLimitedError

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque[float]] = {}
_last_sweep = 0.0
_SWEEP_INTERVAL = 60.0


def _limit_for(name: str) -> int:
    return int(getattr(settings, f"rate_limit_{name}"))


def reset_rate_limits() -> None:
    with _lock:
        _hits.clear()


def _sweep(now: float, window: float) -> None:
    """Drop idle keys so memory stays bounded (caller holds the lock)."""
    global _last_sweep
    if now - _last_sweep < _SWEEP_INTERVAL:
        return
    _last_sweep = now
    for key in [k for k, q in _hits.items() if not q or now - q[-1] >= window]:
        del _hits[key]


def check_rate_limit(name: str, ip: str) -> None:
    if not settings.rate_limit_enabled:
        return
    limit = _limit_for(name)
    window = float(settings.rate_limit_window_seconds)
    now = time.monotonic()
    with _lock:
        _sweep(now, window)
        q = _hits.setdefault((name, ip), deque())
        while q and now - q[0] >= window:
            q.popleft()
        if len(q) >= limit:
            retry_after = math.ceil(window - (now - q[0]))
            raise RateLimitedError("Too many requests, please try again later", retry_after=retry_after)
        q.append(now)


def rate_limit(name: str) -> Callable[[Request], None]:
    """Dependency factory; ``name`` is one of "login", "otp", "search"."""
    _limit_for(name)  # fail fast on unknown names

    def dependency(request: Request) -> None:
        check_rate_limit(name, client_ip(request))

    return dependency
