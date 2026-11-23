# PUSULA

**Borsa İstanbul için makro koşullu, ajan tabanlı risk analizi platformu** (lisans bitirme projesi).

PUSULA, BlackRock Aladdin'den esinlenir. Bir yatırımcının şunları yapmasını sağlar:

1. bir hissenin **risk profilini** görmek,
2. **"ya şöyle olursa?"** makroekonomik senaryolarını simüle etmek (TCMB faiz kararı, USD/TRY şoku, petrol, doğalgaz, ülke riski),
3. yapay zekâ ajanlarından oluşan bir ekibin ürettiği **açıklamalı karar destek** çıktısını (lehte / aleyhte gerekçeler) almak.

Evrenler: **BIST30** ve kurala dayalı seçilmiş **10 enerji hissesi** (elektrik, doğalgaz, rafineri/akaryakıt).

Temel ilke: **sayıları Python hesaplar, dil modeli yalnızca yorumlar.** Ajanların raporlarındaki her sayı, Denetçi tarafından girdiyle karşılaştırılır.

> ⚠️ Bu uygulama akademik bir çalışmadır; yatırım tavsiyesi değildir.

Temel makale: Emmanoulopoulos vd. (2025), *To Trade or Not to Trade: An Agentic Approach to Estimating Market Risk Improves Trading Decisions*, arXiv:2507.08584.

---

## 1. Kurulum

Gereksinim: [uv](https://docs.astral.sh/uv/) (Python 3.12'yi kendisi kurar).

```bash
uv sync
```

`.env.example` dosyasını `.env` olarak kopyalayın ve anahtarları doldurun. `.env` asla commit edilmez.

```bash
cp .env.example .env
```

### Gerekli anahtarlar

| Anahtar | Ne için | Zorunlu mu? | Nereden |
|---|---|---|---|
| `EVDS_API_KEY` | TCMB EVDS3: döviz kuru, TLREF, TÜFE, beklenti anketi | **Evet** (veri güncelleme) | EVDS (evds3.tcmb.gov.tr) üyeliğiyle verilen API anahtarı |
| `NVIDIA_API_KEY` | Ajanlar (NVIDIA NIM ücretsiz katman, Nemotron 3 Ultra) | Yalnızca LLM özellikleri için | NVIDIA NIM (build.nvidia.com) hesabıyla verilen API anahtarı |
| `EPIAS_USERNAME`, `EPIAS_PASSWORD` | EPİAŞ PTF (canlı API) | Hayır (yerine `data/manual/ptf.csv`) | EPİAŞ Şeffaflık Platformu hesabı (giris.epias.com.tr) |
| `ANTHROPIC_API_KEY` | İsteğe bağlı ücretli sağlayıcı | Hayır | Anthropic API hesabı |

LLM sağlayıcısı ve modeli `config/settings.yaml` → `llm` bölümündedir. Ollama veya OpenAI uyumlu başka bir uç nokta da kullanılabilir (`.env.example` dosyasına bakın).

### Elle sağlanması gereken dosyalar

Ayrıntılar ve adım adım indirme talimatları: [`data/manual/README.md`](data/manual/README.md).

| Dosya | Gerekli mi? | Not |
|---|---|---|
| `data/manual/cds_tr_5y.csv` | **Evet** (CDS faktörü) | investing.com'dan indirilir; yeniden dağıtılamaz, git'e eklenmez |
| `data/manual/tr_2y_yield.csv` | **Evet** (faiz faktörü; yoksa TLREF kullanılır) | investing.com; git'e eklenmez |
| `data/manual/ptf.csv` | Elektrik hisseleri için önerilir | EPİAŞ Şeffaflık Platformu dışa aktarımı |
| `data/manual/ppk_decisions.csv` | **Evet** (E3) | Depoda hazır; `python -m pusula.data.prefill ppk` ile yeniden üretilebilir |

Kullanıcı onayı bekleyen yapılandırmalar: `config/universe.yaml` (iki BIST30 listesi), `config/energy_candidates.yaml` (`verified: false`) ve `config/corporate_actions.yaml` (önerilen 4 düzeltme).

## 2. Verileri güncelleme

```bash
uv run python -m pusula.data.update                  # tüm veriler (artımlı); --full, --only
uv run python -m pusula.universe.validate --names    # her Yahoo sembolünün indiğini kontrol et
uv run python -m pusula.universe.select_energy       # 10 enerji hissesini kurala göre seç
uv run python -m pusula.data.jump_review --write     # fiyat sıçramalarını sınıflandır
```

Veriler `data/pusula.duckdb` dosyasına, ham indirmeler `data/raw/` klasörüne yazılır. Kalite raporu arayüzdeki **Veri Durumu** sayfasındadır.

## 3. Uygulamayı çalıştırma

```bash
uv run python -m pusula.risk.run_universe            # bugünün risk düzeyleri (Genel Bakış ısı haritası)
uv run streamlit run src/pusula/app/Home.py          # arayüz: http://localhost:8501
```

Sayfalar: **Genel Bakış**, Hisse Risk Analizi, Senaryo Laboratuvarı, BIST30 vs Enerji, Ajan Kararı, **Backtest & Değerlendirme**, Veri Durumu, Ayarlar. LLM çağrıları yalnızca düğmeyle yapılır; sayfa açılırken asla yapılmaz.

**Canlı sunum için ön ısıtma:** aşağıdaki komut THYAO, AKBNK, ENJSA ve TUPRS için tam analizi önceden çalıştırır. Sunumda aynı hisse ve tarih önbellekten anında gelir.

```bash
uv run python -m pusula.demo.warmup
```

## 4. Makale sonuçlarını yeniden üretme (E1–E5)

Tek komut (LLM adımlarından önce süre tahmini gösterir ve onay ister):

```bash
uv run python -m pusula.evaluation.paper_results
```

Deneyler tek tek de çalıştırılabilir:

| Deney | Komut | Süre (4 çekirdek) | LLM |
|---|---|---|---|
| E1 VaR backtest'i | `uv run python -m pusula.evaluation.var_backtest` | ~30–45 dk | – |
| E2 faktör modeli | `uv run python -m pusula.evaluation.factor_eval` | ~10 sn | – |
| E3 PPK olay çalışması | `uv run python -m pusula.evaluation.event_study` | ~3 dk | – |
| E4 karar backtest'i | `uv run python -m pusula.evaluation.trading_backtest` | risk ~30 dk + girdiler ~15 dk + LLM ~1 sa | ~2.200 kısa çağrı |
| E5 LLM güvenilirliği | `uv run python -m pusula.evaluation.llm_reliability` | ~1–2 sa | ~200 çağrı + 6 tam analiz |

- Her çalıştırma `results/<deney>/<zaman>/` klasörüne CSV, LaTeX, PNG ve SVG dosyalarını ve kullanılan yapılandırmanın bir kopyasını yazar.
- NVIDIA'nın ücretsiz katmanı yoğun olduğunda istekleri kısıtlayabilir veya modeli geçici olarak kapatabilir (D-073). Hızı düşürmek için: `PUSULA_LLM_RPM=20 PUSULA_LLM_CONCURRENCY=2` ortam değişkenleri.
- E4 ve E5 **devam ettirilebilir**: biten LLM çağrıları `data/llm_cache.sqlite` önbelleğinde tutulur, yeniden çalıştırmada atlanır.
- E4'ün aşamaları ayrı ayrı çalıştırılabilir: `--stages risk inputs llm eval`.
- Özet ve yorumlar: [`docs/RESULTS.md`](docs/RESULTS.md).

## 5. Testler ve kod kalitesi

```bash
uv run pytest                                        # ağ kullanmaz; LLM yerine MockLLMClient
uv run ruff check . && uv run ruff format .
```

## 6. Belgeler

- [`CLAUDE.md`](CLAUDE.md): proje tanımı (İngilizce)
- [`docs/RESULTS.md`](docs/RESULTS.md): E1–E5 sonuçları ve şekil listesi
- [`docs/DECISIONS.md`](docs/DECISIONS.md): metodolojik kararlar (makalenin yöntem bölümü)
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md): bilinen kısıtlar
- [`docs/PROGRESS.md`](docs/PROGRESS.md): aşama ilerlemesi ve devam ettirme komutları
- [`docs/EXPERIMENTS_PLAN.md`](docs/EXPERIMENTS_PLAN.md): deney talimatları
- [`docs/data_sources.md`](docs/data_sources.md), [`docs/universe_selection.md`](docs/universe_selection.md): veri kaynakları ve enerji seçimi
- [`docs/prompt_v3_before_after.md`](docs/prompt_v3_before_after.md): prompt v3 öncesi / sonrası
