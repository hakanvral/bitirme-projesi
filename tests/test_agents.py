"""Agents and pipeline with MockLLMClient (no network, CLAUDE.md §9)."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from pusula import pipeline
from pusula.agents import inputs as inputs_mod
from pusula.agents.batch import estimate_wall_clock, run_batch
from pusula.agents.numbers import allowed_numbers, check_report, find_numbers
from pusula.agents.schemas import Decision, RiskNarrative
from pusula.features.trend import rsi, trend_metrics
from pusula.llm.mock import MockLLMClient

UYARI = "Bu çıktı karar destek amaçlıdır, yatırım tavsiyesi değildir."


# ----------------------------------------------------------------------------- numbers
@pytest.mark.parametrize(
    "text,value",
    [
        ("%4,97", 4.97),
        ("4,97%", 4.97),
        ("0.0497", 0.0497),
        ("1.234,5", 1234.5),
        ("−%2,5", -2.5),
        ("300 baz puan", 300.0),
    ],
)
def test_turkish_number_parsing(text, value):
    assert find_numbers(text)[0].value == pytest.approx(value)


def test_names_with_digits_are_not_numbers():
    assert find_numbers("XU100, BIST30 ve VaR99 adları") == []


def test_numeric_check_matches_formats_and_flags_invented_numbers():
    allowed = allowed_numbers(
        {
            "var99_1g_yuzde": 4.97,
            "beta_xu100": 0.98,
            "oran": 0.025,
            "faiz_pp": -3.0,
            "not": "son 500 işlem günü",
        }
    )
    n, bad = check_report(
        {"t": "VaR %4,97, beta 0,98, %2,5 ve -300 bp, 500 gün; %5 civarı", "u": ["uydurma %17,3"]},
        allowed,
    )
    assert n == 7 and [b[1] for b in bad] == ["%17,3"]


# ----------------------------------------------------------------------------- schemas
def test_disclaimer_and_exact_reason_counts_are_enforced():
    base = {
        "karar": "BEKLE",
        "guven": 0.5,
        "vade": "1-3 ay",
        "lehte_gerekceler": ["a", "b", "c"],
        "aleyhte_gerekceler": ["d", "e", "f"],
        "temel_riskler": ["r"],
        "karari_degistirecek_kosullar": ["k"],
        "uyari": UYARI,
    }
    Decision(**base)
    with pytest.raises(ValidationError):
        Decision(**{**base, "uyari": "Dikkatli olun."})
    with pytest.raises(ValidationError):
        Decision(**{**base, "lehte_gerekceler": ["a", "b"]})
    with pytest.raises(ValidationError):
        Decision(**{**base, "karar": "SAT"})


# ----------------------------------------------------------------------------- trend
def test_trend_metrics_known_values():
    up = pd.Series(np.arange(1.0, 301.0))
    assert rsi(up) == 100.0
    m = trend_metrics(up)
    assert m["zirveden_uzaklik_52h_yuzde"] == 0.0
    assert m["momentum_3a_yuzde"] == pytest.approx((300 / 237 - 1) * 100, abs=0.01)


# ----------------------------------------------------------------------------- pipeline
def _fake_ctx(store, symbol, as_of, ablation="P+R+S", scenario_ids=None):
    ctx = inputs_mod.StockContext(symbol, as_of, "Energy", "electricity", "Örnek Enerji")
    ctx.blocks = {"trend": {"rsi14": 61.2, "momentum_3a_yuzde": 9.48}}
    if ablation in ("P+R", "P+R+S"):
        ctx.blocks["risk"] = {
            "risk_duzeyi": "Orta",
            "var99_1g_yuzde": 4.51,
            "cvar99_1g_yuzde": 6.24,
            "beta_xu100": 0.98,
        }
        ctx.limitations["risk"] = ["Uç kayıp (EVT) analizi için yeterli veri yok."]
    if ablation == "P+R+S":
        ctx.blocks["senaryo"] = {
            "senaryolar": [
                {
                    "senaryo": "Kur şoku (USD/TRY +%15)",
                    "tl_beklenen_getiri_degisimi_yuzde": -1.25,
                    "usd_beklenen_getiri_degisimi_yuzde": -8.32,
                }
            ]
        }
    return ctx


def _responses(bad_first_risk=False):
    risk_ok = json.dumps(
        {
            "ozet": "VaR %99 1 günde %4,51.",
            "risk_duzeyi_aciklamasi": "Orta.",
            "ana_risk_kaynaklari": ["beta 0,98"],
            "metriklerin_anlami": "CVaR %6,24",
            "veri_kisitlari": [],
            "uyari": UYARI,
        },
        ensure_ascii=False,
    )
    risk_bad = risk_ok.replace("%6,24", "%12,7")
    case = json.dumps({"tez": "t", "gerekceler": ["RSI 61,2", "momentum %9,48", "beta 0,98"]})
    return {
        "risk_analyst": [risk_bad, risk_ok] if bad_first_risk else risk_ok,
        "scenario_analyst": json.dumps(
            {
                "ozet": "Kur şokunda TL %-1,25, USD %-8,32.",
                "en_hassas_faktor": "USD/TRY",
                "bist30_enerji_karsilastirmasi": "x",
                "uyari": UYARI,
            },
            ensure_ascii=False,
        ),
        "bull": case,
        "bear": case,
        "judge": json.dumps(
            {
                "karar": "BEKLE",
                "guven": 0.4,
                "vade": "1-3 ay",
                "lehte_gerekceler": ["a", "b", "c"],
                "aleyhte_gerekceler": ["d", "e", "f"],
                "temel_riskler": ["r"],
                "karari_degistirecek_kosullar": ["k"],
                "uyari": UYARI,
            },
            ensure_ascii=False,
        ),
        "lean_decision": json.dumps({"karar": "AL", "guven": 0.6, "kisa_gerekce": "RSI 61,2."}),
        "auditor": json.dumps({"tutarli": True, "sorunlar": []}),
    }


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(pipeline, "build_stock_context", _fake_ctx)


def test_full_pipeline_runs_all_agents_and_audit_passes(patched):
    mock = MockLLMClient(_responses())
    run = pipeline.run_analysis(
        "ODAS", date(2026, 11, 20), client=mock, light_client=mock, persist=False
    )
    agents = [c.agent for c in run.calls]
    assert agents == ["risk_analyst", "scenario_analyst", "bull", "bear", "judge", "auditor"]
    assert run.audit.passed and run.audit.numbers_checked > 0 and run.decision.karar == "BEKLE"
    assert run.totals["cost_usd"] == 0.0 and run.prompt_versions["judge"] == "judge.v2"


def test_invented_number_triggers_one_regeneration(patched):
    mock = MockLLMClient(_responses(bad_first_risk=True))
    run = pipeline.run_analysis(
        "ODAS", date(2026, 11, 20), client=mock, light_client=mock, persist=False
    )
    assert run.audit.regenerated == ["risk_analyst:numeric"] and run.audit.numeric_ok
    fb = [m for m in mock.calls if "AUDIT FEEDBACK" in m[1]["content"]]
    assert len(fb) == 1 and "%12,7" in fb[0][1]["content"]


def test_lean_mode_is_a_single_call_and_ablation_p_has_no_risk(patched):
    mock = MockLLMClient(_responses())
    run = pipeline.run_analysis(
        "ODAS", date(2026, 11, 20), mode="lean", ablation="P", client=mock, persist=False
    )
    assert [c.agent for c in run.calls] == ["lean_decision"] and run.lean_decision.karar == "AL"
    assert set(run.inputs) == {"hisse", "analiz_tarihi", "trend", "veri_kisitlari"}


def test_anonymized_inputs_hide_names_and_dates(patched):
    mock = MockLLMClient(_responses())
    run = pipeline.run_analysis(
        "ODAS", date(2026, 11, 20), mode="anonymized", client=mock, light_client=mock, persist=False
    )
    text = json.dumps(run.inputs, ensure_ascii=False)
    for secret in ("ODAS", "Örnek Enerji", "Elektrik", "2026", "Enerji", "BIST30"):
        assert secret not in text
    assert run.inputs["hisse"]["kod"] == "Hisse A"


def test_usage_logging_and_run_persistence(tmp_path, patched):
    from pusula.data.store import Store

    st = Store(tmp_path / "t.duckdb")
    mock = MockLLMClient(_responses())
    run = pipeline.run_analysis("ODAS", date(2026, 11, 20), mode="lean", client=mock, persist=False)
    st.save_analysis_run(run.run_id, run.ticker, run.as_of, "lean:P+R+S", run.model_dump_json())
    _, rec = mock.generate(
        "AGENT: lean_decision\nx",
        "u",
        pipeline.LeanDecision,
        agent="lean_decision",
        prompt_version="v",
        use_cache=False,
    )
    st.log_llm_calls([rec])
    assert st.query("SELECT count(*) AS n FROM analysis_runs")["n"].iloc[0] == 1
    u = st.query("SELECT provider, attempts, json_failures, cost_usd FROM llm_usage")
    assert u.iloc[0].tolist() == ["mock", 1, 0, 0.0]


def test_batch_runner_and_wall_clock_estimate():
    res = run_batch([lambda: 1, lambda: 1 / 0, lambda: 3], max_concurrency=2)
    assert res[0] == 1 and isinstance(res[1], ZeroDivisionError) and res[2] == 3
    est = estimate_wall_clock(2100, 35, 14.0, 4)
    assert est["rate_bound_h"] == pytest.approx(1.0) and est["bottleneck"] == "latency"
    assert est["estimate_h"] == pytest.approx(2100 * 14 / 4 / 3600)


def test_risk_narrative_schema_requires_disclaimer():
    with pytest.raises(ValidationError):
        RiskNarrative(
            ozet="a",
            risk_duzeyi_aciklamasi="b",
            ana_risk_kaynaklari=["c"],
            metriklerin_anlami="d",
            uyari="",
        )


def test_consistency_failure_regenerates_named_report_and_downstream(patched):
    r = _responses()
    r["auditor"] = [
        json.dumps(
            {
                "tutarli": False,
                "sorunlar": ["senaryo listeleri çelişkili"],
                "sorunlu_raporlar": ["scenario_analyst"],
            },
            ensure_ascii=False,
        ),
        json.dumps({"tutarli": True, "sorunlar": [], "sorunlu_raporlar": []}),
    ]
    mock = MockLLMClient(r)
    run = pipeline.run_analysis(
        "ODAS", date(2026, 11, 20), client=mock, light_client=mock, persist=False
    )
    assert run.audit.regenerated == [
        "scenario_analyst:consistency",
        "bull:consistency",
        "bear:consistency",
        "judge:consistency",
    ]
    assert run.audit.passed and run.audit.consistency_ok
