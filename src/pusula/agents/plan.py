"""Print wall-clock estimates for E4 and E5 at the configured rate limit (no LLM calls).

    uv run python -m pusula.agents.plan

Average latencies and requests per call are taken from ``llm_usage`` (measured live calls) when
available, otherwise from conservative defaults.
"""

from __future__ import annotations

import argparse

from pusula.agents.batch import estimate_wall_clock
from pusula.config import get_settings
from pusula.data.store import Store
from pusula.llm.factory import provider_info

DEFAULT_LATENCY = {"lean_decision": 30.0, "full_call": 45.0}


def measured(store: Store, model: str) -> dict[str, float]:
    q = store.query(
        "SELECT agent, avg(latency_s) AS lat, avg(attempts) AS att, count(*) AS n FROM llm_usage "
        "WHERE NOT cached AND model = ? AND error IS NULL GROUP BY agent",
        [model],
    )
    out = dict(DEFAULT_LATENCY)
    if not q.empty:
        lean = q[q["agent"] == "lean_decision"]
        full = q[q["agent"] != "lean_decision"]
        if not lean.empty:
            out["lean_decision"] = float(lean["lat"].iloc[0] / max(lean["att"].iloc[0], 1))
        if not full.empty:
            out["full_call"] = float(
                (full["lat"] * full["n"]).sum() / (full["att"] * full["n"]).sum()
            )
    return out


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stocks", type=int, default=10)
    p.add_argument("--weeks", type=int, default=52)
    p.add_argument("--e5-sample", type=int, default=20, help="analyses repeated k=5 times")
    p.add_argument("--lean-latency", type=float, default=None, help="override (seconds)")
    p.add_argument("--full-latency", type=float, default=None, help="override (seconds)")
    a = p.parse_args(argv)
    s = get_settings()
    info = provider_info()
    lat = measured(Store(s.paths.db_path), info["model"])
    if a.lean_latency:
        lat["lean_decision"] = a.lean_latency
    if a.full_latency:
        lat["full_call"] = a.full_latency
    rpm, conc = s.llm.rpm, s.llm.max_concurrency
    e4 = a.stocks * a.weeks * 4  # P, P+R, P+R+S, anonymized (lean: 1 request each)
    full_sample = 40 * 6  # full Bull/Bear/Judge pipeline on 40 stock-weeks (~6 requests)
    audit_sample = round(0.10 * e4)
    e5 = a.e5_sample * 5 * 6
    print(
        f"Model {info['model']} · {rpm} RPM · concurrency {conc} · "
        f"latency lean {lat['lean_decision']:.1f}s, full-pipeline call {lat['full_call']:.1f}s"
    )
    for name, n, lt in (
        ("E4 lean (4 variants)", e4, lat["lean_decision"]),
        ("E4 full pipeline sample", full_sample, lat["full_call"]),
        ("E4 auditor 10% sample", audit_sample, lat["full_call"]),
        ("E5 (k=5 repeats, full)", e5, lat["full_call"]),
    ):
        for c in (1, conc):
            est = estimate_wall_clock(n, rpm, lt, c)
            print(
                f"{name:28s} requests={n:5d} concurrency={c}: ~{est['estimate_h']:.1f} h "
                f"(bottleneck: {est['bottleneck']})"
            )


if __name__ == "__main__":
    main()
