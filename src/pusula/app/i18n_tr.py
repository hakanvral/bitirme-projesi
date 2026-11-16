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
