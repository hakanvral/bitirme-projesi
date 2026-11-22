"""Precomputed, point-in-time JSON inputs for the agents (CLAUDE.md §2.1, §6.4).

Python computes, the LLM interprets: every number an agent may mention is in these blocks. Ratios
are given in percent (keys ending in ``_yuzde``) with two decimals, so the model can quote them
directly (D-058).

Blocks (E4 ablations select which are included, D-059):
* ``trend``   – price/trend metrics (P)
* ``risk``    – risk report summary with the given relative risk level (R)
* ``senaryo`` – macro scenario results and factor sensitivities (S)
* ``veri_kisitlari`` – data limitations relevant to the blocks that are present
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from pusula.app.i18n_tr import t
from pusula.config import get_settings
from pusula.data.store import Store
from pusula.features.returns import session_prices
from pusula.features.trend import trend_metrics
from pusula.macro.context import build_context, current_passthrough, make_engine
from pusula.macro.scenarios import load_presets, to_factor_shocks, universe_summary
from pusula.risk.engine import compute_risk_report, load_inputs
from pusula.universe.load import load_energy_candidates

ABLATIONS = {"P": ("trend",), "P+R": ("trend", "risk"), "P+R+S": ("trend", "risk", "senaryo")}
LEVEL_TR = {"dusuk": "Düşük", "orta": "Orta", "yuksek": "Yüksek", "cok_yuksek": "Çok Yüksek"}


def pct(x, nd: int = 2):
    return None if x is None or not np.isfinite(x) else round(float(x) * 100, nd)


@dataclass
class StockContext:
    symbol: str
    as_of: date
    universe: str
    sub_sector: str | None
    name: str | None
    blocks: dict = field(default_factory=dict)
    limitations: dict[str, list[str]] = field(default_factory=dict)  # per block


# --------------------------------------------------------------------------- risk
def risk_block(store: Store, symbol: str, as_of: date) -> tuple[dict, list[str]]:
    s = get_settings()
    row = store.query(
        "SELECT payload, risk_level, risk_score FROM risk_reports WHERE as_of = ? AND ticker = ? "
        "AND basis = 'TRY'",
        [as_of, symbol],
    )
    lim: list[str] = []
    if row.empty:
        rep = compute_risk_report(
            load_inputs(store, as_of), symbol, "TRY", s.risk, s.project.random_seed
        ).model_dump(mode="json")
        level, score = None, None
        lim.append("Bu tarih için evren risk hesaplaması yok; göreli risk düzeyi verilemedi.")
    else:
        rep = json.loads(row["payload"].iloc[0])
        level, score = row["risk_level"].iloc[0], row["risk_score"].iloc[0]
    evt = rep["evt"]
    failed = [m["name"] for m in rep["models"] if not m["fitted"]]
    block = {
        "risk_duzeyi": LEVEL_TR.get(level, "hesaplanmadı"),
        "risk_duzeyi_turu": "evren içi göreli (BIST30 + Enerji hisseleri, aynı tarih, nominal TRY)",
        "risk_skoru_yuzdelik": None if score is None else round(float(score), 1),
        "secilen_risk_modeli": rep["selected_model"],
        "getiri_bazi": "nominal TRY",
        "var95_1g_yuzde": pct(rep["horizon_1d"]["var95"]),
        "cvar95_1g_yuzde": pct(rep["horizon_1d"]["cvar95"]),
        "var99_1g_yuzde": pct(rep["horizon_1d"]["var99"]),
        "cvar99_1g_yuzde": pct(rep["horizon_1d"]["cvar99"]),
        "var99_10g_yuzde": pct(rep["horizon_10d"]["var99"]),
        "cvar99_10g_yuzde": pct(rep["horizon_10d"]["cvar99"]),
        "bir_ayda_yuzde10_kayip_olasiligi_yuzde": pct(rep["p_loss_10pct_1m"]),
        "azami_dusus_3ay_medyan_yuzde": pct(rep["drawdown_3m"]["p50"]),
        "azami_dusus_3ay_kotu_senaryo_p95_yuzde": pct(rep["drawdown_3m"]["p95"]),
        "yillik_oynaklik_yuzde": pct(rep["vol_ann_realized"]),
        "beta_xu100": None if rep["beta_xu100"] is None else round(rep["beta_xu100"], 2),
        "kuyruk_indeksi_xi": round(evt["xi"], 3) if evt.get("fitted") else None,
        "kalibrasyon_gun_sayisi": rep["n_window"],
    }
    if not evt.get("fitted"):
        lim.append("Uç kayıp (EVT) analizi için yeterli veri yok.")
    if any(w.startswith("short_history") for w in rep.get("warnings", [])):
        lim.append("Fiyat geçmişi kısa; risk modelleri daha az veriyle kalibre edildi.")
    if failed:
        lim.append(f"Bazı risk modelleri kalibre edilemedi: {', '.join(failed)}.")
    return block, lim


# --------------------------------------------------------------------------- trend
def trend_block(store: Store, symbol: str, as_of: date) -> dict:
    inp = load_inputs(store, as_of)
    return trend_metrics(session_prices(inp.prices, symbol, inp.sessions))


# --------------------------------------------------------------------------- scenarios
_MACRO: dict = {}


def _macro(store: Store, as_of: date):
    if as_of not in _MACRO:
        ctx = build_context(store, as_of)
        _MACRO[as_of] = (ctx, make_engine(ctx))
    return _MACRO[as_of]


def scenario_block(
    store: Store,
    symbol: str,
    as_of: date,
    scenario_ids: list[str] | None = None,
    horizon: str = "3m",
    mode: str = "propagated",
) -> tuple[dict, list[str]]:
    ctx, eng = _macro(store, as_of)
    lim: list[str] = []
    if symbol not in ctx.fits_a:
        return {}, ["Bu hisse için makro faktör modeli kurulamadı (yetersiz haftalık veri)."]
    pt = current_passthrough(ctx)
    presets = [p for p in load_presets() if scenario_ids is None or p.id in scenario_ids]
    rows = []
    for sc in presets:
        spec = to_factor_shocks(sc.shocks, eng.factors, pt)
        if not spec.factor_shocks:
            lim.append(f"'{sc.name_tr}' senaryosu çalıştırılamadı (faktör verisi yok).")
            continue
        r_try = eng.run(spec, horizon, mode, "TRY")
        r_usd = eng.run(spec, horizon, mode, "USD")
        a = r_try["stocks"][r_try["stocks"]["symbol"] == symbol].iloc[0]
        b = r_usd["stocks"][r_usd["stocks"]["symbol"] == symbol].iloc[0]
        us = universe_summary(r_try["stocks"])
        us = us[us["sample"] == "all"].set_index("universe")["d_exp_ret"]
        rows.append(
            {
                "senaryo": sc.name_tr,
                "tl_beklenen_getiri_degisimi_yuzde": pct(a["d_exp_ret"]),
                "usd_beklenen_getiri_degisimi_yuzde": pct(b["d_exp_ret"]),
                "var99_degisimi_yuzde_puan": pct(a["d_var99"]),
                "zarar_olasiligi_degisimi_yuzde_puan": pct(a["d_p_loss"]),
                "evren_ici_sira_degisimi": None
                if pd.isna(a["rank_change"])
                else int(a["rank_change"]),
                "bist30_ortalama_tl_degisim_yuzde": pct(us.get("BIST30")),
                "enerji_ortalama_tl_degisim_yuzde": pct(us.get("Energy")),
                "asiri_sok_tum_orneklem_kullanildi": bool(r_try["extrapolation_guard"]),
            }
        )
        if r_try["extrapolation_guard"]:
            lim.append(
                f"'{sc.name_tr}' şoku güncel rejimin deneyiminin çok dışında; "
                "tüm örneklem ilişkileri kullanıldı."
            )
    fit = ctx.fits_a[symbol]
    sd = ctx.fp.X.std()
    sens = [
        {
            "faktor": t(f"factor_{c}"),
            "haftalik_1_std_hareketine_tepki_yuzde": pct(fit.beta[c] * sd[c]),
            "istatistiksel_olarak_anlamli": bool(fit.pval[c] < 0.05),
        }
        for c in fit.factors
    ]
    block = {
        "vade": "3 ay" if horizon == "3m" else "1 ay",
        "mod": "yayılımlı (diğer faktörler koşullu hareket eder)"
        if mode == "propagated"
        else "yalıtılmış",
        "senaryolar": rows,
        "faktor_duyarliliklari": sens,
        "makro_model_aciklama_gucu_r2": round(fit.r2, 2),
        "faiz_faktoru": "2 yıllık tahvil faizi" if ctx.fp.rate_source == "tr_2y" else "TLREF",
    }
    if fit.r2 < 0.2:
        lim.append(
            "Makro faktörler bu hissenin haftalık getirisinin yalnızca küçük bir kısmını "
            "açıklıyor; senaryo etkileri belirsizdir."
        )
    sub = ctx.members.set_index("symbol")["sub_sector"].dropna().to_dict()
    for m in ctx.fp.missing:
        if m.startswith("ptf") and sub.get(symbol) == "electricity":
            lim.append("Elektrik piyasa fiyatı (PTF) verisi yok; bu etki modellenmedi.")
    return block, lim


# --------------------------------------------------------------------------- assemble
def build_stock_context(
    store: Store,
    symbol: str,
    as_of: date,
    ablation: str = "P+R+S",
    scenario_ids: list[str] | None = None,
) -> StockContext:
    from pusula.universe.members import universe_members

    mem = universe_members(as_of)
    rows = mem[mem["symbol"] == symbol]
    if rows.empty:
        raise ValueError(f"{symbol} is not in the universe at {as_of}")
    energy = rows[rows["universe"] == "Energy"]
    r = energy.iloc[0] if not energy.empty else rows.iloc[0]
    names = load_energy_candidates().set_index("ticker")["name"].to_dict()
    ctx = StockContext(symbol, as_of, r["universe"], r["sub_sector"], names.get(r["ticker"]))
    parts = ABLATIONS[ablation]
    ctx.blocks["trend"] = trend_block(store, symbol, as_of)
    if "risk" in parts:
        ctx.blocks["risk"], ctx.limitations["risk"] = risk_block(store, symbol, as_of)
    if "senaryo" in parts:
        ctx.blocks["senaryo"], ctx.limitations["senaryo"] = scenario_block(
            store, symbol, as_of, scenario_ids
        )
    return ctx


def to_input_json(ctx: StockContext, anonymized: bool = False) -> dict:
    """The JSON given to the agents. Anonymised mode (D-060): 'Hisse A', 'Grup A/B', no company
    or sector names, no absolute dates."""
    if anonymized:
        hisse = {"kod": "Hisse A", "grup": "Grup A" if ctx.universe == "BIST30" else "Grup B"}
        tarih = "t (analiz günü; mutlak tarih gizlendi)"
    else:
        hisse = {
            "kod": ctx.symbol.removesuffix(".IS"),
            "evren": "BIST30" if ctx.universe == "BIST30" else "Enerji",
        }
        if ctx.name:
            hisse["ad"] = ctx.name
        if ctx.sub_sector:
            hisse["alt_sektor"] = t(f"subsector_{ctx.sub_sector}")
        tarih = ctx.as_of.isoformat()
    out = {"hisse": hisse, "analiz_tarihi": tarih}
    out.update(json.loads(json.dumps(ctx.blocks, ensure_ascii=False)))
    lim = [x for v in ctx.limitations.values() for x in v]
    out["veri_kisitlari"] = lim
    if anonymized:
        out = _anonymize(out)
    return out


def _anonymize(obj):
    if isinstance(obj, dict):
        return {_anon_key(k): _anonymize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_anonymize(v) for v in obj]
    if isinstance(obj, str):
        return obj.replace("BIST30", "Grup A").replace("Enerji", "Grup B")
    return obj


def _anon_key(k: str) -> str:
    return k.replace("bist30", "grup_a").replace("enerji", "grup_b")
