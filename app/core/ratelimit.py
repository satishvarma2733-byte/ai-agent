"""In-process sliding-window limiter for auth endpoints.
Per API process only; move to Redis when the API runs as multiple replicas."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

_lock = threading.Lock()
_events: dict[str, deque[float]] = defaultdict(deque)


def _prune(key: str, window: float, now: float) -> deque[float]:
    q = _events[key]
    while q and now - q[0] > window:
        q.popleft()
    return q


def is_limited(key: str, limit: int, window_seconds: float) -> bool:
    with _lock:
        return len(_prune(key, window_seconds, time.monotonic())) >= limit


def hit(key: str, window_seconds: float) -> None:
    with _lock:
        now = time.monotonic()
        _prune(key, window_seconds, now).append(now)


def reset(key: str) -> None:
    with _lock:
        _events.pop(key, None)
