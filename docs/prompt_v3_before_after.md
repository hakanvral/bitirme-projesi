# Prompt v3: before / after (THYAO and ENJSA, full mode, 2026-11-20)

Same inputs, same model (Nemotron 3 Ultra), v2 prompts vs v3 prompts (D-065). Generated from the
saved runs in `results/analysis_runs/20261120/`. The v3 runs were made after the context-aware
numeric check, the RSI zone/threshold inputs and `max_tokens` = 16384 (D-068) were in place.

## Checks

| Check | THYAO v2 | THYAO v3 | ENJSA v2 | ENJSA v3 |
|---|---|---|---|---|
| Faktör duyarlılığı 'beta' diye anılıyor | 3 | 0 | 1 | 0 |
| Yazım hatası: 'alınısa' | 0 | 0 | 1 | 0 |
| Yazım hatası: 'hissedenden' | 1 | 0 | 0 | 0 |
| ASCII / eksik harf ('sok', 'asiri' …) | 0 | 0 | 0 | 3 |
| RSI 70 eşiği (girdide yoktu → v3'te girdide var) | 2 | 1 | 0 | 0 |
| `temel_riskler` items that are not sentences | 0 | 0 | 1 | 0 |
| Numeric audit (numbers checked / not found) | 171 / 0 | 165 / 0 | 181 / 0 | 213 / 0 |
| Consistency check | OK | OK | OK | OK |
| Regenerated reports | risk_analyst:numeric, bull:numeric, judge:numeric | – | scenario_analyst:consistency, bull:consistency, bear:consistency, judge:consistency | – |
| Decision (güven) | BEKLE (0.4) | BEKLE (0.45) | BEKLE (0.35) | BEKLE (0.4) |

Re-auditing the v2 THYAO reports with the v3 numeric check flags 'RSI 70' as a number that was
not in the input (it was accepted before by coincidence). In v3 the input contains `rsi14_bolgesi`
and `rsi_esikleri` (70/30), so citing 70 is now traceable.

Remaining issue found in the ENJSA v3 run: 'aşırı sok' (should be 'aşırı şok'). The model copied the
ASCII input key `asiri_sok_tum_orneklem_kullanildi`; the key was renamed to
`tum_orneklem_kovaryansi_kullanildi` before the experiments (E4/E5 use the renamed key).

## THYAO v2: `temel_riskler` and `karari_degistirecek_kosullar`

**temel_riskler**

- Piyasa riski: Beta 0,98 ile XU100 ile neredeyse aynı yönde hareket.
- Kur riski: USD/TRY haftalık 1 standart sapma hareketinde getiri %0,66 değişiyor.
- Ülke riski (CDS): CDS 5Y haftalık 1 standart sapma artışında getiri %1,69 düşüyor.
- Faiz riski: 2 yıllık tahvil faizi haftalık 1 standart sapma artışında getiri %0,59 düşüyor.
- Çekilme riski: 3 aylık kötü senaryoda (p95) azami düşüş %29,65.

**karari_degistirecek_kosullar**

- Petrol fiyatlarında ciddi bir düşüş (Brent -%30) gerçekleşirse pozitif etki beklenir.
- Sert faiz indirimi (-750 bp) gerçekleşirse getiri pozitif, risk metrikleri iyileşir.
- Ülke riski (CDS) artışı (+200 bp) devam ederse ciddi kayıp riski oluşur.
- Kur şoku (USD/TRY +%15) gibi aşırı hareketler modelin öngörülerini bozabilir (veri kısıtı).
- Teknik düzeltme (RSI 70 altına düşüş, fiyat 50 günlük ortalama altına çekilme) alım fırsatı yaratabilir.

## THYAO v3: `temel_riskler` and `karari_degistirecek_kosullar`

**temel_riskler**

- CDS (5Y) risk priminde +200 baz puanlık artış senaryosunda hisse TL bazında %17,02 kayıp verebilir, VaR %99 ve zarar olasılığı sert şekilde artabilir.
- Brent petrol fiyatında +%30 şoku durumunda hisse zarar görürken (TL getirisi −%2,08), enerji endeksi kazanç sağlamakta; bu ters yönlü etki beklenmedik kayıplara yol açabilir.
- RSI 74 ile aşırı alım bölgesinde bulunma ve fiyatın hareketli ortalamaların çok üzerinde seyretmesi, kısa vadeli bir teknik düzeltme riskini beraberinde getirir.
- Makro modelin düşük açıklama gücü (R²=0,15) ve kur şoku (USD/TRY +%15) senaryosunun mevcut rejim dışında olması, senaryo tahminlerinin belirsizliğini artırır.
- Yıllık oynaklık %32,58 ve 3 aylık medyan azami düşüş %14,35 (kötü senaryoda %29,65) ciddi aşağı yönlü fiyat dalgalanması riskini gösterir.

**karari_degistirecek_kosullar**

- RSI 14 değeri 70'in altına düşerse (aşırı alım bölgesinden çıkarsa).
- CDS (5Y) risk primi belirgin şekilde azalırsa (ülke riski senaryosunun etkisi zayıflarsa).
- Brent petrol fiyatında %30'luk bir düşüş (Brent −%30 senaryosu) gerçekleşirse.
- Sert faiz indirimi (−750 bp) senaryosu gerçekleşirse.
- Makro modelin açıklama gücü (R²) artarsa veya veri kısıtlamaları (kur şoku rejim dışı olması, düşük açıklama gücü) kalkarsa.

## ENJSA v2: `temel_riskler` and `karari_degistirecek_kosullar`

**temel_riskler**

- Ülke riski (CDS) artışı
- Faiz artırımı
- Küresel risk algısı (VIX) artışı
- Yüksek oynaklık ve büyük azami düşüş potansiyeli
- Model belirsizliği (düşük R², PTF verisi yok, aşırı kur şoku)

**karari_degistirecek_kosullar**

- CDS spread'lerinin kalıcı olarak düşmesi (ülke riski iyileşmesi)
- Faiz indirimi sinyalleri güçlenmesi ve piyasa fiyatlamasına yansıması
- Teknik göstergelerin dönmesi: fiyat 50 günlük ortalamanın üzerine çıkması, RSI 50'nin üzerine yükselmesi
- Makro modelin açıklama gücünün artması veya elektrik piyasa fiyatı (PTF) verisinin modele entegre edilmesi
- Oynaklığın %30'un altına inmesi ve azami düşüş riskinin azalması

## ENJSA v3: `temel_riskler` and `karari_degistirecek_kosullar`

**temel_riskler**

- Ülke riski (CDS) artışı senaryosunda ciddi getiri kaybı ve risk artışı yaşanabilir.
- Faiz artırımı senaryosunda getiri düşüşü ve zarar olasılığı artışı olabilir.
- Küresel risk-off (VIX) ortamında hisse negatif etkilenecek.
- Makro modelin düşük açıklama gücü (R²=%10) ve PTF verisi eksikliği nedeniyle gerçek riskler tam yansıtılmamış olabilir.
- Kur şoku senaryosu mevcut rejim deneyiminin çok dışında (aşırı sok), tahminler güvenilir olmayabilir.

**karari_degistirecek_kosullar**

- CDS riski belirgin azalırsa (CDS +200 bp senaryosu riski düşerse).
- Faiz indirimi beklentileri güçlenirse (sert faiz indirimi senaryosu daha olası hale gelirse).
- Kısa vadeli trend göstergeleri iyileşirse (fiyat 50 günlük ortalama üstüne çıkarsa, momentum artarsa).
- Elektrik piyasa fiyatı (PTF) verisi modele entegre edilirse ve risk profili değişirse.
- Makro model açıklama gücü (R²) belirgin artarsa.
