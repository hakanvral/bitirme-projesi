"""Client-side rate limiting and retry with exponential backoff (D-057).

NVIDIA NIM's free tier allows roughly 40 requests per minute per account. A sliding-window
limiter keeps us at ``rpm`` (default 35) across all threads, and HTTP 429 / 5xx / timeouts are
retried with exponential backoff (honouring ``Retry-After``), so long batch runs survive.
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from collections.abc import Callable


class RateLimiter:
    def __init__(self, rpm: int, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep) -> None:  # fmt: skip
        self.rpm = max(1, int(rpm))
        self._clock, self._sleep = clock, sleep
        self._times: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Block until a request may be sent; returns the seconds waited."""
        waited = 0.0
        while True:
            with self._lock:
                now = self._clock()
                while self._times and now - self._times[0] >= 60.0:
                    self._times.popleft()
                if len(self._times) < self.rpm:
                    self._times.append(now)
                    return waited
                wait = 60.0 - (now - self._times[0]) + 0.01
            self._sleep(wait)
            waited += wait


def backoff_delay(attempt: int, base: float = 2.0, cap: float = 60.0,
                  retry_after: float | None = None) -> float:  # fmt: skip
    """Seconds to wait before retry number ``attempt`` (1, 2, ...), with jitter."""
    if retry_after is not None and retry_after > 0:
        return min(cap, retry_after)
    return min(cap, base * 2 ** (attempt - 1)) * (0.75 + 0.5 * random.random())
