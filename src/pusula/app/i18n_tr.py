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
    "nav_home": "Genel Bakış",
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
    "risk_insample_choice": "Örneklem içi eleştirmenin seçimi",
    "risk_critic_help": (
        "Varsayılan (hold-out): her model pencerenin ilk %80'inde kalibre edilir, simülasyonu son "
        "%20'lik gerçekleşen dönemle karşılaştırılır; "
        "seçilen model tüm pencereyle yeniden kurulur. "
        "Her kriter modeller arasında sıralanır (1 = en iyi); puan = eşit ağırlıklı ortalama sıra "
        "(düşük = iyi). Örneklem içi puan yalnızca karşılaştırma içindir: orada "
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
    # --- factors
    "factor_rate": "Faiz",
    "factor_usdtry": "USD/TRY",
    "factor_brent": "Brent",
    "factor_ttf": "TTF doğalgaz",
    "factor_cds": "CDS (5Y)",
    "factor_vix": "VIX",
    "factor_us10y": "ABD 10Y",
    "factor_ptf": "PTF (elektrik)",
    "factor_market_resid": "Piyasa artığı",
    "subsector_electricity": "Elektrik",
    "subsector_natural_gas": "Doğalgaz",
    "subsector_refining_petroleum": "Rafineri / akaryakıt",
    # --- missing inputs
    "missing_header": "Eksik veri uyarısı",
    "missing_cds": "CDS verisi yok (cds_tr_5y.csv): ülke riski faktörü ve CDS şokları devre dışı.",
    "missing_ptf": "PTF verisi yok (ptf.csv veya EPİAŞ): elektrik fiyatı faktörü devre dışı.",
    "missing_tr_2y": "2 yıllık tahvil faizi yok: faiz faktörü olarak TLREF kullanılıyor.",
    "missing_tr_2y_short": (
        "2 yıllık tahvil faizi dosyası 2 yıldan kısa: faiz faktörü olarak TLREF kullanılıyor "
        "(tr_2y_yield.csv'yi 2018'den bugüne indirin)."
    ),
    "missing_cds_short": "CDS dosyası 2 yıldan kısa: ülke riski faktörü devre dışı.",
    "missing_fix": (
        "Dosyayı data/manual/ klasörüne koyup `uv run python -m pusula.data.update` çalıştırın; "
        "sayfa yeniden hesaplanır."
    ),
    # --- scenario page
    "sc_title": "Senaryo Laboratuvarı",
    "sc_preset": "Hazır senaryo",
    "sc_custom": "Özel senaryo",
    "sc_horizon": "Vade",
    "sc_h_1m": "1 ay",
    "sc_h_3m": "3 ay",
    "sc_mode": "Senaryo modu",
    "sc_mode_propagated": "Yayılımlı (diğer faktörler koşullu hareket eder)",
    "sc_mode_isolated": "Yalıtılmış (yalnızca şoklanan faktörler)",
    "sc_cov": "Makro kovaryans dönemi",
    "sc_cov_current": "Güncel rejim",
    "sc_cov_full": "Tüm örneklem",
    "sc_basis": "Getiri bazı",
    "sc_rate_mode": "Faiz şoku girişi",
    "sc_rate_policy": "Politika faizi (bp)",
    "sc_rate_market": "Piyasa faizi (bp)",
    "sc_usdtry": "USD/TRY (%)",
    "sc_brent": "Brent (%)",
    "sc_ttf": "TTF (%)",
    "sc_cds": "CDS (bp)",
    "sc_vix": "VIX (puan)",
    "sc_us10y": "ABD 10Y (bp)",
    "sc_passthrough": "Politika faizinden piyasa faizine geçiş",
    "sc_passthrough_text": (
        "Politika faizi {bp:+.0f} bp → {src} değişimi ≈ {mid:+.2f} puan "
        "(%90 bant: {lo:+.2f} … {hi:+.2f}); rejim: {regime}, β = {beta:.2f}"
    ),
    "sc_ignored": "Verisi olmayan faktör şokları yok sayıldı",
    "sc_no_shock": "Şok tanımlanmadı.",
    "sc_summary": "Evren özeti (taban senaryoya göre değişim)",
    "sc_all": "Tüm hisseler",
    "sc_no_overlap": "Çakışan hisseler hariç",
    "sc_d_exp": "Δ beklenen getiri",
    "sc_d_var": "Δ VaR %99",
    "sc_d_cvar": "Δ CVaR %99",
    "sc_d_ploss": "Δ zarar olasılığı",
    "sc_rank": "Sıra değişimi",
    "sc_median": "Δ beklenen getiri (medyan)",
    "sc_band": "Geçiş bandı (düşük / yüksek)",
    "sc_by_stock": "Hisse bazında etki: BIST30 ve Enerji",
    "sc_implied": "Faktörlerin beklenen değişimi (ufuk toplamı)",
    "sc_implied_base": "Taban",
    "sc_implied_scen": "Senaryo",
    "sc_analogues": "Tarihsel benzer dönemler",
    "sc_analogues_help": (
        "Şoklanan faktörlerin geçmişte benzer hareket ettiği, çakışmayan dönemler ve o dönemlerde "
        "gerçekleşen getiriler. Modelden bağımsız bir sağlama kontrolüdür."
    ),
    "sc_real_na": "Reel baz için yayımlanmış enflasyon beklentisi verisi yok; TRY veya USD seçin.",
    "sc_guard": (
        "Bu şok, seçilen rejimin bu ufuktaki deneyiminin {z:.0f} standart sapma dışında. Rejime "
        "özgü ilişkileri bu kadar uzağa taşımak anlamsız sonuçlar verir; yayılımlı mod bu "
        "çalıştırmada tüm örneklem kovaryansını kullandı."
    ),
    "sc_guard_iso": (
        "Bu şok, seçilen rejimin deneyiminin {z:.0f} standart sapma dışında; sonuçları "
        "temkinle yorumlayın."
    ),
    "sc_real_note": (
        "Reel getiri = nominal getiri − ufuk boyunca beklenen enflasyon (piyasa katılımcılarının "
        "12 aylık beklentisi: %{pi:.1f}). TÜFE simüle edilmez; bu nedenle şok etkileri TRY ile "
        "neredeyse aynıdır, yalnızca seviyeler kayar."
    ),
    "sc_usd_note": (
        "USD getiri = TRY getiri − aynı simülasyondaki USD/TRY değişimi. Kur şoku nominal TRY "
        "fiyatlarını artırırken aynı hissenin dolar değerini düşürebilir."
    ),
    "cmp_basis_note_TRY": "Betalar nominal TRY haftalık getirilere göredir.",
    "cmp_basis_note_USD": (
        "USD bazında yalnızca USD/TRY betası değişir (TRY betası − 1): dolar bazlı yatırımcı için "
        "kur artışı ek bir kayıptır. Diğer betalar aynıdır."
    ),
    "cmp_basis_note_REAL": (
        "Reel bazda betalar TRY ile aynıdır (enflasyon beklentisi sabit bir düzeltmedir); "
        "duyarlılık grafiği reel getirilerle hesaplanır."
    ),
    # --- comparison page
    "cmp_title": "BIST30 vs Enerji",
    "cmp_heatmap": "Faktör betaları ısı haritası (Model A)",
    "cmp_std": "Standartlaştırılmış (1 standart sapmalık haftalık faktör hareketine tepki)",
    "cmp_raw": "Ham beta",
    "cmp_heat_help": (
        "Standartlaştırılmış beta = beta × faktörün haftalık standart sapması: farklı birimli "
        "faktörleri karşılaştırılabilir kılar. * = %5 düzeyinde anlamlı (Newey–West)."
    ),
    "cmp_group": "Evren / alt sektör ortalamaları",
    "cmp_r2": "Açıklama gücü (R²): Model A ve Model B",
    "cmp_vif": "Çoklu doğrusallık (VIF)",
    "cmp_sens": "Hazır senaryolara duyarlılık (3 ay, yayılımlı; ortalama Δ beklenen getiri)",
    "cmp_rolling": "Kayan 2 yıllık beta",
    "cmp_regime": "Rejimlere göre beta",
    "cmp_ridge": "Ridge (sağlamlık kontrolü) ve OLS betaları",
    # --- agents (P4)
    "nav_agent": "Ajan Kararı",
    "nav_settings": "Ayarlar",
    "ag_title": "Ajan Kararı",
    "ag_intro": (
        "Seçilen hisse için deterministik risk ve senaryo sonuçları hesaplanır; ardından Risk "
        "Analisti, Senaryo Analisti, Lehte/Aleyhte (Bull/Bear) ajanları ve Karar Ajanı çalışır, "
        "Denetçi her sayıyı girdiyle karşılaştırır. LLM yalnızca butona basınca çağrılır."
    ),
    "ag_mode": "Mod",
    "ag_mode_full": "Tam (tüm ajanlar)",
    "ag_mode_anonymized": "Anonim (Hisse A, tarih gizli)",
    "ag_mode_lean": "Yalın (tek karar çağrısı)",
    "ag_ablation": "Girdi blokları",
    "ag_ablation_help": "P: fiyat/trend, R: risk raporu, S: makro senaryolar",
    "ag_run": "Analizi çalıştır",
    "ag_running": "Ajanlar çalışıyor… (ücretsiz katmanda birkaç dakika sürebilir)",
    "ag_cost_note": (
        "Tahmini istek sayısı: {n}. Önbellekteki çağrılar tekrar gönderilmez. "
        "Ücretsiz katman: dakikada en fazla {rpm} istek."
    ),
    "ag_decision": "Karar destek kartı",
    "ag_confidence": "Güven",
    "ag_horizon": "Vade",
    "ag_for": "Lehte gerekçeler",
    "ag_against": "Aleyhte gerekçeler",
    "ag_risks": "Temel riskler",
    "ag_conditions": "Kararı değiştirecek koşullar",
    "ag_risk_report": "Risk Analisti raporu",
    "ag_scenario_report": "Senaryo Analisti raporu",
    "ag_debate": "Lehte / aleyhte tartışma",
    "ag_bull": "Lehte (Bull)",
    "ag_bear": "Aleyhte (Bear)",
    "ag_audit_ok": "Denetim geçti",
    "ag_audit_fail": "Denetim uyarısı",
    "ag_audit_numbers": "{n} sayı kontrol edildi; girdide bulunmayan: {bad}",
    "ag_regenerated": "Yeniden üretilen raporlar",
    "ag_usage": "Bu çalıştırmanın kullanımı",
    "ag_history": "Çalıştırma geçmişi",
    "ag_inputs": "Ajanlara verilen girdi (JSON)",
    "ag_limits": "Veri kısıtları",
    "ag_summary": "Özet",
    "ag_level_expl": "Risk düzeyi açıklaması",
    "ag_drivers": "Ana risk kaynakları",
    "ag_meaning": "Metrikler ne anlama geliyor?",
    "ag_hurt": "Zarar veren senaryolar",
    "ag_help": "Fayda sağlayan senaryolar",
    "ag_sensitive": "En hassas faktör",
    "ag_contrast": "BIST30 – Enerji karşılaştırması",
    "ag_button_risk": "Risk Analisti raporunu üret (LLM)",
    "ag_button_scenario": "Senaryo Analisti raporunu üret (LLM)",
    "ag_error": "LLM çağrısı başarısız oldu",
    # --- settings
    "set_title": "Ayarlar",
    "set_provider": "LLM sağlayıcısı",
    "set_keys": "Anahtar durumu (anahtarlar hiçbir zaman gösterilmez)",
    "set_key_set": "tanımlı",
    "set_key_missing": "yok (bulut ortamında ağ sırrı olarak eklenmiş olabilir)",
    "set_usage": "Toplam LLM kullanımı",
    "set_usage_by": "Model ve ajan bazında",
    "set_cost_note": "Ücretsiz katman: maliyet 0 olarak kaydedilir; token ve süre izlenir.",
    "set_cache": "Yanıt önbelleği: {n} kayıt",
    # --- home
    "home_intro": (
        'PUSULA; bir hissenin **risk profilini** gösterir, **"ya şöyle olursa?"** makro '
        "senaryolarını (faiz, kur, petrol, doğalgaz, ülke riski) simüle eder ve yapay zekâ "
        "ajanlarından oluşan bir ekibin **açıklamalı karar destek** çıktısını sunar."
    ),
    "home_universes": "Evrenler: **BIST30** ve kurala dayalı seçilmiş **10 enerji hissesi**.",
    "home_status_header": "Proje durumu",
    "home_status_body": (
        "Tüm sayfalar hazır: Genel Bakış, Hisse Risk Analizi, Senaryo Laboratuvarı, "
        "BIST30 vs Enerji, Ajan Kararı, Backtest & Değerlendirme, Veri Durumu ve Ayarlar."
    ),
    # --- evaluation viewer (Backtest & Değerlendirme, P5–P6)
    "nav_eval": "Backtest & Değerlendirme",
    "ev_intro": (
        "Makaledeki deneylerin (E1–E5) sonuçları. Sayfa yalnızca `results/` klasöründeki en son "
        "çalıştırmayı okur; deney başlatmaz ve LLM çağrısı yapmaz."
    ),
    "ev_tab_e1": "E1 · Risk modeli (VaR)",
    "ev_tab_e2": "E2 · Faktör modeli",
    "ev_tab_e3": "E3 · PPK olay çalışması",
    "ev_tab_e4": "E4 · Karar backtest'i",
    "ev_tab_e5": "E5 · LLM güvenilirliği",
    "ev_run": "Çalıştırma: {run} · klasör: `{path}`",
    "ev_not_run": "Bu deney henüz çalıştırılmadı. Komut: `{cmd}`",
    "ev_missing_file": "Dosya bulunamadı: {f}",
    "ev_more": "Ayrıntılı tablolar",
    "ev_level": "VaR güven düzeyi",
    "ev_group": "Grup",
    "ev_window": "Dönem",
    "ev_cmd_e1_var": "uv run python -m pusula.evaluation.var_backtest",
    "ev_cmd_e2_factor": "uv run python -m pusula.evaluation.factor_eval",
    "ev_cmd_e3_event": "uv run python -m pusula.evaluation.event_study",
    "ev_cmd_e4_backtest": "uv run python -m pusula.evaluation.trading_backtest",
    "ev_cmd_e5_llm": "uv run python -m pusula.evaluation.llm_reliability",
    "ev_e1_text": (
        "Her hisse için 2019'dan bugüne her gün 1 günlük VaR tahmini yapıldı (modeller 5 işlem "
        "gününde bir yeniden kalibre edildi). İyi bir VaR %99 modelinde kayıp, tahmini yaklaşık "
        "100 günde 1 aşmalıdır. **Kupiec** testi aşım sayısını, **Christoffersen** testi aşımların "
        "kümelenip kümelenmediğini sınar. Tablolarda: aşım oranı, testi reddeden hisse payı ve "
        "kuantil kaybı (düşük = daha iyi)."
    ),
    "ev_e1_critic": "Ana soru: hold-out kritik, örneklem içi kritiği ve sade HS'yi geçiyor mu?",
    "ev_e1_selection": "Kritiklerin model seçim payları",
    "ev_e1_regime": "Rejimlere göre sonuçlar",
    "ev_e2_text": (
        "Makro faktör modelinin açıklama gücü: örneklem içi R² ve 2 yıl ile kurulup sonraki 26 "
        "haftada sınanan örneklem dışı R². Faktör duyarlılıkları, 1 standart sapmalık haftalık "
        "harekete yüzde tepki olarak gösterilir. BIST30 ve Enerji, örtüşen hisse (TUPRS) dahil ve "
        "hariç karşılaştırılır."
    ),
    "ev_e3_text": (
        "2018'den bu yana PPK faiz kararları: karar gününün etrafındaki [−1, +5] işlem "
        "günü penceresinde gerçekleşen tepki ile senaryo motorunun yalnızca karar öncesi "
        "veriyle yaptığı tahmin karşılaştırılır (yön isabeti ve ortalama mutlak hata, "
        "olay bazlı bootstrap güven aralıklarıyla). Örneklem küçüktür; sonuçlar temkinli "
        "yorumlanmalıdır."
    ),
    "ev_e4_text": (
        "10 hisse (5 BIST30 + 5 Enerji) için haftalık karar: cuma kapanışında karar, sonraki hafta "
        "boyunca pozisyon; işlem maliyeti 10 bp + kayma 5 bp; nakit TLREF getirir. "
        "LLM varyantları: P (yalnız fiyat/trend), P+R (+ risk), P+R+S (+ senaryolar), "
        "P+R+S anonim. 'Kesim sonrası' dönem, modelin eğitim verisi kesim tarihinden "
        "sonraki haftalardır."
    ),
    "ev_e4_ci": "Sharpe farkları için durağan bootstrap %95 güven aralıkları (TRY)",
    "ev_e4_coverage": (
        "LLM varyantlarının kapsamı (yalnızca hisse-haftaların en az %98'inde kararı olan "
        "varyantlar değerlendirilir)"
    ),
    "ev_e4_dist": "Karar dağılımı (BEKLE payı %70'i aşarsa işaretlenir)",
    "ev_e5_text": (
        "Aynı girdiye tekrar tekrar sorulduğunda modelin kararı ne kadar tutarlı (Fleiss κ)? "
        "Farklı modeller ve akıl yürütme açık/kapalı aynı kararı veriyor mu? Tam modda denetçinin "
        "sayısal doğruluk oranı ve rapor yeniden üretme sıklığı."
    ),
    "ev_e5_full": "Tam mod: denetçi sonuçları (6 analiz)",
    # --- overview (Genel Bakış, P7)
    "ov_macro": "Makro görünüm",
    "ov_policy": "Politika faizi (1 hafta repo)",
    "ov_tlref": "TLREF",
    "ov_usdtry": "USD/TRY",
    "ov_cpi": "Yıllık TÜFE enflasyonu",
    "ov_brent": "Brent petrol",
    "ov_ttf": "TTF doğalgaz",
    "ov_cds": "Türkiye 5Y CDS",
    "ov_xu100": "BIST 100 (XU100)",
    "ov_as_of": "Son veri: {d}",
    "ov_delta_note": (
        "Değişimler yaklaşık bir hafta öncesine göredir (faiz ve CDS: puan / baz puan farkı; "
        "diğerleri: yüzde değişim). Enflasyon yalnızca yayımlanmış TÜFE verisinden hesaplanır."
    ),
    "ov_heatmap": "Risk ısı haritası (evren içi göreli risk düzeyi)",
    "ov_heatmap_note": (
        "Risk hesaplama tarihi: {d} · nominal TRY · renk = risk skoru (oynaklık ve CVaR "
        "yüzdeliklerinin ortalaması; 0 = evrenin en düşük riskli hissesi, 100 = en yüksek)."
    ),
    "ov_hover": (
        "{n}: {lvl}<br>Risk skoru: {s:.1f}<br>Yıllık oynaklık: %{v:.1f}<br>"
        "CVaR %99 (1 gün): %{c:.2f}<br>Seçilen model: {m}"
    ),
    "ov_score": "Risk skoru",
    "ov_overlap_note": "TUPRS hem BIST30 hem Enerji evrenindedir; iki panelde de gösterilir.",
    "ov_about": "PUSULA nedir?",
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
    "db_empty": (
        "Veritabanında henüz fiyat verisi yok. Proje klasöründe sırayla şu komutları "
        "çalıştırın, sonra sayfayı yenileyin:\n\n"
        "`uv run python -m pusula.data.update --frozen-rebuild`\n\n"
        "`uv run python -m pusula.risk.run_universe --as-of 2026-11-20`"
    ),
    "ds_freeze": (
        "Veri dondurma açık: makale {d} tarihli veriyi kullanıyor ve LLM deneyleri (E4, E5) "
        "sürüyor. Deneyler bitene kadar veri güncellemesi kapalıdır."
    ),
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


# Column labels of the result tables shown on the evaluation page (files keep English names).
EVAL_COLUMNS: dict[str, str] = {
    "group": "Grup",
    "model": "Model",
    "level": "Düzey",
    "n_days": "Gün",
    "n_stocks": "Hisse",
    "exceed_rate": "Aşım oranı",
    "pooled_kupiec_p": "Kupiec p (havuz)",
    "share_reject_pof": "POF red payı",
    "share_reject_ind": "Bağımsızlık red payı",
    "share_reject_cc": "Koşullu kapsama red payı",
    "tick_loss_x1e4": "Kuantil kaybı (×10⁴)",
    "comparison": "Karşılaştırma",
    "holdout_lower_tick_loss": "Hold-out daha iyi (hisse)",
    "sign_test_p": "İşaret testi p",
    "holdout_closer_coverage": "Hold-out kapsama daha yakın (hisse)",
    "strategy": "Strateji",
    "cum_return": "Kümülatif getiri",
    "cagr": "Yıllık bileşik getiri",
    "vol_ann": "Yıllık oynaklık",
    "sharpe": "Sharpe",
    "sortino": "Sortino",
    "max_drawdown": "Azami düşüş",
    "calmar": "Calmar",
    "hit_rate": "İsabet oranı",
    "turnover_weekly": "Haftalık devir",
    "avg_position": "Ort. pozisyon",
    "direction_accuracy": "Yön isabeti",
    "acc_ci_lo": "İsabet GA alt",
    "acc_ci_hi": "İsabet GA üst",
    "mae_pct": "OMH (%)",
    "mae_ci_lo": "OMH GA alt",
    "mae_ci_hi": "OMH GA üst",
    "n_events": "Olay",
    "n_obs": "Gözlem",
    "sharpe_diff": "Sharpe farkı",
    "ci_lo": "GA alt",
    "ci_hi": "GA üst",
    "p_two_sided": "p (çift yönlü)",
    "metric": "Ölçüt",
    "value": "Değer",
    "agreement": "Uyum",
    "cohen_kappa": "Cohen κ",
    "mean_tick_loss_holdout_x1e4": "Hold-out kuantil kaybı (×10⁴)",
    "mean_tick_loss_other_x1e4": "Diğerinin kuantil kaybı (×10⁴)",
    "mean_pred_pct": "Ort. tahmin (%)",
    "mean_real_pct": "Ort. gerçekleşen (%)",
    "corr": "Korelasyon",
    "window": "Dönem",
    "basis": "Baz",
    "a": "A",
    "b": "B",
    "n": "N",
    "rater": "Değerlendirici",
    "karar": "Karar",
    "sample": "Örneklem",
    "BIST30_mean": "BIST30 ort.",
    "BIST30_median": "BIST30 medyan",
    "Energy_mean": "Enerji ort.",
    "Energy_median": "Enerji medyan",
    "mw_p": "Mann–Whitney p",
    "n_BIST30": "N BIST30",
    "n_Energy": "N Enerji",
    "expected": "Beklenen",
    "mean_var": "Ort. VaR",
    "regime": "Rejim",
    "variant": "Varyant",
    "decisions": "Karar sayısı",
    "coverage": "Kapsam",
    "evaluated": "Değerlendirildi",
}
