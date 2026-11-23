"""The four agents (CLAUDE.md §6.4). Each agent = one versioned prompt + one output schema.

The user message is always ``INPUT JSON:`` followed by the precomputed input, so the model only
interprets numbers that Python computed.
"""

from __future__ import annotations

import json

from pydantic import BaseModel

from pusula.agents.numbers import allowed_numbers, check_report
from pusula.agents.prompts import system_prompt
from pusula.agents.schemas import (
    AuditResult,
    CaseArgument,
    ConsistencyCheck,
    Decision,
    LeanDecision,
    NumericIssue,
    RiskNarrative,
    ScenarioNarrative,
)
from pusula.llm.base import CallRecord, LLMClient

AGENT_SCHEMAS: dict[str, type[BaseModel]] = {
    "risk_analyst": RiskNarrative,
    "scenario_analyst": ScenarioNarrative,
    "bull": CaseArgument,
    "bear": CaseArgument,
    "judge": Decision,
    "lean_decision": LeanDecision,
    "auditor": ConsistencyCheck,
}


def _user(payload: dict, extra: str = "") -> str:
    text = "INPUT JSON:\n" + json.dumps(payload, ensure_ascii=False, indent=1)
    return text + (f"\n\n{extra}" if extra else "")


def call_agent(
    client: LLMClient, agent: str, payload: dict, run_id: str | None = None, feedback: str = ""
) -> tuple[BaseModel, CallRecord]:
    schema = AGENT_SCHEMAS[agent]
    version, system = system_prompt(agent, schema)
    return client.generate(
        system, _user(payload, feedback), schema, agent=agent, prompt_version=version, run_id=run_id
    )


# --------------------------------------------------------------------------- audit (D-058)
def numeric_audit(reports: dict[str, BaseModel], inputs: dict) -> tuple[int, list[NumericIssue]]:
    allowed = allowed_numbers(inputs)
    n_total, issues = 0, []
    for name, rep in reports.items():
        if rep is None:
            continue
        n, bad = check_report(rep.model_dump(exclude={"guven"}), allowed)
        n_total += n
        issues += [NumericIssue(report=name, field=f, text=tx, value=v) for f, tx, v in bad]
    return n_total, issues


def numeric_feedback(issues: list[NumericIssue]) -> str:
    listed = ", ".join(f"'{i.text}' ({i.field})" for i in issues[:15])
    return (
        "AUDIT FEEDBACK: your previous answer contained numbers that are NOT in the input "
        f"JSON: {listed}. Rewrite the answer using only numbers from the input JSON "
        "(or describe them in words)."
    )


def consistency_payload(inputs: dict, reports: dict[str, BaseModel]) -> dict:
    return {
        "girdi": inputs,
        "raporlar": {k: v.model_dump() for k, v in reports.items() if v is not None},
    }


def audit(
    reports: dict[str, BaseModel], inputs: dict, light: LLMClient | None, run_id: str | None = None
) -> tuple[AuditResult, list[CallRecord]]:
    """Deterministic numeric check, then (optionally) an LLM consistency check."""
    n, issues = numeric_audit(reports, inputs)
    res = AuditResult(
        passed=not issues, numeric_ok=not issues, numbers_checked=n, numeric_issues=issues
    )
    recs: list[CallRecord] = []
    if light is not None:
        cc, rec = call_agent(light, "auditor", consistency_payload(inputs, reports), run_id)
        recs.append(rec)
        res.consistency_checked = True
        res.consistency_ok = cc.tutarli
        res.consistency_issues = cc.sorunlar
        res.problem_reports = list(cc.sorunlu_raporlar)
        res.passed = res.passed and cc.tutarli
    return res, recs
