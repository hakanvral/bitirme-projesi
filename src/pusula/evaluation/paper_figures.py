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


ITEMS = {
    "s02": s02_macro,
    "s03": s03_fan,
    "s04": s04_model_selection,
    "t01": t01_descriptive,
    "t02": t02_energy_selection,
    "t03": t03_llm_models,
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
