"""Paper figure pack in Turkish → ``results/paper/figures_tr/`` (D-077).

    uv run python -m pusula.evaluation.paper_figures                # everything available
    uv run python -m pusula.evaluation.paper_figures --only s02 t01 # selected items

Rules:
* **Data freeze (D-076):** only data already stored (as of 2026-11-20) and the saved experiment
  results are read; nothing is downloaded and no input file is changed. PTF is not used.
* Style: Turkish labels and number format (decimal comma, percent sign before the number:
  ``%2,5``); BIST30 blue, Energy orange, sub-sectors as shades of orange; PNG at 300 dpi + SVG;
  numbered files ``sekil_NN_<name>`` and ``tablo_NN_<name>`` (LaTeX + Markdown + CSV).
* LLM-based items (Ş14, Ş15, the agent comparison table) are produced only when the LLM results
  exist; otherwise they are skipped with a note.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from pusula.config import ROOT_DIR, get_regimes, get_settings
from pusula.data.store import Store
from pusula.evaluation.common import latest_run
from pusula.logging_setup import setup_logging

OUT = get_settings().paths.results_dir / "paper" / "figures_tr"
AS_OF = date(2026, 11, 20)  # data freeze date (D-076)
BLUE, ORANGE = "#2E6FBA", "#E07B1F"
SUB_COLORS = {"electricity": "#E07B1F", "natural_gas": "#F4A259", "refining_petroleum": "#A04A12"}
SUB_TR = {
    "electricity": "Elektrik",
    "natural_gas": "Doğalgaz",
    "refining_petroleum": "Rafineri/akaryakıt",
}
UNI_TR = {"BIST30": "BIST30", "Energy": "Enerji"}
MODEL_TR = {
    "HS": "HS",
    "FHS": "FHS",
    "GBM": "GBM",
    "Merton": "Merton",
    "GARCH-t": "GARCH-t",
    "critic_insample": "Kritik (örneklem içi)",
    "critic_holdout": "Kritik (hold-out)",
}
REGIME_SHORT = {
    "crisis_2018": "2018 kriz",
    "easing_2019_2020": "2019–20 gevşeme",
    "tightening_2020_2021": "2020–21 sıkılaştırma",
    "unorthodox_2021_2023": "2021–23 düşük faiz",
    "normalization_2023_2024": "2023–24 normalleşme",
    "easing_2024_2026": "2024–26 gevşeme",
}


# --------------------------------------------------------------------------- style helpers
def plt_setup():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.dpi": 300,
            "axes.grid": True,
            "grid.alpha": 0.25,
            "legend.frameon": False,
        }
    )
    return plt


def tr_num(x: float, nd: int = 1) -> str:
    """Turkish number: thousands dot, decimal comma."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    s = f"{abs(x):,.{nd}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("−" if x < 0 and float(s.replace(".", "").replace(",", ".")) != 0 else "") + s


def tr_pct(x: float, nd: int = 1, sign: bool = False) -> str:
    """Fraction → Turkish percent ('%2,5', '−%1,2')."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "–"
    v = x * 100
    pre = "−" if v < 0 else ("+" if sign and v > 0 else "")
    return f"{pre}%{tr_num(abs(v), nd)}"


def fmt_axis(ax, axis: str = "y", kind: str = "num", nd: int = 0):
    """Turkish tick labels. kind: num | pct (value already in percent) | frac (fraction)."""
    from matplotlib.ticker import FuncFormatter

    def f(v, _):
        if kind == "pct":
            return ("−" if v < 0 else "") + f"%{tr_num(abs(v), nd)}"
        if kind == "frac":
            return ("−" if v < 0 else "") + f"%{tr_num(abs(v) * 100, nd)}"
        return tr_num(v, nd)

    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(FuncFormatter(f))


def save_fig(fig, name: str) -> list[str]:
    import matplotlib.pyplot as plt

    OUT.mkdir(parents=True, exist_ok=True)
    files = [f"{name}.png", f"{name}.svg"]
    fig.savefig(OUT / files[0], dpi=300, bbox_inches="tight")
    fig.savefig(OUT / files[1], bbox_inches="tight")
    plt.close(fig)
    return files


def save_tab(df: pd.DataFrame, name: str, caption: str) -> list[str]:
    """LaTeX + Markdown + CSV. ``df`` must already hold formatted (Turkish) strings."""
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / f"{name}.csv", index=False)
    (OUT / f"{name}.md").write_text(
        f"**{caption}**\n\n" + df.to_markdown(index=False) + "\n", encoding="utf-8"
    )
    tex = df.to_latex(index=False, escape=True, caption=caption, label=f"tab:{name}")
    (OUT / f"{name}.tex").write_text(tex, encoding="utf-8")
    return [f"{name}.tex", f"{name}.md", f"{name}.csv"]


def store() -> Store:
    s = get_settings()
    return Store(s.paths.db_path, s.paths.raw_dir, read_only=True)


def regime_bands(ax, start: pd.Timestamp, end: pd.Timestamp, label_y: float | None = None):
    """Alternating grey bands for the policy regimes (config/regimes.yaml)."""
    for i, rg in enumerate(get_regimes().regimes):
        lo = max(pd.Timestamp(rg.start), start)
        hi = min(pd.Timestamp(rg.end) if rg.end else end, end)
        if lo >= hi:
            continue
        if i % 2 == 0:
            ax.axvspan(lo, hi, color="#9E9E9E", alpha=0.12, lw=0)
        if label_y is not None:  # two label rows so neighbouring names do not overlap
            ax.text(
                lo + (hi - lo) / 2,
                label_y - (0.09 if i % 2 else 0.0),
                REGIME_SHORT.get(rg.id, rg.id),
                ha="center",
                va="top",
                fontsize=6.5,
                color="#555555",
                transform=ax.get_xaxis_transform(),
            )


def members() -> pd.DataFrame:
    from pusula.universe.members import universe_members

    return universe_members(get_settings().project.reference_date)


# --------------------------------------------------------------------------- Ş2
def s02_macro() -> list[str]:
    plt = plt_setup()
    m = store().macro(["policy_rate", "usdtry", "cds_5y"])
    m = m[m["date"] <= pd.Timestamp(AS_OF)]
    start, end = pd.Timestamp("2018-01-01"), pd.Timestamp(AS_OF)
    fig, axes = plt.subplots(3, 1, figsize=(7.2, 6.4), sharex=True)
    spec = [
        ("policy_rate", "Politika faizi (1 hafta repo)", "pct", 0),
        ("usdtry", "USD/TRY", "num", 0),
        ("cds_5y", "Türkiye 5 yıllık CDS (baz puan)", "num", 0),
    ]
    for k, (ax, (sid, title, kind, nd)) in enumerate(zip(axes, spec, strict=True)):
        s = m[m["series"] == sid].set_index("date")["value"].sort_index()
        regime_bands(ax, start, end, label_y=0.98 if k == 0 else None)
        step = "steps-post" if sid == "policy_rate" else "default"  # the policy rate is a step
        ax.plot(s.index, s.to_numpy(), color="#333333", lw=1.1, drawstyle=step)
        if k == 0:  # headroom for the regime labels
            ax.set_ylim(0, s.max() * 1.3)
        ax.set_title(title, loc="left")
        fmt_axis(ax, "y", kind, nd)
        ax.set_xlim(start, end)
    axes[-1].set_xlabel("")
    fig.suptitle(
        "Makro görünüm 2018–2026 ve para politikası rejimleri", fontsize=11, x=0.02, ha="left"
    )
    fig.tight_layout()
    return save_fig(fig, "sekil_02_makro_seriler")


# --------------------------------------------------------------------------- Ş3
def _risk_payload(sym: str, d: date = AS_OF, basis: str = "TRY") -> dict:
    r = store().query(
        "SELECT payload FROM risk_reports WHERE as_of = ? AND ticker = ? AND basis = ?",
        [d, sym, basis],
    )
    if r.empty:
        raise RuntimeError(f"no stored risk report for {sym} at {d}")
    return json.loads(r["payload"].iloc[0])


def s03_fan() -> list[str]:
    from pusula.features.returns import session_prices
    from pusula.risk.engine import load_inputs

    plt = plt_setup()
    inp = load_inputs(store(), AS_OF)
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.2), sharey=True)
    for ax, (tk, col) in zip(axes, (("THYAO", BLUE), ("ENJSA", ORANGE)), strict=True):
        p = _risk_payload(f"{tk}.IS")
        fan = p["fan_chart"]
        px = session_prices(inp.prices, f"{tk}.IS", inp.sessions).dropna().iloc[-120:]
        hist = px / px.iloc[-1]
        x_hist = np.arange(-len(hist) + 1, 1)
        h = len(fan["p50"])
        x_f = np.arange(0, h + 1)

        def band(k, fan=fan):
            return np.concatenate([[1.0], np.asarray(fan[k])])

        ax.plot(x_hist, hist.to_numpy(), color="#333333", lw=1, label="Gerçekleşen (son 120 gün)")
        ax.fill_between(x_f, band("p5"), band("p95"), color=col, alpha=0.18, lw=0, label="%5–%95")
        ax.fill_between(x_f, band("p25"), band("p75"), color=col, alpha=0.35, lw=0, label="%25–%75")
        ax.plot(x_f, band("p50"), color=col, lw=1.4, label="Medyan")
        ax.axvline(0, color="#777777", lw=0.8, ls=":")
        model = p["selected_model"]
        lvl = {
            "dusuk": "Düşük",
            "orta": "Orta",
            "yuksek": "Yüksek",
            "cok_yuksek": "Çok Yüksek",
        }.get(p.get("risk_level") or "", "–")
        ax.set_title(f"{tk}: model {model}, risk düzeyi {lvl}", loc="left")
        ax.set_xlabel("işlem günü (0 = 20.11.2026)")
        fmt_axis(ax, "y", "num", 2)
    axes[0].set_ylabel("fiyat (20.11.2026 = 1)")
    axes[0].legend(fontsize=7, loc="upper left")
    fig.suptitle(
        "Monte Carlo yelpaze grafiği, 3 ay (63 işlem günü), nominal TL",
        fontsize=11,
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    return save_fig(fig, "sekil_03_yelpaze_THYAO_ENJSA")


# --------------------------------------------------------------------------- Ş4
def s04_model_selection() -> list[str]:
    plt = plt_setup()
    e1 = latest_run("e1_var")
    shares = pd.read_csv(e1 / "e1_model_selection_shares.csv").set_index("model")
    snap = store().query(
        "SELECT payload FROM risk_reports WHERE as_of = ? AND basis = 'TRY'", [AS_OF]
    )
    rows = [json.loads(x) for x in snap["payload"]]
    snap_df = pd.DataFrame(
        {
            "in": [r["selected_model_insample"] for r in rows],
            "ho": [r["selected_model"] for r in rows],
        }
    )
    models = ["HS", "FHS", "GBM", "Merton", "GARCH-t"]
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.0))
    x = np.arange(len(models))
    for ax, (title, a, b) in zip(
        axes,
        (
            (
                "E1: tüm yeniden kalibrasyonlar (41 hisse, 2019–2026)",
                shares["sel_insample"].reindex(models).fillna(0),
                shares["sel_holdout"].reindex(models).fillna(0),
            ),
            (
                f"Evren, 20.11.2026 ({len(rows)} hisse)",
                snap_df["in"].value_counts(normalize=True).reindex(models).fillna(0),
                snap_df["ho"].value_counts(normalize=True).reindex(models).fillna(0),
            ),
        ),
        strict=True,
    ):
        ax.bar(x - 0.2, a.to_numpy(), 0.4, color="#9E9E9E", label="Örneklem içi kritik")
        ax.bar(x + 0.2, b.to_numpy(), 0.4, color=BLUE, label="Hold-out kritik")
        ax.set_xticks(x, models)
        ax.set_title(title, loc="left", fontsize=9)
        fmt_axis(ax, "y", "frac", 0)
    axes[0].set_ylabel("seçilme payı")
    axes[0].legend(fontsize=7)
    fig.suptitle("Kritiğin model seçimi: örneklem içi ve hold-out", fontsize=11, x=0.02, ha="left")
    fig.tight_layout()
    return save_fig(fig, "sekil_04_model_secimi")


# --------------------------------------------------------------------------- T1
def _weekly(px: pd.Series) -> pd.Series:
    w = px.dropna().resample("W-FRI").last().dropna()
    return np.log(w).diff().dropna()


def t01_descriptive() -> list[str]:
    from scipy import stats

    from pusula.features.returns import session_prices
    from pusula.risk.engine import load_inputs

    inp = load_inputs(store(), AS_OF)
    mem = members().drop_duplicates(["symbol", "universe"])
    fx = inp.usdtry
    rows = []
    for sym in mem["symbol"].unique():
        px = session_prices(inp.prices, sym, inp.sessions).dropna()
        if len(px) < 260:
            continue
        for basis in ("TRY", "USD"):
            p = px if basis == "TRY" else (px / fx.reindex(px.index).ffill()).dropna()
            r = _weekly(p)
            w = np.exp(r.cumsum())
            rows.append(
                {
                    "symbol": sym,
                    "basis": basis,
                    "mean": r.mean(),
                    "vol": r.std(ddof=1) * np.sqrt(52),
                    "skew": stats.skew(r),
                    "kurt": stats.kurtosis(r),
                    "mdd": float((w / w.cummax() - 1).min()),
                    "weeks": len(r),
                }
            )
    st = pd.DataFrame(rows)
    groups = {
        "BIST30": mem[mem["universe"] == "BIST30"]["symbol"],
        "Enerji": mem[mem["universe"] == "Energy"]["symbol"],
        "Enerji (TUPRS hariç)": mem[(mem["universe"] == "Energy") & ~mem["overlap"]]["symbol"],
    }
    for sub, g in mem[mem["universe"] == "Energy"].groupby("sub_sector"):
        groups[f"  {SUB_TR[sub]}"] = g["symbol"]
    out = []
    for basis in ("TRY", "USD"):
        for gname, syms in groups.items():
            g = st[(st["basis"] == basis) & st["symbol"].isin(syms)]
            if g.empty:
                continue
            md = g[["mean", "vol", "skew", "kurt", "mdd"]].median()
            out.append(
                {
                    "Baz": basis,
                    "Grup": gname,
                    "N": str(len(g)),
                    "Haftalık ort. getiri": tr_pct(md["mean"], 2),
                    "Yıllık oynaklık": tr_pct(md["vol"], 1),
                    "Çarpıklık": tr_num(md["skew"], 2),
                    "Basıklık (fazla)": tr_num(md["kurt"], 1),
                    "Azami düşüş": tr_pct(md["mdd"], 1),
                }
            )
    return save_tab(
        pd.DataFrame(out),
        "tablo_01_tanimlayici_istatistikler",
        "Tablo 1. Haftalık log getirilerin tanımlayıcı istatistikleri (2018 – 20.11.2026; "
        "grup içi hisse medyanları; basıklık = fazla basıklık)",
    )


# --------------------------------------------------------------------------- T2
def t02_energy_selection() -> list[str]:
    text = (ROOT_DIR / "docs" / "universe_selection.md").read_text(encoding="utf-8")
    table = [ln for ln in text.split("## Score table", 1)[1].splitlines() if ln.startswith("|")]
    head = [c.strip() for c in table[0].strip("|").split("|")]
    body = [[c.strip() for c in ln.strip("|").split("|")] for ln in table[2:]]
    df = pd.DataFrame(body, columns=head)
    yes = {"True": "evet", "False": "hayır"}
    out = pd.DataFrame(
        {
            "Hisse": df["ticker"],
            "Şirket": df["name"],
            "Alt sektör": df["sub_sector"].map(SUB_TR),
            "BIST30'da": df["in_bist30"].map(yes),
            "İlk işlem": pd.to_datetime(df["first_date"]).dt.strftime("%d.%m.%Y"),
            "Medyan işlem hacmi (mn TL)": df["median_value_mn_try"].map(
                lambda v: tr_num(float(v), 1) if v not in ("", "nan") else "–"
            ),
            "Likidite sırası": df["rank_liquidity"].map(
                lambda v: v.replace(".0", "") if v != "nan" else "–"
            ),
            "Seçildi": df["selected"].map(yes),
            "Giriş kuralı": df["entry_rule"].replace(
                {"3y": "3 yıl", "2y_relaxed": "2 yıl (gevşetilmiş)", "": "–"}
            ),
        }
    )
    return save_tab(
        out,
        "tablo_02_enerji_secimi",
        "Tablo 2. Kurala dayalı enerji hissesi seçimi (seçim tarihi 03.11.2025; yalnızca "
        "bu tarihe kadarki veri)",
    )


# --------------------------------------------------------------------------- T3
def t03_llm_models() -> list[str]:
    """Transcribed from the documented tests D-055 (2026-11-22) and D-075 (2026-11-23)."""
    rows = [
        (
            "nvidia/nemotron-3-ultra-550b-a55b",
            "NVIDIA NIM",
            "Tam akış, yalın karar, denetçi",
            "İlk denemede geçerli JSON 12 çağrının 11'inde; sayısal denetim 222/222 ve 185/185; "
            "tutarlılık geçti",
            "25–70 sn (akıl yürütme açık); yalın ~2 sn (kapalı)",
            "Seçildi",
        ),
        (
            "nvidia/nemotron-3.5-lightning-30b-a3b",
            "NVIDIA NIM",
            "Denetçi, yalın karar",
            "Denetçi: 3/3 boş yanıt; yalın: geçerli ama zayıf Türkçe",
            "6,5 sn (yalın)",
            "Elendi",
        ),
        ("z-ai/glm-5.3-flash", "NVIDIA NIM", "Denetçi", "3/3 boş yanıt", "698 sn", "Elendi"),
        (
            "mistralai/mistral-large-4-1t-a52b",
            "NVIDIA NIM",
            "Tam akış, yalın karar",
            "~10 dk içinde tamamlanamadı; yalın 2 kez 300 sn zaman aşımı",
            "> 300 sn",
            "Elendi",
        ),
        (
            "moonshotai/kimi-k3.1-pro",
            "NVIDIA NIM",
            "Yalın karar",
            "Geçerli JSON, iyi Türkçe, girdi dışı sayı yok; karar AL (0,62)",
            "94 sn",
            "E5 karşılaştırma",
        ),
        (
            "google/gemma-4-31b-it",
            "NVIDIA NIM",
            "Yalın karar",
            "Geçerli, iyi Türkçe, girdi dışı sayı yok; karar AL (0,70)",
            "126 sn",
            "E5 karşılaştırma",
        ),
        (
            "gemini-3.5-flash",
            "Google (OpenAI uyumlu)",
            "Yalın karar (THYAO, 13.11.2026)",
            "İlk denemede geçerli JSON, sayısal denetim temiz; karar BEKLE (0,70)",
            "9,1 sn",
            "Yedek (etkin değil)",
        ),
        (
            "gemini-2.5-flash",
            "Google (OpenAI uyumlu)",
            "Yalın karar",
            "Geçerli; karar BEKLE (0,65)",
            "12,0 sn",
            "–",
        ),
        (
            "gemini-pro-latest",
            "Google (OpenAI uyumlu)",
            "Yalın karar",
            "Ücretsiz katman kotası 0 (sağlayıcı hata mesajı)",
            "–",
            "Kullanılamaz",
        ),
    ]
    df = pd.DataFrame(
        rows, columns=["Model", "Sağlayıcı", "Test edilen rol", "Sonuç", "Gecikme", "Karar"]
    )
    return save_tab(
        df,
        "tablo_03_llm_model_karsilastirmasi",
        "Tablo 3. Dil modeli karşılaştırması (ücretsiz katman; D-055, D-075)",
    )


# --------------------------------------------------------------------------- E1: Ş5, Ş6, T4, T5
E1_MODELS = ["HS", "FHS", "GBM", "Merton", "GARCH-t", "critic_insample", "critic_holdout"]


def _e1() -> Path:
    run = latest_run("e1_var")
    if run is None:
        raise RuntimeError("E1 results missing")
    return run


def s05_exceedance() -> list[str]:
    plt = plt_setup()
    sm = pd.read_csv(_e1() / "e1_summary_by_group_regime.csv")
    sm = sm[(sm["regime"] == "all") & sm["group"].isin(["BIST30", "Energy"])]
    fig, axes = plt.subplots(1, 2, figsize=(7.6, 3.3))
    x = np.arange(len(E1_MODELS))
    for ax, lv in zip(axes, (0.95, 0.99), strict=True):
        piv = sm[sm["level"] == lv].pivot(index="model", columns="group", values="exceed_rate")
        piv = piv.reindex(E1_MODELS)
        ax.bar(x - 0.2, piv["BIST30"] * 100, 0.4, color=BLUE, label="BIST30")
        ax.bar(x + 0.2, piv["Energy"] * 100, 0.4, color=ORANGE, label="Enerji")
        ax.axhline(
            (1 - lv) * 100,
            color="black",
            ls="--",
            lw=1,
            label=f"hedef %{tr_num((1 - lv) * 100, 0)}",
        )
        ax.set_xticks(x, [MODEL_TR[m] for m in E1_MODELS], fontsize=7, rotation=30, ha="right")
        ax.set_title(f"VaR %{lv * 100:.0f} (1 gün)", loc="left")
        fmt_axis(ax, "y", "pct", 1 if lv == 0.95 else 2)
    axes[0].set_ylabel("aşım oranı")
    axes[1].legend(fontsize=7, loc="upper left")
    fig.suptitle(
        "E1: VaR aşım oranları, 2019–2026 (41 hisse, 73.842 hisse-gün)",
        fontsize=11,
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    return save_fig(fig, "sekil_05_e1_asim_oranlari")


def s06_pass_heatmap() -> list[str]:
    plt = plt_setup()
    sm = pd.read_csv(_e1() / "e1_summary_by_group_regime.csv")
    sm = sm[(sm["regime"] == "all") & sm["group"].isin(["BIST30", "Energy"])]
    tests = [("share_reject_pof", "POF"), ("share_reject_ind", "BĞM"), ("share_reject_cc", "KK")]
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.4), sharey=True)
    for ax, lv in zip(axes, (0.95, 0.99), strict=True):
        cols, labels = [], []
        for g in ("BIST30", "Energy"):
            for col, tname in tests:
                s = (
                    sm[(sm["level"] == lv) & (sm["group"] == g)]
                    .set_index("model")[col]
                    .reindex(E1_MODELS)
                )
                cols.append(1 - s.to_numpy())
                labels.append(tname)
        M = np.column_stack(cols)
        im = ax.imshow(M, cmap="RdYlGn", vmin=0, vmax=1, aspect="auto")
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                ax.text(j, i, tr_pct(M[i, j], 0), ha="center", va="center", fontsize=6.5)
        ax.axvline(2.5, color="white", lw=2)
        ax.set_xticks(range(len(labels)), labels, fontsize=7)
        for xc, g in ((1, "BIST30"), (4, "Enerji")):
            ax.text(
                xc,
                -0.75,
                g,
                ha="center",
                va="bottom",
                fontsize=8,
                color=BLUE if g == "BIST30" else ORANGE,
            )
        ax.set_yticks(range(len(E1_MODELS)), [MODEL_TR[m] for m in E1_MODELS], fontsize=7.5)
        ax.set_title(f"VaR %{lv * 100:.0f}", loc="left", pad=16)
        ax.grid(False)
    fig.text(
        0.02,
        0.01,
        "POF = Kupiec kapsama testi, BĞM = Christoffersen bağımsızlık testi, "
        "KK = koşullu kapsama testi",
        fontsize=7,
    )
    cb = fig.colorbar(im, ax=axes, shrink=0.8)
    fmt_axis(cb.ax, "y", "frac", 0)
    cb.set_label("testi geçen hisse payı (%5 düzey)")
    fig.suptitle(
        "E1: Kupiec ve Christoffersen testlerini geçen hisse payı",
        fontsize=11,
        x=0.02,
        ha="left",
        y=1.06,
    )
    return save_fig(fig, "sekil_06_e1_test_gecme_isi_haritasi")


def t04_e1_table() -> list[str]:
    k = pd.read_csv(_e1() / "e1_key_table.csv")
    k = k[k["group"] == "Tümü"]
    out = pd.DataFrame(
        {
            "Model": k["model"].map(MODEL_TR),
            "Düzey": k["level"].map(lambda v: f"%{v * 100:.0f}"),
            "Aşım oranı": k["exceed_rate"].map(lambda v: tr_pct(v, 2)),
            "Kupiec p (havuz)": k["pooled_kupiec_p"].map(
                lambda v: "<0,001" if v < 0.001 else tr_num(v, 3)
            ),
            "POF red payı": k["share_reject_pof"].map(lambda v: tr_pct(v, 0)),
            "Bağımsızlık red payı": k["share_reject_ind"].map(lambda v: tr_pct(v, 0)),
            "Koşullu kapsama red payı": k["share_reject_cc"].map(lambda v: tr_pct(v, 0)),
            "Kuantil kaybı (×10⁴)": k["tick_loss_x1e4"].map(lambda v: tr_num(v, 2)),
        }
    )
    return save_tab(
        out,
        "tablo_04_e1_var_backtest",
        "Tablo 4. E1: 1 günlük VaR backtest'i, tüm hisseler (2019 – 20.11.2026; red payı: %5 düzeyde testi reddeden hisse oranı)",
    )


def t05_e1_critic() -> list[str]:
    c = pd.read_csv(_e1() / "e1_critic_comparison.csv")
    other = {
        "critic_holdout vs critic_insample": "örneklem içi kritik",
        "critic_holdout vs HS": "HS",
    }
    out = pd.DataFrame(
        {
            "Düzey": c["level"].map(lambda v: f"%{v * 100:.0f}"),
            "Karşılaştırma": "Hold-out kritik – " + c["comparison"].map(other),
            "Hold-out kuantil kaybı daha düşük": c.apply(
                lambda r: f"{r['holdout_lower_tick_loss']} / {r['n_stocks']}", axis=1
            ),
            "İşaret testi p": c["sign_test_p"].map(
                lambda v: "<0,001" if v < 0.001 else tr_num(v, 2)
            ),
            "Ort. kuantil kaybı (hold-out, ×10⁴)": c["mean_tick_loss_holdout_x1e4"].map(
                lambda v: tr_num(v, 2)
            ),
            "Ort. kuantil kaybı (diğer, ×10⁴)": c["mean_tick_loss_other_x1e4"].map(
                lambda v: tr_num(v, 2)
            ),
            "Hold-out kapsama hedefe daha yakın": c.apply(
                lambda r: f"{r['holdout_closer_coverage']} / {r['n_stocks']}", axis=1
            ),
        }
    )
    return save_tab(
        out,
        "tablo_05_e1_kritik_karsilastirma",
        "Tablo 5. E1: hold-out kritik, örneklem içi kritik ve HS karşısında (hisse bazında, örneklem dışı)",
    )


# --------------------------------------------------------------------------- E2: Ş7, Ş8, T6, T7
FACTOR_TR = {
    "rate": "2Y faiz",
    "usdtry": "USD/TRY",
    "brent": "Brent",
    "ttf": "TTF",
    "cds": "CDS",
    "vix": "VIX",
    "us10y": "ABD 10Y",
}


def _e2() -> Path:
    run = latest_run("e2_factor")
    if run is None:
        raise RuntimeError("E2 results missing")
    return run


def s07_beta_heatmap() -> list[str]:
    from matplotlib.colors import TwoSlopeNorm

    plt = plt_setup()
    sens = pd.read_csv(_e2() / "e2_sensitivities.csv")
    mem = members().drop_duplicates(["symbol", "universe"])
    blocks = [("BIST30", sorted(mem[mem["universe"] == "BIST30"]["symbol"]), None)]
    for sub in ("refining_petroleum", "natural_gas", "electricity"):
        blocks.append(
            (
                SUB_TR[sub],
                sorted(mem[(mem["universe"] == "Energy") & (mem["sub_sector"] == sub)]["symbol"]),
                sub,
            )
        )
    sens1 = sens.drop_duplicates(["symbol", "factor"])
    piv = sens1.pivot(index="symbol", columns="factor", values="resp_1sd_pct")
    pv = sens1.pivot(index="symbol", columns="factor", values="p")
    facs = [f for f in FACTOR_TR if f in piv.columns]
    rows, labels, colors, seps = [], [], [], []
    for _name, syms, sub in blocks:
        for s_ in syms:
            if s_ in piv.index:
                rows.append(s_)
                labels.append(s_.removesuffix(".IS"))
                colors.append(BLUE if sub is None else SUB_COLORS[sub])
        seps.append(len(rows))
    M, P = (
        piv.reindex(index=rows, columns=facs).to_numpy(),
        pv.reindex(index=rows, columns=facs).to_numpy(),
    )
    lim = np.nanmax(np.abs(M))
    fig, ax = plt.subplots(figsize=(6.4, 0.2 * len(rows) + 1.6))
    im = ax.imshow(M, aspect="auto", cmap="RdBu", norm=TwoSlopeNorm(0, -lim, lim))
    for i in range(M.shape[0]):
        for j in range(M.shape[1]):
            if np.isfinite(M[i, j]):
                ax.text(
                    j,
                    i,
                    tr_num(M[i, j], 1) + ("*" if P[i, j] < 0.05 else ""),
                    ha="center",
                    va="center",
                    fontsize=5.8,
                )
    for s_ in seps[:-1]:
        ax.axhline(s_ - 0.5, color="black", lw=1)
    ax.set_xticks(range(len(facs)), [FACTOR_TR[f] for f in facs], fontsize=8)
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(rows)), labels, fontsize=6.5)
    for t, c in zip(ax.get_yticklabels(), colors, strict=True):
        t.set_color(c)
    ax.grid(False)
    y = 0
    for name, syms, _ in blocks:
        n = sum(1 for s_ in syms if s_ in piv.index)
        short = {"Rafineri/akaryakıt": "Rafineri"}.get(name, name)
        ax.text(
            len(facs) - 0.35,
            y + n / 2 - 0.5,
            short,
            va="center",
            fontsize=6.5,
            rotation=270 if n > 3 else 0,
        )
        y += n
    cb = fig.colorbar(im, ax=ax, shrink=0.5, pad=0.08)
    cb.set_label("haftalık getiri tepkisi (%)")
    fmt_axis(cb.ax, "y", "pct", 1)
    ax.set_title(
        "1 standart sapmalık haftalık faktör hareketine yüzde tepki (Model A)\n* p < 0,05 (Newey–West); PTF kullanılmadı",
        fontsize=9,
        pad=24,
    )
    return save_fig(fig, "sekil_07_e2_beta_isi_haritasi")


def s08_r2() -> list[str]:
    plt = plt_setup()
    st = pd.read_csv(_e2() / "e2_per_stock.csv")
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.4), sharey=True)
    for ax, (m, title) in zip(
        axes, (("A", "Model A (yalnız makro)"), ("B", "Model B (+ piyasa artığı)")), strict=True
    ):
        for u, g in st.groupby("universe"):
            if u == "BIST30":
                ax.scatter(
                    g[f"r2_{m}"], g[f"oos_r2_{m}"], s=14, color=BLUE, label="BIST30", alpha=0.8
                )
            else:
                for sub, gg in g.groupby("sub_sector"):
                    ax.scatter(
                        gg[f"r2_{m}"],
                        gg[f"oos_r2_{m}"],
                        s=14,
                        color=SUB_COLORS[sub],
                        label=f"Enerji: {SUB_TR[sub]}",
                        alpha=0.9,
                        marker="s",
                    )
        lo = min(-0.3, st[[f"oos_r2_{m}"]].min().min() - 0.02)
        ax.plot([0, 0.8], [0, 0.8], color="grey", lw=0.8, ls="--")
        ax.axhline(0, color="black", lw=0.8)
        ax.set_xlim(0, 0.8)
        ax.set_ylim(lo, 0.8)
        ax.set_title(title, loc="left")
        ax.set_xlabel("örneklem içi R²")
        fmt_axis(ax, "x", "num", 1)
        fmt_axis(ax, "y", "num", 1)
    axes[0].set_ylabel("örneklem dışı R² (2 yıl kurulum, 26 hafta test)")
    axes[1].legend(fontsize=6.5, loc="upper left")
    fig.suptitle(
        "E2: faktör modelinin örneklem içi ve dışı açıklama gücü (hisse başına)",
        fontsize=11,
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    return save_fig(fig, "sekil_08_e2_r2_ic_dis")


def t06_e2_table() -> list[str]:
    c = pd.read_csv(_e2() / "e2_universe_comparison.csv")
    names = {
        "r2_A": "Örneklem içi R², Model A",
        "r2_B": "Örneklem içi R², Model B",
        "oos_r2_A": "Örneklem dışı R², Model A",
        "oos_r2_B": "Örneklem dışı R², Model B",
        "max_vif": "En büyük VIF",
    }
    rows = []
    for metric, label in names.items():
        a = c[(c["sample"] == "all") & (c["metric"] == metric)].iloc[0]
        b = c[(c["sample"] == "no_overlap") & (c["metric"] == metric)].iloc[0]
        rows.append(
            {
                "Ölçüt": label,
                "BIST30 medyan": tr_num(a["BIST30_median"], 3),
                "Enerji medyan": tr_num(a["Energy_median"], 3),
                "Mann–Whitney p": tr_num(a["mw_p"], 3),
                "Enerji medyan (TUPRS hariç)": tr_num(b["Energy_median"], 3),
            }
        )
    for f, label in FACTOR_TR.items():
        sel = c[(c["sample"] == "all") & (c["metric"] == f"resp_1sd_pct:{f}")]
        if sel.empty:
            continue
        a = sel.iloc[0]
        b = c[(c["sample"] == "no_overlap") & (c["metric"] == f"resp_1sd_pct:{f}")].iloc[0]
        rows.append(
            {
                "Ölçüt": f"Tepki (1 sd), {label}",
                "BIST30 medyan": tr_pct(a["BIST30_median"] / 100, 2),
                "Enerji medyan": tr_pct(a["Energy_median"] / 100, 2),
                "Mann–Whitney p": tr_num(a["mw_p"], 3),
                "Enerji medyan (TUPRS hariç)": tr_pct(b["Energy_median"] / 100, 2),
            }
        )
    return save_tab(
        pd.DataFrame(rows),
        "tablo_06_e2_faktor_modeli",
        "Tablo 6. E2: faktör modeli, BIST30 ve Enerji (örtüşen TUPRS dahil ve hariç)",
    )


def t07_e2_subsector() -> list[str]:
    b = pd.read_csv(_e2() / "e2_by_subsector.csv")
    grp = {
        "BIST30": "BIST30",
        "Energy:electricity": "Enerji: elektrik",
        "Energy:natural_gas": "Enerji: doğalgaz",
        "Energy:refining_petroleum": "Enerji: rafineri/akaryakıt",
    }
    out = pd.DataFrame(
        {
            "Grup": b["group"].map(grp),
            "N": b["n"].astype(int).astype(str),
            "R² A": b["r2_A"].map(lambda v: tr_num(v, 3)),
            "R² B": b["r2_B"].map(lambda v: tr_num(v, 3)),
            "ÖD R² A": b["oos_r2_A"].map(lambda v: tr_num(v, 3)),
            "ÖD R² B": b["oos_r2_B"].map(lambda v: tr_num(v, 3)),
            "En büyük VIF": b["max_vif"].map(lambda v: tr_num(v, 2)),
        }
    )
    return save_tab(
        out,
        "tablo_07_e2_alt_sektorler",
        "Tablo 7. E2: alt sektörlere göre medyan açıklama gücü (ÖD = örneklem dışı)",
    )


# --------------------------------------------------------------------------- scenarios: Ş9, Ş10
_SCEN: dict = {}


def scenario_results(horizon: str = "3m", mode: str = "propagated") -> pd.DataFrame:
    """All 10 presets on the frozen data (as of 2026-11-20), TRY and USD; one row per stock,
    scenario and basis (cached in memory for the case studies)."""
    key = (horizon, mode)
    if key in _SCEN:
        return _SCEN[key]
    from pusula.macro.context import build_context, current_passthrough, make_engine
    from pusula.macro.scenarios import load_presets, to_factor_shocks

    ctx = build_context(store(), AS_OF)
    eng = make_engine(ctx)
    pt = current_passthrough(ctx)
    rows = []
    for sc in load_presets():
        spec = to_factor_shocks(sc.shocks, eng.factors, pt)
        for basis in ("TRY", "USD"):
            r = eng.run(spec, horizon, mode, basis)
            st = r["stocks"].assign(
                scenario=sc.name_tr,
                scenario_id=sc.id,
                basis=basis,
                guard=bool(r["extrapolation_guard"]),
            )
            rows.append(st)
    df = pd.concat(rows, ignore_index=True)
    _SCEN[key] = df
    _SCEN["ctx"] = ctx
    return df


def s09_scenarios() -> list[str]:
    plt = plt_setup()
    df = scenario_results()
    order = list(dict.fromkeys(df["scenario"]))
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 5.2), sharey=True)
    y = np.arange(len(order))
    for ax, basis in zip(axes, ("TRY", "USD"), strict=True):
        d = df[df["basis"] == basis]
        for k, (u, col) in enumerate((("BIST30", BLUE), ("Energy", ORANGE))):
            g = d[d["universe"] == u].groupby("scenario")["d_exp_ret"].mean().reindex(order) * 100
            ax.barh(y + (0.2 if k == 0 else -0.2), g.to_numpy(), 0.38, color=col, label=UNI_TR[u])
        e = d[d["universe"] == "Energy"]
        for sub, col in SUB_COLORS.items():
            g = (
                e[e["sub_sector"] == sub].groupby("scenario")["d_exp_ret"].mean().reindex(order)
                * 100
            )
            ax.scatter(
                g.to_numpy(),
                y - 0.2,
                s=14,
                color=col,
                edgecolor="black",
                lw=0.4,
                zorder=3,
                label=f"Enerji: {SUB_TR[sub]}",
            )
        guard = d.groupby("scenario")["guard"].first().reindex(order)
        ax.axvline(0, color="black", lw=0.8)
        ax.set_title(f"{'TL bazında' if basis == 'TRY' else 'USD bazında'}", loc="left")
        fmt_axis(ax, "x", "pct", 0)
    labels = [o + (" †" if guard.iloc[i] else "") for i, o in enumerate(order)]
    axes[0].set_yticks(y, labels, fontsize=7.5)
    axes[0].invert_yaxis()
    fig.supxlabel("beklenen getiri değişimi, 3 ay (şoksuz baz senaryoya göre)", fontsize=9, y=0.06)
    h, lab = axes[1].get_legend_handles_labels()
    fig.legend(h, lab, loc="lower center", ncol=5, fontsize=7, bbox_to_anchor=(0.5, 0.015))
    fig.suptitle(
        "Hazır senaryolar: BIST30 ve Enerji (3 ay, yayılımlı mod, 20.11.2026 verisi)",
        fontsize=11,
        x=0.02,
        ha="left",
    )
    fig.text(
        0.02,
        -0.02,
        "Çubuk: evren ortalaması; nokta: enerji alt sektör ortalaması. † Şok güncel rejimin deneyiminin çok dışında; tüm örneklem ilişkileri kullanıldı (D-053).",
        fontsize=6.5,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    return save_fig(fig, "sekil_09_senaryolar_bist30_enerji")


def s10_passthrough() -> list[str]:
    from pusula.macro.context import build_context

    plt = plt_setup()
    ctx = _SCEN.get("ctx") or build_context(store(), AS_OF)
    pt = ctx.passthrough
    ev = ctx.pt_events.copy()
    regs = [r.id for r in get_regimes().regimes if r.id in pt] + (
        ["pooled"] if "pooled" in pt else []
    )
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.5), gridspec_kw={"width_ratios": [1.2, 1]})
    ax = axes[0]
    for i, rid in enumerate(regs):
        p = pt[rid]
        col = "#555555" if rid == "pooled" else (BLUE if not p.fallback_pooled else "#BBBBBB")
        ax.errorbar(
            i,
            p.beta,
            yerr=[[p.beta - min(p.lo, p.hi)], [max(p.lo, p.hi) - p.beta]],
            fmt="o",
            color=col,
            capsize=3,
            lw=1.2,
        )
        ax.text(i, max(p.lo, p.hi) + 0.03, f"n={p.n_changes}", ha="center", fontsize=6.5)
    ax.axhline(0, color="black", lw=0.8)
    ax.axhline(1, color="grey", lw=0.6, ls=":")
    ax.set_xticks(
        range(len(regs)),
        [REGIME_SHORT.get(r, "Tüm örneklem") for r in regs],
        rotation=30,
        ha="right",
        fontsize=7,
    )
    ax.set_ylabel("aktarım katsayısı (2Y faiz / politika faizi)")
    ax.set_title(
        "Rejime göre aktarım, %90 bant (gri: az olay, havuz kullanıldı)", loc="left", fontsize=8.5
    )
    fmt_axis(ax, "y", "num", 2)
    ax = axes[1]
    if not ev.empty:
        ev["regime"] = [get_regimes().regime_of(d.date()) for d in ev["meeting_date"]]
        palette = plt.get_cmap("tab10")
        for k, (rid, g) in enumerate(ev[ev["d_policy"] != 0].groupby("regime")):
            ax.scatter(
                g["d_policy"],
                g["d_market"],
                s=16,
                color=palette(k),
                label=REGIME_SHORT.get(rid, rid),
            )
        lim = float(np.nanmax(np.abs(ev[["d_policy"]].to_numpy()))) + 0.5
        xs = np.linspace(-lim, lim, 10)
        if "pooled" in pt:
            ax.plot(xs, pt["pooled"].beta * xs, color="#555555", lw=1, ls="--", label="havuz eğimi")
        ax.axhline(0, color="black", lw=0.6)
        ax.axvline(0, color="black", lw=0.6)
        ax.set_xlabel("politika faizi değişimi (puan)")
        ax.set_ylabel("2Y faiz değişimi, [−1, +5] (puan)")
        fmt_axis(ax, "x", "num", 1)
        fmt_axis(ax, "y", "num", 1)
        ax.legend(fontsize=6, loc="upper left")
        ax.set_title("PPK kararları (faiz değişikliği olanlar)", loc="left", fontsize=8.5)
    fig.suptitle(
        "Politika faizinden 2 yıllık tahvil faizine aktarım", fontsize=11, x=0.02, ha="left"
    )
    fig.tight_layout()
    return save_fig(fig, "sekil_10_aktarim_rejimler")


# --------------------------------------------------------------------------- E3: Ş11, Ş12, T8
def _e3() -> Path:
    run = latest_run("e3_event")
    if run is None:
        raise RuntimeError("E3 results missing")
    return run


def s11_e3_scatter() -> list[str]:
    plt = plt_setup()
    df = pd.read_csv(_e3() / "e3_stock_events.csv")
    df = df[(df["direction"] != "hold") & df["pred_total"].notna()]
    sc = pd.read_csv(_e3() / "e3_scores.csv").set_index(["group", "comparison"])
    fig, axes = plt.subplots(1, 2, figsize=(7.8, 3.5))
    for ax, (p, r, title, comp) in zip(
        axes,
        (
            ("pred_total", "mean_adj", "Toplam tepki", "total"),
            ("pred_abn", "car", "Anormal tepki (CAR)", "abnormal"),
        ),
        strict=True,
    ):
        g = df[df["universe"] == "BIST30"]
        ax.scatter(g[p] * 100, g[r] * 100, s=7, alpha=0.45, color=BLUE, label="BIST30", lw=0)
        e = df[df["universe"] == "Energy"]
        for sub, col in SUB_COLORS.items():
            gg = e[e["sub_sector"] == sub]
            ax.scatter(
                gg[p] * 100,
                gg[r] * 100,
                s=9,
                alpha=0.7,
                color=col,
                marker="s",
                lw=0,
                label=f"Enerji: {SUB_TR[sub]}",
            )
        ax.axhline(0, color="black", lw=0.7)
        ax.axvline(0, color="black", lw=0.7)
        acc = sc.loc[("Tümü", comp)]
        ax.text(
            0.02,
            0.97,
            f"yön isabeti {tr_num(acc['direction_accuracy'], 2)} "
            f"[{tr_num(acc['acc_ci_lo'], 2)}; {tr_num(acc['acc_ci_hi'], 2)}]\nOMH {tr_num(acc['mae_pct'], 1)} puan",
            transform=ax.transAxes,
            va="top",
            fontsize=7,
        )
        lim = np.nanpercentile(np.abs(df[r]) * 100, 99)
        ax.set_ylim(-lim, lim)
        ax.set_title(title, loc="left")
        ax.set_xlabel("model tahmini, % (karar öncesi veriyle)")
        from matplotlib.ticker import MaxNLocator

        ax.xaxis.set_major_locator(MaxNLocator(5))
        fmt_axis(ax, "x", "pct", 1)
        fmt_axis(ax, "y", "pct", 0)
    axes[0].set_ylabel("gerçekleşen [−1, +5], %")
    axes[1].legend(fontsize=6.5, loc="lower right")
    fig.suptitle(
        "E3: PPK faiz değişiklikleri, senaryo motoru tahmini ve gerçekleşen tepki (37 karar, 2020–2026)",
        fontsize=10,
        x=0.02,
        ha="left",
    )
    fig.text(
        0.02,
        -0.02,
        "Not: eksen ölçekleri farklıdır; tahminler gerçekleşen tepkilerden yaklaşık iki büyüklük mertebesi küçüktür.",
        fontsize=6.5,
    )
    fig.tight_layout()
    return save_fig(fig, "sekil_11_e3_tahmin_gerceklesen")


def s12_e3_car() -> list[str]:
    plt = plt_setup()
    ev = pd.read_csv(_e3() / "e3_events.csv")
    ev = ev[ev["direction"] != "hold"].sort_values("event").reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(8.4, 3.4))
    x = np.arange(len(ev))
    for i, r in ev.iterrows():
        if r["direction"] == "hike":
            ax.axvspan(i - 0.5, i + 0.5, color="#F2D7D5", lw=0)
    ax.bar(x - 0.2, ev["car_BIST30"] * 100, 0.4, color=BLUE, label="BIST30 ort. CAR")
    ax.bar(x + 0.2, ev["car_Energy"] * 100, 0.4, color=ORANGE, label="Enerji ort. CAR")
    ax.axhline(0, color="black", lw=0.8)
    labels = [
        f"{pd.Timestamp(d):%m.%y} {'+' if b > 0 else '−'}{abs(b):.0f}"
        for d, b in zip(ev["event"], ev["change_bp"], strict=True)
    ]
    ax.set_xticks(x, labels, fontsize=6, rotation=90)
    ax.set_xlim(-0.6, len(ev) - 0.4)
    ax.set_ylabel("ortalama CAR [−1, +5]")
    fmt_axis(ax, "y", "pct", 0)
    ax.legend(fontsize=7, loc="lower left")
    ax.set_title(
        "Faiz değişikliği olan PPK kararları (etiket: ay.yıl ve değişim, baz puan; pembe = artırım)",
        loc="left",
        fontsize=8.5,
    )
    fig.suptitle(
        "E3: kararlar etrafında evren ortalaması anormal getiri", fontsize=11, x=0.02, ha="left"
    )
    fig.tight_layout()
    return save_fig(fig, "sekil_12_e3_car_evrenler")


def t08_e3_table() -> list[str]:
    sc = pd.read_csv(_e3() / "e3_scores.csv")
    grp = {
        "Tümü": "Tümü",
        "BIST30": "BIST30",
        "Energy": "Enerji",
        "Energy:electricity": "Enerji: elektrik",
        "Energy:natural_gas": "Enerji: doğalgaz",
        "Energy:refining_petroleum": "Enerji: rafineri",
        "Tümü:cut": "İndirimler",
        "Tümü:hike": "Artırımlar",
    }
    out = pd.DataFrame(
        {
            "Grup": sc["group"].map(grp),
            "Karşılaştırma": sc["comparison"].map({"total": "toplam", "abnormal": "anormal (CAR)"}),
            "Olay": sc["n_events"].astype(str),
            "Gözlem": sc["n_obs"].astype(str),
            "Yön isabeti [%95 GA]": sc.apply(
                lambda r: (
                    f"{tr_num(r['direction_accuracy'], 2)} [{tr_num(r['acc_ci_lo'], 2)}; {tr_num(r['acc_ci_hi'], 2)}]"
                ),
                axis=1,
            ),
            "OMH (puan) [%95 GA]": sc.apply(
                lambda r: (
                    f"{tr_num(r['mae_pct'], 2)} [{tr_num(r['mae_ci_lo'], 2)}; {tr_num(r['mae_ci_hi'], 2)}]"
                ),
                axis=1,
            ),
            "Ort. tahmin": sc["mean_pred_pct"].map(lambda v: tr_pct(v / 100, 2)),
            "Ort. gerçekleşen": sc["mean_real_pct"].map(lambda v: tr_pct(v / 100, 2)),
        }
    )
    return save_tab(
        out,
        "tablo_08_e3_olay_calismasi",
        "Tablo 8. E3: senaryo motoru tahmini ile gerçekleşen [−1, +5] tepkinin karşılaştırılması (faiz değişiklikleri, 2020–2026; olay bazlı bootstrap)",
    )


# --------------------------------------------------------------------------- E4: Ş13, Ş14, T9, T10
E4_STYLE = {
    "Al-ve-tut (EW)": ("#444444", "-"),
    "XU030": ("#999999", "--"),
    "Kural tabanlı risk filtresi": ("#33A02C", "-"),
    "LLM P": ("#A6CEE3", "-"),
    "LLM P+R": ("#1F78B4", "-"),
    "LLM P+R+S": ("#E31A1C", "-"),
    "LLM P+R+S-anon": ("#FB9A99", "--"),
}
STRAT_TR = {
    "Al-ve-tut (EW)": "Al ve tut (eşit ağırlık)",
    "XU030": "XU030",
    "Kural tabanlı risk filtresi": "Kural tabanlı risk filtresi",
    "LLM P": "LLM P",
    "LLM P+R": "LLM P+R",
    "LLM P+R+S": "LLM P+R+S",
    "LLM P+R+S-anon": "LLM P+R+S anonim",
}


def _e4_series() -> dict:
    """Weekly portfolio returns of every strategy that can be evaluated now (only LLM variants
    with ≥98 % coverage), from the frozen data; no bootstrap."""
    import tempfile

    from pusula.evaluation import trading_backtest as tb
    from pusula.evaluation.llm_runner import DECISIONS
    from pusula.risk.engine import load_inputs

    s = get_settings()
    st = tb._store(read_only=True)
    inp = load_inputs(st, AS_OF)
    dates = tb.decision_dates(inp.sessions, s.project.selection_date)
    stocks = tb.select_stocks(st, s.project.selection_date)
    dec = (
        pd.read_csv(DECISIONS).drop_duplicates(["date", "symbol", "variant"], keep="last")
        if DECISIONS.exists()
        else pd.DataFrame(columns=["date", "symbol", "variant", "karar"])
    )
    with tempfile.TemporaryDirectory() as tmp:
        res = tb.evaluate(dec, stocks, dates, Path(tmp), s.project.random_seed, with_ci=False)
        cov = pd.read_csv(Path(tmp) / "e4_coverage.csv")
    res["coverage"] = cov
    res["dec"] = dec
    return res


def s13_e4_equity() -> list[str]:
    plt = plt_setup()
    res = _e4_series()
    port, rf = res["port"], res["rf"]
    fig, (a1, a2) = plt.subplots(
        2, 1, figsize=(7.8, 5.2), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]}
    )

    def curve(r):
        idx = list(r.index)
        x = [idx[0], *idx[1:], idx[-1] + pd.Timedelta(days=7)]
        return x, np.concatenate([[1.0], (1 + r.fillna(0)).cumprod().to_numpy()])

    for name, (col, ls) in E4_STYLE.items():
        if name not in port:
            continue
        x, y = curve(port[name])
        a1.plot(x, y, color=col, ls=ls, lw=1.4, label=STRAT_TR[name])
        a2.plot(x, y / np.maximum.accumulate(y) - 1, color=col, ls=ls, lw=1.1)
    x, y = curve(rf)
    a1.plot(x, y, color="black", ls=":", lw=1, label="Nakit (TLREF)")
    for ax in (a1, a2):
        ax.axvline(pd.Timestamp(get_settings().llm.post_cutoff_start), color="grey", lw=0.8)
    a1.text(
        pd.Timestamp(get_settings().llm.post_cutoff_start),
        0.03,
        " model eğitim kesimi sonrası →",
        fontsize=7,
        va="bottom",
        transform=a1.get_xaxis_transform(),
    )
    a1.set_ylabel("portföy değeri (başlangıç = 1, TL)")
    fmt_axis(a1, "y", "num", 2)
    a2.set_ylabel("düşüş (zirveden)")
    fmt_axis(a2, "y", "frac", 0)
    h, lab = a1.get_legend_handles_labels()
    fig.legend(h, lab, fontsize=7, ncol=4, loc="lower center", bbox_to_anchor=(0.5, 0.0))
    n_llm = int(res["coverage"]["evaluated"].sum())
    note = "" if n_llm else " — LLM varyantları henüz tamamlanmadı"
    fig.suptitle(
        f"E4: haftalık karar destek backtest'i, 10 hisse, maliyetler dahil{note}",
        fontsize=10,
        x=0.02,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    return save_fig(fig, "sekil_13_e4_birikimli_getiri_dusus")


def s14_e4_decisions() -> list[str]:
    res = _e4_series()
    cov = res["coverage"]
    done = list(cov.loc[cov["evaluated"], "variant"])
    if not done:
        print("  s14 skipped: no LLM variant has ≥98 % coverage yet")
        return []
    plt = plt_setup()
    dec = res["dec"].dropna(subset=["karar"])
    dec = dec[dec["variant"].isin(done)]
    dist = dec.groupby(["variant", "karar"]).size().unstack(fill_value=0)
    dist = dist.div(dist.sum(axis=1), axis=0).reindex(columns=["AL", "ALMA", "BEKLE"], fill_value=0)
    fig, ax = plt.subplots(figsize=(6.8, 0.5 * len(dist) + 1.4))
    left = np.zeros(len(dist))
    for c, col in zip(["AL", "ALMA", "BEKLE"], ["#33A02C", "#E31A1C", "#999999"], strict=True):
        ax.barh(
            [STRAT_TR.get(f"LLM {v}", v) for v in dist.index],
            dist[c],
            left=left,
            color=col,
            label=c,
        )
        for i, v in enumerate(dist[c]):
            if v > 0.06:
                ax.text(
                    left[i] + v / 2,
                    i,
                    tr_pct(v, 0),
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="white",
                )
        left += dist[c].to_numpy()
    ax.axvline(0.7, color="black", ls=":", lw=0.8)
    fmt_axis(ax, "x", "frac", 0)
    ax.legend(ncol=3, fontsize=7, loc="lower right")
    ax.set_title("E4: LLM karar dağılımı (noktalı çizgi: BEKLE %70 eşiği)", loc="left")
    fig.tight_layout()
    return save_fig(fig, "sekil_14_e4_karar_dagilimi")


def _perf_table(perf: pd.DataFrame) -> pd.DataFrame:
    win = {"tam": "Tam dönem", "kesim sonrası": "Kesim sonrası"}
    return pd.DataFrame(
        {
            "Dönem": perf["window"].map(win),
            "Strateji": perf["strategy"].map(lambda v: STRAT_TR.get(v, v)),
            "Baz": perf["basis"],
            "Hafta": perf["weeks"].astype(int).astype(str),
            "Kümülatif getiri": perf["cum_return"].map(lambda v: tr_pct(v, 1)),
            "Yıllık oynaklık": perf["vol_ann"].map(lambda v: tr_pct(v, 1)),
            "Sharpe (TLREF)": perf["sharpe"].map(lambda v: tr_num(v, 2)),
            "Sortino": perf["sortino"].map(lambda v: tr_num(v, 2)),
            "Azami düşüş": perf["max_drawdown"].map(lambda v: tr_pct(v, 1)),
            "Calmar": perf["calmar"].map(lambda v: tr_num(v, 2)),
            "İsabet oranı": perf["hit_rate"].map(lambda v: tr_pct(v, 0)),
            "Haftalık devir": perf["turnover_weekly"].map(
                lambda v: tr_num(v, 3) if pd.notna(v) else "–"
            ),
        }
    )


def t09_e4_table() -> list[str]:
    res = _e4_series()
    perf = res["perf"]
    perf = perf[~perf["strategy"].str.contains("BEKLE=%50")]
    files = save_tab(
        _perf_table(perf),
        "tablo_09_e4_performans",
        "Tablo 9. E4: 10 hisselik portföy performansı (03.11.2025 – 20.11.2026; kesim sonrası = 01.06.2026'dan itibaren; "
        "maliyetler dahil; Sharpe ve Sortino'da risksiz faiz TLREF)",
    )
    cov = res["coverage"]
    cov_tab = pd.DataFrame(
        {
            "Varyant": cov["variant"].map(lambda v: STRAT_TR.get(f"LLM {v}", v)),
            "Karar sayısı": cov.apply(lambda r: f"{r['decisions']} / {r['expected']}", axis=1),
            "Kapsam": cov["coverage"].map(lambda v: tr_pct(v, 0)),
            "Değerlendirildi": cov["evaluated"].map({True: "evet", False: "hayır (kapsam < %98)"}),
        }
    )
    files += save_tab(
        cov_tab, "tablo_09b_e4_llm_kapsam", "Tablo 9b. E4: LLM varyantlarının karar kapsamı"
    )
    return files


def t10_e4_long() -> list[str]:
    run = latest_run("e4_backtest")
    if run is None or not (run / "e4_long_sample_2019_2026.csv").exists():
        raise RuntimeError("E4 long-sample results missing")
    ls = pd.read_csv(run / "e4_long_sample_2019_2026.csv").assign(window="tam")
    t = _perf_table(ls).drop(columns=["Dönem"])
    ci = pd.read_csv(run / "e4_long_sample_sharpe_ci.csv").iloc[0]
    cap = (
        "Tablo 10. E4 referans: LLM'siz stratejiler, 2019 – 20.11.2026 (411 hafta). Sharpe farkı (kural filtresi − al ve tut): "
        f"{tr_num(ci['sharpe_diff'], 2)} [%95 GA {tr_num(ci['ci_lo'], 2)}; {tr_num(ci['ci_hi'], 2)}], p = {tr_num(ci['p_two_sided'], 2)}"
    )
    return save_tab(t, "tablo_10_e4_uzun_orneklem", cap)


# --------------------------------------------------------------------------- E5: Ş15
def s15_e5_agreement() -> list[str]:
    run = latest_run("e5_llm")
    if run is None or not (run / "e5_items_decisions.csv").exists():
        print("  s15 skipped: E5 results do not exist yet")
        return []
    plt = plt_setup()
    from pusula.evaluation.llm_reliability import cohen_kappa

    d = pd.read_csv(run / "e5_items_decisions.csv")
    raters = [
        c
        for c in [
            "rep0",
            "rep1",
            "rep2",
            "rep3",
            "rep4",
            "reasoning_on",
            "Kimi K3.1 Pro",
            "Gemma 4 31B",
        ]
        if c in d
    ]
    names = {
        "rep0": "Nemotron t1",
        "rep1": "t2",
        "rep2": "t3",
        "rep3": "t4",
        "rep4": "t5",
        "reasoning_on": "Nemotron (akıl y. açık)",
        "Kimi K3.1 Pro": "Kimi K3.1 Pro",
        "Gemma 4 31B": "Gemma 4 31B",
    }
    M = np.full((len(raters), len(raters)), np.nan)
    for i, a in enumerate(raters):
        for j, b in enumerate(raters):
            x = d[[a, b]].dropna()
            M[i, j] = (x[a] == x[b]).mean() if len(x) else np.nan
    fig, ax = plt.subplots(figsize=(5.6, 4.8))
    im = ax.imshow(M, cmap="Greens", vmin=0, vmax=1)
    for i in range(len(raters)):
        for j in range(len(raters)):
            ax.text(j, i, tr_pct(M[i, j], 0), ha="center", va="center", fontsize=7)
    ax.set_xticks(
        range(len(raters)), [names[r] for r in raters], rotation=40, ha="right", fontsize=7
    )
    ax.set_yticks(range(len(raters)), [names[r] for r in raters], fontsize=7)
    ax.grid(False)
    fig.colorbar(im, ax=ax, shrink=0.7, label="aynı karar oranı")
    k = cohen_kappa(d["rep0"], d["reasoning_on"]) if "reasoning_on" in d else np.nan
    ax.set_title(
        f"E5: karar uyumu ({len(d)} hisse-hafta); Cohen κ (akıl yürütme açık/kapalı) = {tr_num(k, 2)}",
        fontsize=8.5,
        loc="left",
    )
    fig.tight_layout()
    return save_fig(fig, "sekil_15_e5_uyum_matrisi")


# --------------------------------------------------------------------------- case studies
def _scenario_dists(shocks: dict, symbols: list[str], horizon: str = "3m", basis: str = "TRY"):
    """Simulated 3-month simple returns (baseline, scenario) per stock, propagated mode, with the
    same random numbers as the engine's own run."""
    from pusula.macro.context import build_context, current_passthrough, make_engine
    from pusula.macro.scenarios import HORIZONS, to_factor_shocks

    ctx = _SCEN.get("ctx") or build_context(store(), AS_OF)
    eng = make_engine(ctx)
    spec = to_factor_shocks(shocks, eng.factors, current_passthrough(ctx))
    h = HORIZONS[horizon]
    z, idx = eng._random(h)
    Xb, _ = eng.macro_draws(h, None, "propagated", z)
    Xs, _ = eng.macro_draws(h, spec.factor_shocks, "propagated", z)
    out = {}
    for sym in symbols:
        rb = eng.to_basis(eng.stock_returns(sym, Xb, h, idx[sym]), Xb, h, basis)
        rs = eng.to_basis(eng.stock_returns(sym, Xs, h, idx[sym]), Xs, h, basis)
        out[sym] = (np.expm1(rb), np.expm1(rs))
    return out, spec


def vaka_a_rate_cut() -> list[str]:
    plt = plt_setup()
    syms = [
        ("THYAO.IS", BLUE, "THYAO (BIST30)"),
        ("ENJSA.IS", SUB_COLORS["electricity"], "ENJSA (Enerji: elektrik)"),
        ("TUPRS.IS", SUB_COLORS["refining_petroleum"], "TUPRS (Enerji: rafineri; BIST30)"),
    ]
    d, spec = _scenario_dists({"policy_rate_bp": -300}, [x[0] for x in syms])
    fig, axes = plt.subplots(1, 3, figsize=(8.6, 3.0), sharey=True)
    bins = np.linspace(-0.6, 0.8, 70)
    for ax, (sym, col, title) in zip(axes, syms, strict=True):
        b, sc = d[sym]
        ax.hist(b, bins=bins, color="#BBBBBB", alpha=0.8, density=True, label="baz (şoksuz)")
        ax.hist(
            sc, bins=bins, histtype="step", color=col, lw=1.4, density=True, label="faiz −300 bp"
        )
        de = sc.mean() - b.mean()
        dv = np.quantile(-sc, 0.99) - np.quantile(-b, 0.99)
        dv_txt = ("+" if dv > 0 else "−" if dv < 0 else "") + tr_num(abs(dv) * 100, 2)
        ax.text(
            0.03,
            0.96,
            f"Δ beklenen getiri {tr_pct(de, 2, sign=True)}\nΔ VaR %99 {dv_txt} puan",
            transform=ax.transAxes,
            va="top",
            fontsize=7,
        )
        ax.set_title(title, loc="left", fontsize=8.5)
        ax.set_ylim(0, ax.get_ylim()[1] * 1.3)  # room for the text
        fmt_axis(ax, "x", "frac", 0)
        ax.set_yticks([])
    h, lab = axes[0].get_legend_handles_labels()
    fig.legend(h, lab, fontsize=7, loc="lower center", ncol=2, bbox_to_anchor=(0.5, -0.02))
    lo, mid, hi = spec.rate_band
    fig.suptitle(
        f"Vaka (a): politika faizi −300 bp → 2Y faiz {tr_num(mid, 2)} puan (%90 bant {tr_num(lo, 2)} … {tr_num(hi, 2)}); "
        "3 aylık getiri dağılımı, TL",
        fontsize=9.5,
        x=0.02,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    return save_fig(fig, "sekil_17_vaka_a_faiz_indirimi")


def vaka_b_country_risk() -> list[str]:
    plt = plt_setup()
    df = scenario_results()
    d = df[(df["scenario_id"] == "ulke_riski") & (df["basis"] == "TRY")].drop_duplicates(
        ["symbol", "universe"]
    )
    groups = [("BIST30", d[d["universe"] == "BIST30"], BLUE)]
    for sub in ("refining_petroleum", "natural_gas", "electricity"):
        groups.append(
            (
                f"Enerji: {SUB_TR[sub]}",
                d[(d["universe"] == "Energy") & (d["sub_sector"] == sub)],
                SUB_COLORS[sub],
            )
        )
    fig, ax = plt.subplots(figsize=(7.4, 3.4))
    rng = np.random.default_rng(1)
    for i, (name, g, col) in enumerate(groups):
        v = g["d_exp_ret"].to_numpy() * 100
        ax.scatter(
            i + rng.uniform(-0.15, 0.15, len(v)),
            v,
            color=col,
            s=22,
            alpha=0.85,
            edgecolor="white",
            lw=0.4,
        )
        ax.hlines(np.mean(v), i - 0.3, i + 0.3, color="black", lw=1.4)
        gs = g.sort_values("d_exp_ret")
        show = gs if name != "BIST30" else pd.concat([gs.head(3), gs.tail(3)])
        for _, r in show.iterrows():
            ax.annotate(r["ticker"], (i + 0.18, r["d_exp_ret"] * 100), fontsize=5.5, va="center")
    ax.set_xticks(range(len(groups)), [f"{n}\n(n={len(g)})" for n, g, _ in groups], fontsize=7.5)
    ax.axhline(0, color="black", lw=0.7)
    ax.set_ylabel("beklenen getiri değişimi, 3 ay")
    fmt_axis(ax, "y", "pct", 0)
    ax.set_title(
        "Vaka (b): ülke riski artışı (CDS +200 bp), hisse bazında etki, TL (çizgi: grup ortalaması)",
        loc="left",
        fontsize=9,
    )
    fig.tight_layout()
    return save_fig(fig, "sekil_18_vaka_b_ulke_riski")


def vaka_c_fx_shock() -> list[str]:
    plt = plt_setup()
    df = scenario_results()
    d = df[df["scenario_id"] == "kur_soku"].drop_duplicates(["symbol", "universe", "basis"])
    d = d.assign(sub_sector=d["sub_sector"].fillna("-"))
    piv = d.pivot_table(
        index=["symbol", "universe", "sub_sector"], columns="basis", values="d_exp_ret"
    ).reset_index()
    fig, axes = plt.subplots(1, 2, figsize=(8.2, 3.5), gridspec_kw={"width_ratios": [1, 1.2]})
    ax = axes[0]
    labels, vals_t, vals_u, cols = [], [], [], []
    for name, mask, col in [("BIST30", piv["universe"] == "BIST30", BLUE)] + [
        (
            f"Enerji: {SUB_TR[s_]}",
            (piv["universe"] == "Energy") & (piv["sub_sector"] == s_),
            SUB_COLORS[s_],
        )
        for s_ in ("refining_petroleum", "natural_gas", "electricity")
    ]:
        labels.append(name)
        vals_t.append(piv.loc[mask, "TRY"].mean() * 100)
        vals_u.append(piv.loc[mask, "USD"].mean() * 100)
        cols.append(col)
    x = np.arange(len(labels))
    ax.bar(x - 0.2, vals_t, 0.4, color=cols, label="TL bazında")
    ax.bar(
        x + 0.2,
        vals_u,
        0.4,
        color=cols,
        alpha=0.45,
        hatch="///",
        edgecolor="white",
        label="USD bazında",
    )
    ax.axhline(0, color="black", lw=0.7)
    ax.set_xticks(x, labels, fontsize=7, rotation=20, ha="right")
    fmt_axis(ax, "y", "pct", 0)
    ax.set_title("Grup ortalaması", loc="left", fontsize=9)
    ax.legend(fontsize=7)
    ax = axes[1]
    for u, g in piv.groupby("universe"):
        for sub, gg in g.groupby("sub_sector") if u == "Energy" else [(None, g)]:
            col = BLUE if u == "BIST30" else SUB_COLORS.get(sub, ORANGE)
            ax.scatter(
                gg["TRY"] * 100,
                gg["USD"] * 100,
                color=col,
                s=18,
                alpha=0.85,
                label="BIST30" if u == "BIST30" else f"Enerji: {SUB_TR.get(sub, sub)}",
            )
    lim = np.nanmax(np.abs(piv[["TRY", "USD"]].to_numpy())) * 100 + 1
    ax.plot([-lim, lim], [-lim, lim], color="grey", lw=0.8, ls="--")
    ax.axhline(0, color="black", lw=0.6)
    ax.axvline(0, color="black", lw=0.6)
    ax.set_xlabel("TL bazında beklenen getiri değişimi")
    ax.set_ylabel("USD bazında")
    fmt_axis(ax, "x", "pct", 0)
    fmt_axis(ax, "y", "pct", 0)
    ax.legend(fontsize=6, loc="lower right")
    ax.set_title("Hisse bazında: TL ve USD görünümü", loc="left", fontsize=9)
    guard = bool(d["guard"].any())
    fig.suptitle(
        "Vaka (c): kur şoku (USD/TRY +%15), 3 ay"
        + (" — şok güncel rejimin dışında, tüm örneklem ilişkileri (D-053)" if guard else ""),
        fontsize=9.5,
        x=0.02,
        ha="left",
    )
    fig.tight_layout()
    return save_fig(fig, "sekil_19_vaka_c_kur_soku")


# --------------------------------------------------------------------------- agent comparison table
AGENT_TICKERS = ["THYAO", "AKBNK", "ENJSA", "TUPRS"]


def _first_sentence(text: str, n: int = 170) -> str:
    t_ = text.split(". ")[0].strip().rstrip(".") + "."
    return t_ if len(t_) <= n else t_[: n - 1].rstrip() + "…"


def t11_agent_comparison() -> list[str]:
    """Latest full-mode v3 run per ticker on the freeze date, from stored runs only (no LLM call)."""
    runs = store().query(
        "SELECT ticker, payload, created_at FROM analysis_runs WHERE as_of = ? AND mode LIKE 'full:%' "
        "ORDER BY created_at DESC",
        [AS_OF],
    )
    rows, missing = [], []
    for tk in AGENT_TICKERS:
        cand = runs[runs["ticker"] == f"{tk}.IS"]
        run = None
        for p in cand["payload"]:
            r = json.loads(p)
            if r.get("prompt_versions", {}).get("judge") == "judge.v3" and r.get("decision"):
                run = r
                break
        if run is None:
            missing.append(tk)
            rows.append(
                {
                    "Hisse": tk,
                    "Risk düzeyi": "–",
                    "En büyük senaryo riski (TL, 3 ay)": "–",
                    "Karar": "–",
                    "Güven": "–",
                    "Lehte (özet)": "LLM çalıştırmaları sonrasında eklenecek",
                    "Aleyhte (özet)": "–",
                }
            )
            continue
        inp = run["inputs"]
        sc = inp.get("senaryo", {}).get("senaryolar", [])
        worst = min(sc, key=lambda x: x["tl_beklenen_getiri_degisimi_yuzde"]) if sc else None
        d = run["decision"]
        rows.append(
            {
                "Hisse": tk,
                "Risk düzeyi": inp.get("risk", {}).get("risk_duzeyi", "–"),
                "En büyük senaryo riski (TL, 3 ay)": f"{worst['senaryo']}: {tr_pct(worst['tl_beklenen_getiri_degisimi_yuzde'] / 100, 2)}"
                if worst
                else "–",
                "Karar": d["karar"],
                "Güven": tr_num(d["guven"], 2),
                "Lehte (özet)": _first_sentence(d["lehte_gerekceler"][0]),
                "Aleyhte (özet)": _first_sentence(d["aleyhte_gerekceler"][0]),
            }
        )
    cap = (
        "Tablo 11. Ajan kararlarının karşılaştırması (tam mod, prompt v3, veri 20.11.2026; kayıtlı çalıştırmalardan)"
        + (f". Henüz çalıştırılmayanlar: {', '.join(missing)}" if missing else "")
    )
    return save_tab(pd.DataFrame(rows), "tablo_11_ajan_karar_karsilastirmasi", cap)


ITEMS = {
    "s02": s02_macro,
    "s03": s03_fan,
    "s04": s04_model_selection,
    "t01": t01_descriptive,
    "t02": t02_energy_selection,
    "t03": t03_llm_models,
    "s05": s05_exceedance,
    "s06": s06_pass_heatmap,
    "t04": t04_e1_table,
    "t05": t05_e1_critic,
    "s07": s07_beta_heatmap,
    "s08": s08_r2,
    "t06": t06_e2_table,
    "t07": t07_e2_subsector,
    "s09": s09_scenarios,
    "s10": s10_passthrough,
    "s11": s11_e3_scatter,
    "s12": s12_e3_car,
    "t08": t08_e3_table,
    "s13": s13_e4_equity,
    "s14": s14_e4_decisions,
    "t09": t09_e4_table,
    "t10": t10_e4_long,
    "s15": s15_e5_agreement,
    "s17": vaka_a_rate_cut,
    "s18": vaka_b_country_risk,
    "s19": vaka_c_fx_shock,
    "t11": t11_agent_comparison,
}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--only", nargs="+", choices=list(ITEMS))
    a = ap.parse_args(argv)
    setup_logging("WARNING")
    for key in a.only or list(ITEMS):
        try:
            files = ITEMS[key]()
            print(f"{key}: {', '.join(files) if files else 'skipped'}", flush=True)
        except Exception as exc:  # one failing item must not stop the pack
            print(f"{key}: FAILED ({type(exc).__name__}: {exc})", flush=True)


if __name__ == "__main__":
    _ = Path
    main()
