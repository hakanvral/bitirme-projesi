"""Resumable batch runs and wall-clock planning for E4/E5 (D-057).

* Resumable: every agent call goes through the disk cache, so rerunning a batch after an
  interruption skips finished items (cached calls cost no request and no time).
* Throughput: up to ``max_concurrency`` requests in flight, all sharing one rate limiter
  (default 35 requests/minute), so parallelism helps only while the limiter is not the bottleneck.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

log = logging.getLogger(__name__)


def run_batch[T](
    tasks: list[Callable[[], T]],
    max_concurrency: int = 4,
    on_done: Callable[[int, T | Exception], None] | None = None,
) -> list[T | Exception]:
    """Run callables in a thread pool; failures are returned (not raised) so a long batch never
    stops because of one item."""
    results: list[T | Exception] = [None] * len(tasks)  # type: ignore[list-item]
    with ThreadPoolExecutor(max_workers=max(1, max_concurrency)) as ex:
        futs = {ex.submit(fn): i for i, fn in enumerate(tasks)}
        for f in as_completed(futs):
            i = futs[f]
            try:
                results[i] = f.result()
            except Exception as exc:  # recorded, batch continues
                log.warning("batch item %d failed: %s", i, exc)
                results[i] = exc
            if on_done:
                on_done(i, results[i])
    return results


def estimate_wall_clock(
    n_requests: int, rpm: int, avg_latency_s: float, concurrency: int
) -> dict[str, float]:
    """Wall-clock estimate: the slower of the rate limit and the latency/concurrency bound."""
    rate_bound = n_requests / rpm * 60
    latency_bound = n_requests * avg_latency_s / max(1, concurrency)
    total = max(rate_bound, latency_bound)
    return {
        "requests": n_requests,
        "rate_bound_h": rate_bound / 3600,
        "latency_bound_h": latency_bound / 3600,
        "estimate_h": total / 3600,
        "bottleneck": "rate limit" if rate_bound >= latency_bound else "latency",
    }
