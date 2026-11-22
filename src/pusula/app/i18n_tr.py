"""All Turkish UI strings in one place (CLAUDE.md §2.6).

Code refers to keys of :data:`TR`; nothing user-visible is hard-coded in page files.
"""

from __future__ import annotations

TR: dict[str, str] = {
    # --- general
    "app_title": "PUSULA",
    "app_subtitle": "Borsa İstanbul için makro koşullu, ajan tabanlı risk analizi platformu",
    "disclaimer": "Bu uygulama akademik bir çalışmadır; yatırım tavsiyesi değildir.",
    # --- navigation
    "nav_home": "Ana Sayfa",
    "nav_data_status": "Veri Durumu",
    # --- navigation (P2/P3)
    "nav_risk": "Hisse Risk Analizi",
    "nav_scenario": "Senaryo Laboratuvarı",
    "nav_compare": "BIST30 vs Enerji",
    # --- common
    "universe_label": "Evren",
    "universe_all": "Tümü",
    "universe_bist30": "BIST30",
    "universe_energy": "Enerji",
    "basis_label": "Getiri bazı",
    "basis_TRY": "TRY (nominal)",
    "basis_REAL": "Reel (TÜFE'den arındırılmış)",
    "basis_USD": "USD",
    "as_of": "Analiz tarihi",
    "stock": "Hisse",
    "no_data": "Veri yok.",
    # --- risk page
    "risk_title": "Hisse Risk Analizi",
    "risk_insufficient": (
        "Bu tarih için yeterli geçmiş yok (en az 250 işlem günü gerekir). Rapor üretilmedi."
    ),
    "risk_level_label": "Evren içi göreli risk düzeyi",
    "risk_level_help": (
        "Göreli bir ölçüdür: aynı tarihteki BIST30 + Enerji hisseleri içinde yıllık oynaklık ve "
        "%99 CVaR yüzdelik sıralarının ortalaması (nominal TRY). "
        "Yanında mutlak değerler gösterilir."
    ),
    "risk_level_dusuk": "Düşük",
    "risk_level_orta": "Orta",
    "risk_level_yuksek": "Yüksek",
    "risk_level_cok_yuksek": "Çok Yüksek",
    "risk_level_missing": "Bu tarih için evren hesaplaması yok; göreli düzey gösterilemiyor.",
    "risk_level_run": "Evren risk düzeylerini hesapla (~1 dk, LLM kullanılmaz)",
    "risk_vol": "Yıllık oynaklık (gerçekleşen)",
    "risk_vol_model": "Yıllık oynaklık (model)",
    "risk_cvar99": "CVaR %99 (1 gün)",
    "risk_beta": "XU100 betası",
    "risk_ploss": "1 ayda %10'dan fazla kayıp olasılığı",
    "risk_selected": "Seçilen model",
    "risk_price_header": "Fiyat",
    "risk_dist_header": "Günlük getiri dağılımı: tarih vs seçilen model",
    "risk_dist_hist": "Gerçekleşen (kalibrasyon penceresi)",
    "risk_dist_model": "Model simülasyonu",
    "risk_fan_header": "Monte Carlo yelpaze grafiği (63 işlem günü)",
    "risk_fan_median": "Medyan",
    "risk_var_header": "Riske maruz değer (VaR) ve beklenen kayıp (CVaR)",
    "risk_var_help": (
        "VaR %99: 100 günden yalnızca 1'inde aşılması beklenen kayıp. CVaR %99: o en kötü "
        "günlerdeki ortalama kayıp. 10 günlük değerler simüle edilen yollardan doğrudan hesaplanır."
    ),
    "risk_horizon": "Vade",
    "risk_1d": "1 gün",
    "risk_10d": "10 gün",
    "risk_dd_header": "Azami düşüş (drawdown) dağılımı",
    "risk_dd_1m": "1 ay",
    "risk_dd_3m": "3 ay",
    "risk_critic_header": "Model seçimi (eleştirmen) puanları",
    "risk_critic_help": (
        "Her kriter modeller arasında sıralanır (1 = en iyi); puan = eşit ağırlıklı ortalama sıra "
        "(düşük = iyi). Karşılaştırma kalibrasyon penceresi içindedir; "
        "Tarihsel Simülasyon 1 günlük "
        "kriterlerde bu nedenle avantajlıdır. Örneklem dışı test E1'dedir."
    ),
    "risk_sensitivity": "Ağırlık duyarlılığı (seçilen model)",
    "risk_failed": "Kalibre edilemeyen modeller",
    "risk_evt_header": "Uç değer (EVT) kuyruk indeksi",
    "risk_evt_none": "EVT: yetersiz veri",
    "risk_evt_xi": "Kuyruk indeksi ξ",
    "risk_window": "Kalibrasyon penceresi",
    "risk_timing": "Hesaplama süresi",
    # --- home
    "home_intro": (
        'PUSULA; bir hissenin **risk profilini** gösterir, **"ya şöyle olursa?"** makro '
        "senaryolarını (faiz, kur, petrol, doğalgaz, ülke riski) simüle eder ve yapay zekâ "
        "ajanlarından oluşan bir ekibin **açıklamalı karar destek** çıktısını sunar."
    ),
    "home_universes": "Evrenler: **BIST30** ve kurala dayalı seçilmiş **10 enerji hissesi**.",
    "home_status_header": "Proje durumu",
    "home_status_body": (
        "Sayfalar proje aşamaları ilerledikçe eklenecektir. Şu an mevcut: **Veri Durumu**."
    ),
    # --- data status page
    "ds_title": "Veri Durumu",
    "ds_no_db": (
        "Veritabanı henüz oluşturulmadı. Terminalde şu komutu çalıştırın: "
        "`uv run python -m pusula.data.update`"
    ),
    "ds_series_header": "Seri bazında kalite raporu",
    "ds_flags_header": "Manuel inceleme gerektiren fiyat sıçramaları (hisse ±%10,5, endeks ±%10)",
    "ds_no_flags": "İşaretlenmiş sıçrama yok.",
    "ds_update_button": "Verileri güncelle",
    "ds_update_running": "Veriler güncelleniyor… (bu işlem birkaç dakika sürebilir)",
    "ds_update_done": "Güncelleme tamamlandı.",
    "ds_update_failed": "Güncelleme sırasında hata oluştu. Ayrıntılar aşağıda.",
    "ds_energy_header": "Enerji hissesi seçimi",
    "ds_energy_missing": (
        "Enerji seçimi henüz yapılmadı: `uv run python -m pusula.universe.select_energy`"
    ),
    "ds_universe_header": "Evren doğrulaması",
    "ds_manual_header": "Manuel dosyalar",
    "ds_col_series": "Seri",
    "ds_col_source": "Kaynak",
    "ds_col_first": "İlk tarih",
    "ds_col_last": "Son tarih",
    "ds_col_coverage": "Kapsama %",
    "ds_col_missing": "Eksik gün",
    "ds_col_stale": "Durağan gün",
    "ds_col_jumps": "Sıçrama",
    "ds_col_updated": "Son güncelleme",
    "ds_col_status": "Durum",
    "ds_col_date": "Tarih",
    "ds_col_ticker": "Hisse",
    "ds_col_prev": "Önceki düz. kapanış",
    "ds_col_adj": "Düz. kapanış",
    "ds_col_return": "Günlük getiri",
    "ds_col_name": "Şirket",
    "ds_col_subsector": "Alt sektör",
    "ds_col_inbist30": "BIST30'da",
    "ds_col_verified": "Doğrulandı",
    "ds_col_file": "Dosya",
    "ds_metric_series": "Seri sayısı",
    "ds_metric_ok": "Sorunsuz",
    "ds_metric_warn": "Uyarılı",
    "ds_metric_missing": "Eksik",
}


def t(key: str) -> str:
    """Return the Turkish string for ``key`` (the key itself if missing, so gaps are visible)."""
    return TR.get(key, key)
