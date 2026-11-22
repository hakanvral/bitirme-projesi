"""Orchestrator (CLAUDE.md §6.4): ``run_analysis(ticker, as_of, scenarios, mode)``.

Modes (D-059, D-060):
* ``full``       – Risk Analisti, Senaryo Analisti, Bull, Bear, Judge, then the Denetçi;
* ``anonymized`` – the same with "Hisse A", "Grup A/B" and no absolute dates (look-ahead control);
* ``lean``       – one structured decision call on the precomputed JSON (for the E4 backtest);
                   only the deterministic numeric audit runs (free), the LLM audit is optional.
``ablation`` selects the input blocks: P (price/trend), P+R (+ risk), P+R+S (+ scenarios).

Audit policy (D-058): a report with numbers not found in the input is regenerated once with the
offending numbers fed back; if the LLM consistency check fails, the decision is regenerated once
with the issues fed back. Both events are recorded in ``AuditResult.regenerated``.
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from pusula.agents.agents import audit, call_agent, numeric_audit, numeric_feedback
from pusula.agents.inputs import ABLATIONS, build_stock_context, to_input_json
from pusula.agents.schemas import (
    AuditResult,
    CaseArgument,
    Decision,
    LeanDecision,
    RiskNarrative,
    ScenarioNarrative,
)
from pusula.config import get_settings
from pusula.data.store import Store
from pusula.llm.base import CallRecord, LLMClient

Mode = Literal["full", "lean", "anonymized"]


class CallSummary(BaseModel):
    agent: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_s: float
    attempts: int
    json_failures: int
    cached: bool


class AnalysisRun(BaseModel):
    run_id: str
    ticker: str
    as_of: date
    mode: str
    ablation: str
    scenarios: list[str] | None
    provider: str
    model: str
    model_light: str | None
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    inputs: dict
    risk_narrative: RiskNarrative | None = None
    scenario_narrative: ScenarioNarrative | None = None
    bull: CaseArgument | None = None
    bear: CaseArgument | None = None
    decision: Decision | None = None
    lean_decision: LeanDecision | None = None
    audit: AuditResult | None = None
    calls: list[CallSummary] = Field(default_factory=list)
    totals: dict = Field(default_factory=dict)
    wall_clock_s: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC).replace(tzinfo=None))


def _summ(r: CallRecord) -> CallSummary:
    return CallSummary(
        agent=r.agent,
        model=r.model,
        input_tokens=r.input_tokens,
        output_tokens=r.output_tokens,
        latency_s=round(r.latency_s, 2),
        attempts=r.attempts,
        json_failures=r.json_failures,
        cached=r.cached,
    )


def run_analysis(
    ticker: str,
    as_of: date,
    scenarios: list[str] | None = None,
    mode: Mode = "full",
    ablation: str = "P+R+S",
    client: LLMClient | None = None,
    light_client: LLMClient | None = None,
    store: Store | None = None,
    persist: bool = True,
    llm_audit: bool | None = None,
) -> AnalysisRun:
    from pusula.agents.prompts import _raw
    from pusula.universe.load import to_yahoo

    if ablation not in ABLATIONS:
        raise ValueError(f"ablation must be one of {list(ABLATIONS)}")
    s = get_settings()
    store = store or Store(s.paths.db_path, s.paths.raw_dir)
    if client is None or (light_client is None and mode != "lean"):
        from pusula.llm.factory import get_client

        client = client or get_client(lean=(mode == "lean"))
        light_client = light_client or get_client(light=True)
    llm_audit = (mode != "lean") if llm_audit is None else llm_audit
    t0 = time.perf_counter()
    symbol = to_yahoo(ticker)
    run_id = str(uuid.uuid4())
    ctx = build_stock_context(store, symbol, as_of, ablation, scenarios)
    inputs = to_input_json(ctx, anonymized=(mode == "anonymized"))
    run = AnalysisRun(
        run_id=run_id,
        ticker=symbol,
        as_of=as_of,
        mode=mode,
        ablation=ablation,
        scenarios=scenarios,
        provider=client.provider,
        model=client.model,
        model_light=light_client.model if light_client else None,
        inputs=inputs,
    )
    records: list[CallRecord] = []

    def call(agent, payload, feedback=""):
        obj, rec = call_agent(client, agent, payload, run_id, feedback)
        records.append(rec)
        run.prompt_versions[agent] = rec.prompt_version
        return obj

    if mode == "lean":
        run.lean_decision = call("lean_decision", inputs)
        n, issues = numeric_audit({"lean": run.lean_decision}, inputs)
        run.audit = AuditResult(
            passed=not issues, numeric_ok=not issues, numbers_checked=n, numeric_issues=issues
        )
    else:
        parts = ABLATIONS[ablation]
        reports: dict[str, BaseModel | None] = {}
        if "risk" in parts:
            reports["risk_analyst"] = call("risk_analyst", inputs)
        if "senaryo" in parts and inputs.get("senaryo"):
            reports["scenario_analyst"] = call("scenario_analyst", inputs)
        debate_in = {**inputs, "analist_raporlari": {k: v.model_dump() for k, v in reports.items()}}
        reports["bull"] = call("bull", debate_in)
        reports["bear"] = call("bear", debate_in)
        judge_in = {
            **debate_in,
            "bull": reports["bull"].model_dump(),
            "bear": reports["bear"].model_dump(),
        }
        reports["judge"] = call("judge", judge_in)

        # --- audit: numeric first; regenerate each offending report once
        regenerated: list[str] = []
        _, issues = numeric_audit(reports, inputs)
        for name in dict.fromkeys(i.report for i in issues):
            payload = (
                judge_in if name == "judge" else (debate_in if name in ("bull", "bear") else inputs)
            )
            mine = [i for i in issues if i.report == name]
            reports[name] = call(name, payload, numeric_feedback(mine))
            regenerated.append(f"{name}:numeric")
        res, recs = audit(reports, inputs, light_client if llm_audit else None, run_id)
        records += recs
        if res.consistency_checked and not res.consistency_ok and "judge:consistency" not in (
                regenerated):  # fmt: skip
            fb = (
                "AUDIT FEEDBACK: the consistency check found these problems: "
                + "; ".join(res.consistency_issues)
                + ". Fix them in your decision."
            )
            reports["judge"] = call("judge", judge_in, fb)
            regenerated.append("judge:consistency")
            res, recs = audit(reports, inputs, light_client if llm_audit else None, run_id)
            records += recs
        res.regenerated = regenerated
        run.audit = res
        run.risk_narrative = reports.get("risk_analyst")
        run.scenario_narrative = reports.get("scenario_analyst")
        run.bull, run.bear, run.decision = reports["bull"], reports["bear"], reports["judge"]

    run.calls = [_summ(r) for r in records]
    live = [r for r in records if not r.cached]
    run.totals = {
        "calls": len(records),
        "live_calls": len(live),
        "input_tokens": sum(r.input_tokens for r in records),
        "output_tokens": sum(r.output_tokens for r in records),
        "llm_latency_s": round(sum(r.latency_s for r in live), 2),
        "json_failures": sum(r.json_failures for r in records),
        "requests": sum(r.attempts for r in live),
        "cost_usd": 0.0,
    }
    run.wall_clock_s = round(time.perf_counter() - t0, 2)
    for name in ("risk_analyst", "scenario_analyst", "bull", "bear", "judge", "lean_decision",
                 "auditor"):  # fmt: skip
        if name not in run.prompt_versions and any(r.agent == name for r in records):
            run.prompt_versions[name] = _raw(name)[0]
    if persist:
        store.log_llm_calls(records)
        payload = run.model_dump_json()
        store.save_analysis_run(run_id, symbol, as_of, f"{mode}:{ablation}", payload)
        out = s.paths.results_dir / "analysis_runs" / f"{as_of:%Y%m%d}"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{symbol}_{mode}_{ablation}_{run_id[:8]}.json").write_text(
            json.dumps(json.loads(payload), ensure_ascii=False, indent=1), encoding="utf-8"
        )
    return run


def run_agent_report(
    ticker: str,
    as_of: date,
    agent: str,
    client: LLMClient | None = None,
    store: Store | None = None,
):
    """One analyst report on its own (buttons on the risk / scenario pages). Returns
    (report, CallSummary, numeric AuditResult)."""
    from pusula.universe.load import to_yahoo

    if agent not in ("risk_analyst", "scenario_analyst"):
        raise ValueError("agent must be risk_analyst or scenario_analyst")
    s = get_settings()
    store = store or Store(s.paths.db_path, s.paths.raw_dir)
    if client is None:
        from pusula.llm.factory import get_client

        client = get_client()
    ablation = "P+R" if agent == "risk_analyst" else "P+R+S"
    inputs = to_input_json(build_stock_context(store, to_yahoo(ticker), as_of, ablation))
    if agent == "scenario_analyst":
        inputs.pop("risk", None)
    report, rec = call_agent(client, agent, inputs)
    n, issues = numeric_audit({agent: report}, inputs)
    if issues:
        report, rec2 = call_agent(client, agent, inputs, feedback=numeric_feedback(issues))
        store.log_llm_calls([rec])
        rec = rec2
        n, issues = numeric_audit({agent: report}, inputs)
    store.log_llm_calls([rec])
    aud = AuditResult(
        passed=not issues, numeric_ok=not issues, numbers_checked=n, numeric_issues=issues
    )
    return report, _summ(rec), aud
