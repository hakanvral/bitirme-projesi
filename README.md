# PUSULA

**Borsa İstanbul için makro koşullu, ajan tabanlı risk analizi platformu** — lisans bitirme projesi.

PUSULA, BlackRock Aladdin'den esinlenir. Bir yatırımcının:

1. bir hissenin **risk profilini** görmesini,
2. **"ya şöyle olursa?"** makroekonomik senaryolarını (TCMB faiz kararı, USD/TRY şoku, petrol, doğalgaz, ülke riski) simüle etmesini,
3. yapay zekâ ajanlarından oluşan bir ekibin ürettiği **açıklamalı karar destek** çıktısını (lehte / aleyhte gerekçeler) almasını

sağlar. Evrenler: **BIST30** ve kurala dayalı seçilmiş **10 enerji hissesi** (elektrik, doğalgaz, rafineri/akaryakıt).

> ⚠️ Bu uygulama akademik bir çalışmadır; yatırım tavsiyesi değildir.

Temel makale: Emmanoulopoulos vd. (2025), *To Trade or Not to Trade: An Agentic Approach to Estimating Market Risk Improves Trading Decisions*, arXiv:2507.08584.

## Kurulum

Gereksinim: [uv](https://docs.astral.sh/uv/) (Python 3.12'yi kendisi kurar).

```bash
uv sync
```

`.env.example` dosyasını `.env` olarak kopyalayıp anahtarları doldurun (`.env` asla commit edilmez):

```bash
cp .env.example .env
```

## Çalıştırma

```bash
uv run python -m pusula.data.update                 # verileri indir / güncelle (artımlı)
uv run python -m pusula.universe.validate           # BIST30 ve enerji adaylarını yfinance ile doğrula
uv run python -m pusula.universe.select_energy      # 10 enerji hissesini kurala göre seç
uv run streamlit run src/pusula/app/Home.py         # arayüz
uv run pytest                                       # testler
uv run ruff check . && uv run ruff format .         # kod kalitesi
```

## Elle sağlanması gereken dosyalar

Bkz. [`data/manual/README.md`](data/manual/README.md): her dosyanın kaynağı ve sütun şeması orada.

## Belgeler

- [`CLAUDE.md`](CLAUDE.md): proje tanımı (İngilizce)
- [`docs/DECISIONS.md`](docs/DECISIONS.md): metodolojik kararlar
- [`docs/PROGRESS.md`](docs/PROGRESS.md): aşama ilerlemesi
- [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md): bilinen kısıtlar
- [`docs/data_sources.md`](docs/data_sources.md): veri kaynakları
