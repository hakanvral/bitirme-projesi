# Kalan LLM işlerini kendi Windows bilgisayarında çalıştırma

Bu rehber, E4 (karar backtest'i) ve E5 (LLM güvenilirliği) deneylerinin kalan LLM çağrılarını kendi bilgisayarında çalıştırman için adım adım yazıldı. Komut satırı deneyimi gerekmez: her komutu kopyalayıp yapıştırman yeterli.

> ⚠️ **Aynı anda tek bir yerde çalıştır.** Bulutta (Claude oturumunda) çalışan işlem varken kendi bilgisayarında da başlatırsan aynı çağrılar iki kez yapılır ve git'te çakışma olur. Başlamadan önce Claude'a "buluttaki LLM işlemini durdur" de.

Ne olacak, kısaca:
1. Projeyi indireceksin.
2. Verileri ve E4 girdilerini kendi bilgisayarında yeniden üreteceksin (yaklaşık 1 saat).
3. Bulutta kaydedilmiş LLM yanıtlarını geri yükleyeceksin.
4. Kalan çağrıları başlatacaksın.

Program her 100 yeni yanıtta ilerlemeyi otomatik olarak GitHub'a gönderir. Bilgisayar kapanırsa aynı komutla kaldığı yerden devam eder.

---

## 1. Gerekli programları kur (bir kez)

1. **Git:** https://git-scm.com/download/win adresinden "64-bit Git for Windows Setup" dosyasını indir ve kur. Kurulumda tüm seçenekleri varsayılan bırak.
2. **PowerShell'i aç:** Başlat menüsüne `PowerShell` yaz, **Windows PowerShell**'e tıkla. Açılan mavi/siyah pencere "terminal"dir. Aşağıdaki komutları buraya yapıştırıp **Enter**'a basacaksın (yapıştırmak için pencereye sağ tıklamak yeterli).
3. **uv** (Python'u ve kütüphaneleri kuran araç):

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

   Bitince PowerShell penceresini **kapatıp yeniden aç** (yoksa `uv` komutu tanınmaz).
4. Git'e adını ve e-postanı tanıt (GitHub hesabındakilerle aynı olsun):

   ```powershell
   git config --global user.name "Adın Soyadın"
   ```

   ```powershell
   git config --global user.email "github-e-postan@ornek.com"
   ```

## 2. Projeyi indir

```powershell
cd $HOME\Documents
```

```powershell
git clone https://github.com/hakanvral/bitirme-projesi.git
```

```powershell
cd bitirme-projesi
```

```powershell
git checkout claude/new-session-2l9tgd
```

```powershell
uv sync
```

`uv sync` ilk seferde birkaç dakika sürer (Python 3.12 ve kütüphaneler iner).

## 3. Anahtarlar (.env dosyası)

```powershell
copy .env.example .env
```

```powershell
notepad .env
```

Açılan Not Defteri'nde şu satırları doldur, kaydet (Ctrl+S) ve kapat:

```
NVIDIA_API_KEY=buraya-nvidia-anahtarın
EVDS_API_KEY=buraya-evds-anahtarın
```

`.env` dosyası asla GitHub'a gönderilmez (git bunu yok sayar). Anahtarlarını kimseyle paylaşma.

## 4. Elle sağlanan veri dosyaları

Daha önce bana gönderdiğin dosyaları şu klasöre kopyala: `Documents\bitirme-projesi\data\manual\`

- `cds_tr_5y.csv`
- `tr_2y_yield.csv`
- `ptf.csv` (varsa)

Biçim kuralları `data\manual\README.md` dosyasında.

## 5. Verileri ve E4 girdilerini üret (yaklaşık 1 saat)

```powershell
uv run python -m pusula.data.update --frozen-rebuild
```

> **Veri dondurma (D-076):** makale 2026-11-20 tarihli veriyi kullanır. `--frozen-rebuild` boş veritabanını yalnızca bu tarihe kadarki veriyle doldurur. Normal `data.update` komutu, deneyler bitene kadar bilerek çalışmaz. Yeniden indirilen veri buluttakiyle neredeyse aynıdır; birebir aynı değildir (Yahoo düzeltilmiş fiyatları sonradan güncelleyebilir). Daha önce alınmış kararlar karar kaydından okunur, yeniden hesaplanmaz.

```powershell
uv run python -m pusula.evaluation.trading_backtest --stages risk inputs --workers 4
```

İkinci komut her hafta için risk raporlarını ve yapay zekâya verilecek girdileri hazırlar. Ekrana `[risk] 12/53 …` ve `[inputs] 30/54 …` gibi satırlar yazar. Bitmesini bekle.

## 6. Buluttaki yanıtları geri yükle

```powershell
git pull
```

```powershell
uv run python -m pusula.evaluation.llm_runner restore
```

Ekranda `cache restored: … rows added` görmelisin. Daha önce alınmış kararlar `llm_state\e4_decisions.csv` dosyasında; program onları tekrar sormaz.

## 7. Kalan LLM çağrılarını başlat

```powershell
uv run python -m pusula.evaluation.llm_runner all
```

- Sıra şöyle: E4 P+R+S → E4 P → E5 (küçültülmüş) → E4 P+R+S anonim → E4 P+R.
- Ekranda `[e4] P+R+S: 150/540 (pace 10 RPM)` gibi satırlar görürsün.
- `'HTTP 429 …': pace 5 RPM, wait 60s` gibi satırlar **normaldir**: NVIDIA'nın ücretsiz katmanı yoğun, program kendiliğinden yavaşlar ve bekler.
- Her 100 yeni yanıtta ilerleme otomatik olarak GitHub'a gönderilir. **İlk gönderimde** bir pencere açılıp GitHub'a giriş yapmanı isteyebilir: giriş yap ve izin ver.
- Bilgisayarın uykuya geçmemesi için: Ayarlar → Sistem → Güç → "Uyku" süresini "Hiçbir zaman" yap (iş bitince geri al).

**Durdurmak için:** PowerShell penceresinde **Ctrl+C**.
**Devam etmek için:** aynı komutu (`uv run python -m pusula.evaluation.llm_runner all`) tekrar çalıştır. Biten çağrılar atlanır.

## 8. İş bitince

Ekranda `done at …` yazınca son durumu gönder:

```powershell
git push
```

Sonra Claude'a "LLM işleri bitti" de. Değerlendirme tabloları ve şekiller bulutta, gönderdiğin karar kaydından yeniden üretilir.

## Sık karşılaşılan sorunlar

| Sorun | Çözüm |
|---|---|
| `uv` tanınmıyor | PowerShell'i kapatıp yeniden aç; olmazsa 1. adımdaki kurulumu tekrarla |
| `git` tanınmıyor | Git'i kurduktan sonra PowerShell'i yeniden aç |
| `E4 input dates missing` | 5. adımdaki ikinci komutu çalıştır |
| `Could not set lock on file … pusula.duckdb` | Açık bir Streamlit arayüzü varsa kapat, komutu tekrar çalıştır |
| Uzun süre `wait 900s` görüyorum | NVIDIA tarafında kesinti var; program kendi kendine yeniden dener. İstersen Ctrl+C ile durdurup sonra devam et |
| `git push` hata veriyor | `git pull` çalıştır, sonra tekrar `git push` |
