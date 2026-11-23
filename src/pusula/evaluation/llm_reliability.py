"""E5 · LLM reliability (CLAUDE.md §6.5, D-071).

Sample (reduced, D-074): 10 stock-weeks drawn (seeded) from the E4 inputs (P+R+S variant, lean
prompt); they are the first 10 items of the original 20-item draw.

* **Repeatability**: k = 5 repeated lean calls per stock-week with the production settings
  (temperature 0.2, reasoning off). Repeats bypass the response cache with a ``#rep<k>`` suffix
  on the prompt version (the prompt itself is unchanged). Agreement = Fleiss' κ.
* **Cross-model**: the same 10 inputs, lean prompt, with Nemotron 3 Ultra (reasoning off),
  Kimi K3.1 Pro and Gemma 4 31B (provider defaults). Pairwise agreement and Fleiss' κ.
* **Reasoning on vs off** (Nemotron): agreement and Cohen's κ.
* **Decision distribution per model** (is there a BEKLE bias?).
* **Full-mode audit**: 4 full analyses (THYAO, AKBNK; ENJSA, TUPRS = the demo warm-up runs) on
  the latest data date: numeric
  faithfulness of the final reports, consistency result and regeneration rate. These runs also
  warm the cache for the demo (``pusula.demo.warmup``).
* **Overall**: JSON failure rate and latency distribution per agent and mode from ``llm_usage``.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import date

import numpy as np
import pandas as pd

from pusula.agents.agents import AGENT_SCHEMAS, _user
from pusula.agents.batch import estimate_wall_clock, run_batch
from pusula.agents.prompts import system_prompt
from pusula.config import get_settings
from pusula.data.store import Store
from pusula.evaluation.common import mark_latest, new_run_dir, save_fig, save_table
from pusula.evaluation.trading_backtest import inputs_dir, variant_input
from pusula.logging_setup import setup_logging

CATS = ["AL", "ALMA", "BEKLE"]
N_ITEMS, K_REPEATS = 10, 5  # reduced E5 (D-074); the 10 items are the first 10 of the
SAMPLE_DRAW = 20  # original 20-item draw, so answers cached for that draw stay usable
OTHER_MODELS = {"Kimi K3.1 Pro": "moonshotai/kimi-k3.1-pro", "Gemma 4 31B": "google/gemma-4-31b-it"}
FULL_SET = {"BIST30": ["THYAO", "AKBNK"], "Energy": ["ENJSA", "TUPRS"]}  # = demo warm-up set


# --------------------------------------------------------------------------- agreement
def fleiss_kappa(labels: pd.DataFrame, cats=CATS) -> float:
    """Fleiss' κ; rows = items, columns = raters (labels as strings; NaN rows dropped)."""
    x = labels.dropna()
    if x.empty or x.shape[1] < 2:
        return np.nan
    n = x.shape[1]
    counts = np.stack([(x == c).sum(axis=1).to_numpy() for c in cats], axis=1)
    p_j = counts.sum(axis=0) / counts.sum()
    p_i = (np.sum(counts**2, axis=1) - n) / (n * (n - 1))
    p_bar, p_e = p_i.mean(), np.sum(p_j**2)
    return float((p_bar - p_e) / (1 - p_e)) if p_e < 1 else 1.0


def cohen_kappa(a: pd.Series, b: pd.Series, cats=CATS) -> float:
    d = pd.concat([a, b], axis=1).dropna()
    if d.empty:
        return np.nan
    po = float((d.iloc[:, 0] == d.iloc[:, 1]).mean())
    pe = sum(float((d.iloc[:, 0] == c).mean() * (d.iloc[:, 1] == c).mean()) for c in cats)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


# --------------------------------------------------------------------------- clients
def client_for(model: str, reasoning_off: bool, max_backoff_retries: int | None = None):
    from pusula.llm.factory import _api_key, shared_cache, shared_limiter
    from pusula.llm.openai_compat import OpenAICompatibleClient

    cfg = get_settings().llm
    extra = dict(cfg.extra_body)
    if reasoning_off and model == cfg.model:
        extra.update(cfg.extra_body_lean)
    return OpenAICompatibleClient(
        model,
        cfg.base_url,
        _api_key(),
        limiter=shared_limiter(),
        timeout_s=max(cfg.timeout_s, 300),
        json_mode=cfg.json_mode,
        max_backoff_retries=(
            cfg.max_backoff_retries if max_backoff_retries is None else max_backoff_retries
        ),
        extra_body=extra,
        cache=shared_cache(),
        max_json_retries=cfg.max_json_retries,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
    )


def lean_call(client, inp: dict, version_suffix: str = ""):
    version, system = system_prompt("lean_decision", AGENT_SCHEMAS["lean_decision"])
    return client.generate(
        system,
        _user(inp),
        AGENT_SCHEMAS["lean_decision"],
        agent="lean_decision",
        prompt_version=version + version_suffix,
        run_id="e5",
    )


def sample_items(seed: int) -> list[tuple[str, str, dict]]:
    files = sorted(inputs_dir().glob("*.json"))
    pool = []
    for f in files:
        recs = json.loads(f.read_text(encoding="utf-8"))
        d = date(int(f.stem[:4]), int(f.stem[4:6]), int(f.stem[6:]))
        for sym in sorted(recs):
            pool.append((str(d), sym, variant_input(recs[sym], sym, d, "P+R+S")))
    if len(pool) < N_ITEMS:
        raise RuntimeError("E4 inputs missing: run the E4 'inputs' stage first")
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(pool), size=SAMPLE_DRAW, replace=False)[:N_ITEMS]
    return [pool[i] for i in sorted(pick)]


# --------------------------------------------------------------------------- main parts
def run_calls(items, yes: bool, executor=None, max_backoff_retries=None) -> pd.DataFrame:
    """``executor(list_of_thunks) -> list of results/exceptions``; default: the parallel batch
    runner. The paced runner (``llm_runner``) passes a sequential, adaptive executor."""
    cfg = get_settings().llm
    jobs = []  # (label, rater, client, inp, suffix)
    mb = max_backoff_retries
    nemo_off = client_for(cfg.model, reasoning_off=True, max_backoff_retries=mb)
    nemo_on = client_for(cfg.model, reasoning_off=False, max_backoff_retries=mb)
    others = {
        name: client_for(m, reasoning_off=False, max_backoff_retries=mb)
        for name, m in OTHER_MODELS.items()
    }
    for i, (_, _, inp) in enumerate(items):
        for k in range(K_REPEATS):
            jobs.append((i, f"rep{k}", nemo_off, inp, "" if k == 0 else f"#rep{k}"))
        # the cache key does not contain the reasoning switch, so this needs its own suffix
        jobs.append((i, "reasoning_on", nemo_on, inp, "#reasoning_on"))
        for name, c in others.items():
            jobs.append((i, name, c, inp, ""))
    est = estimate_wall_clock(len(jobs), cfg.rpm, 30.0, cfg.max_concurrency)
    print(
        f"[e5] {len(jobs)} calls (cached ones are skipped); rough estimate "
        f"{est['estimate_h']:.2f} h (other models and reasoning-on calls are slow)",
        flush=True,
    )
    if not yes and input("Continue? [y/N] ").strip().lower() != "y":
        raise SystemExit("aborted")
    t0 = time.perf_counter()
    thunks = [(lambda c=c, inp=inp, sfx=sfx: lean_call(c, inp, sfx)) for _, _, c, inp, sfx in jobs]
    res = executor(thunks) if executor else run_batch(thunks, cfg.max_concurrency)
    rows, recs = [], []
    for (i, rater, c, _, _), r in zip(jobs, res, strict=True):
        if isinstance(r, Exception):
            rows.append(
                {"item": i, "rater": rater, "model": c.model, "karar": None, "error": str(r)[:200]}
            )
            continue
        obj, rec = r
        recs.append(rec)
        rows.append(
            {
                "item": i,
                "rater": rater,
                "model": c.model,
                "karar": obj.karar,
                "guven": obj.guven,
                "latency_s": rec.latency_s,
                "cached": rec.cached,
                "json_failures": rec.json_failures,
                "error": None,
            }
        )
    s = get_settings()
    Store(s.paths.db_path, s.paths.raw_dir).log_llm_calls([r for r in recs if not r.cached])
    print(f"[e5] calls done in {(time.perf_counter() - t0) / 60:.1f} min", flush=True)
    return pd.DataFrame(rows)


def full_runs(as_of: date) -> pd.DataFrame:
    from pusula.pipeline import run_analysis

    rows = []
    for u, ticks in FULL_SET.items():
        for tk in ticks:
            t0 = time.perf_counter()
            try:
                run = run_analysis(tk, as_of, mode="full")
            except Exception as exc:
                rows.append({"ticker": tk, "universe": u, "error": str(exc)[:200]})
                continue
            a = run.audit
            rows.append(
                {
                    "ticker": tk,
                    "universe": u,
                    "karar": run.decision.karar,
                    "guven": run.decision.guven,
                    "audit_passed": a.passed,
                    "numbers_checked": a.numbers_checked,
                    "numeric_issues_final": len(a.numeric_issues),
                    "faithfulness_final": 1 - len(a.numeric_issues) / max(1, a.numbers_checked),
                    "consistency_ok": a.consistency_ok,
                    "regenerated_numeric": sum(r.endswith(":numeric") for r in a.regenerated),
                    "regenerated_consistency": sum(
                        r.endswith(":consistency") for r in a.regenerated
                    ),
                    "calls": run.totals["calls"],
                    "live_calls": run.totals["live_calls"],
                    "json_failures": run.totals["json_failures"],
                    "wall_clock_s": time.perf_counter() - t0,
                    "error": None,
                }
            )
            print(f"[e5] full {tk}: {rows[-1].get('karar')} audit={a.passed}", flush=True)
    return pd.DataFrame(rows)


def usage_stats(store: Store) -> pd.DataFrame:
    u = store.query(
        "SELECT agent, model, attempts, json_failures, latency_s, error, "
        "output_tokens FROM llm_usage"
    )
    if u.empty:
        return u
    g = u.groupby(["model", "agent"])
    out = pd.DataFrame(
        {
            "calls": g.size(),
            "json_failure_rate": g["json_failures"].sum() / g["attempts"].sum(),
            "failed_calls": g["error"].apply(lambda s: s.notna().sum()),
            "latency_p50_s": g["latency_s"].median(),
            "latency_p90_s": g["latency_s"].quantile(0.9),
            "latency_max_s": g["latency_s"].max(),
            "output_tokens_p50": g["output_tokens"].median(),
        }
    ).reset_index()
    return out


def analyse(calls: pd.DataFrame, items, out) -> dict:
    piv = calls.pivot(index="item", columns="rater", values="karar")
    reps = [c for c in piv.columns if c.startswith("rep")]
    res = {
        "fleiss_kappa_repeats": fleiss_kappa(piv[reps]),
        "unanimous_share_repeats": float((piv[reps].nunique(axis=1) == 1).mean()),
    }
    models = ["rep0", *OTHER_MODELS]
    names = {"rep0": "Nemotron 3 Ultra"}
    res["fleiss_kappa_cross_model"] = fleiss_kappa(piv[[m for m in models if m in piv]])
    pair_rows = []
    present = [m for m in models if m in piv]
    for i, a in enumerate(present):
        for b in present[i + 1 :]:
            d = piv[[a, b]].dropna()
            pair_rows.append(
                {
                    "a": names.get(a, a),
                    "b": names.get(b, b),
                    "n": len(d),
                    "agreement": float((d[a] == d[b]).mean()) if len(d) else np.nan,
                    "cohen_kappa": cohen_kappa(piv[a], piv[b]),
                }
            )
    if "reasoning_on" in piv:
        d = piv[["rep0", "reasoning_on"]].dropna()
        pair_rows.append(
            {
                "a": "Nemotron (akıl yürütme kapalı)",
                "b": "Nemotron (açık)",
                "n": len(d),
                "agreement": float((d["rep0"] == d["reasoning_on"]).mean()),
                "cohen_kappa": cohen_kappa(piv["rep0"], piv["reasoning_on"]),
            }
        )
    dist = (
        calls[calls["rater"].isin([*models, "reasoning_on"])]
        .assign(
            rater=lambda x: x["rater"].replace(
                {"rep0": "Nemotron 3 Ultra", "reasoning_on": "Nemotron (akıl yürütme açık)"}
            )
        )
        .groupby(["rater", "karar"])
        .size()
        .unstack(fill_value=0)
    )
    dist = dist.div(dist.sum(axis=1), axis=0).reindex(columns=CATS, fill_value=0.0).reset_index()
    lat = (
        calls.assign(
            rater=lambda x: np.where(
                x["rater"].str.startswith("rep"), "Nemotron (kapalı)", x["rater"]
            )
        )
        .groupby("rater")["latency_s"]
        .describe(percentiles=[0.5, 0.9])
        .reset_index()
    )
    summary = pd.DataFrame([{"metric": k, "value": v} for k, v in res.items()])
    save_table(
        summary,
        out,
        "e5_agreement_summary",
        "{:.3f}",
        caption="E5: repeatability and cross-model agreement",
    )
    save_table(pd.DataFrame(pair_rows), out, "e5_pairwise_agreement", "{:.3f}")
    save_table(dist, out, "e5_decision_distribution", "{:.3f}")
    save_table(lat, out, "e5_latency_by_rater", "{:.2f}")
    items_tbl = pd.DataFrame(
        [{"item": i, "date": d, "symbol": s} for i, (d, s, _) in enumerate(items)]
    )
    save_table(items_tbl.merge(piv.reset_index(), on="item"), out, "e5_items_decisions")
    plot_dist(dist, out)
    return res


def plot_dist(dist: pd.DataFrame, out) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 3.2))
    left = np.zeros(len(dist))
    for c, col in zip(CATS, ("#33A02C", "#E31A1C", "#999999"), strict=True):
        ax.barh(dist["rater"], dist[c] * 100, left=left, color=col, label=c)
        left += dist[c].to_numpy() * 100
    ax.set_xlabel("karar payı, %")
    ax.set_title("E5: aynı 20 hisse-haftada modellerin karar dağılımı")
    ax.legend(ncol=3, fontsize=8, loc="lower right")
    fig.tight_layout()
    return save_fig(fig, out, "e5_decision_distribution")


def main(argv: list[str] | None = None, executor=None, max_backoff_retries=None) -> str:
    ap = argparse.ArgumentParser(description="E5 LLM reliability (resumable via the cache)")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--skip-full", action="store_true", help="skip the full-mode analyses")
    a = ap.parse_args(argv)
    setup_logging("WARNING")
    s = get_settings()
    store = Store(s.paths.db_path, s.paths.raw_dir)
    items = sample_items(s.project.random_seed)
    out = new_run_dir(
        "e5_llm",
        {
            "n_items": N_ITEMS,
            "k_repeats": K_REPEATS,
            "other_models": OTHER_MODELS,
            "full_set": FULL_SET,
            "temperature": s.llm.temperature,
        },
    )
    calls = run_calls(items, a.yes, executor, max_backoff_retries)
    calls.to_csv(out / "e5_calls.csv", index=False)
    res = analyse(calls, items, out)
    print(json.dumps(res, indent=1), flush=True)
    if not a.skip_full:
        as_of = store.prices()["date"].max().date()
        fr = full_runs(as_of)
        save_table(
            fr,
            out,
            "e5_full_mode_audit",
            "{:.3f}",
            caption="E5: auditor faithfulness and regeneration, 4 full analyses",
        )
    save_table(
        usage_stats(store),
        out,
        "e5_usage_by_agent",
        "{:.3f}",
        caption="E5: JSON failure rate and latency per agent (all logged calls)",
    )
    mark_latest(out)
    print(out)
    return str(out)


if __name__ == "__main__":
    main()
