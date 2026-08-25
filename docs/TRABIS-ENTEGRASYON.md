# .com.tr (TRABIS) entegrasyon rehberi

## Durum

- **Izleme:** calisiyor. `app/providers/whois_tr.py`, nic.tr WHOIS (port 43)
  sunucusunu `WHOIS_TR_MIN_INTERVAL` araligiyla sorgular, expire/created/registrar
  bilgisini cikarir, "No match" cevabini serbest kalma sinyali sayar.
- **Kayit:** otomatik degil. `app/providers/trabis.py` bilerek fail-closed.

## Neden fail-closed?

TRABIS registry'dir; son kullanici dogrudan registry'ye kayit yapamaz. Kayit,
akredite **kayit kurulusu** (Registration Organization) uzerinden yapilir ve her
kurulusun kendi API sozlesmesi vardir. Tek bir "genel .tr kayit API'si" yoktur.
Uydurma bir endpoint'e istek gondermek yerine adapter, sozlesme uygulanana kadar
hata verir ve kullaniciyi manuel kayda yonlendirir.

## Entegrasyon adimlari

1. **Kayit kurulusu secin.** TRABIS'in yayinladigi akredite kayit kuruluslari
   listesinden API destegi olan birini secin. Sorulacaklar:
   - REST/EPP API var mi, dokumantasyon paylasiliyor mu?
   - Sandbox/test ortami var mi?
   - Musaitlik sorgusu ve kayit icin ayri endpoint'ler ve rate limitleri neler?
   - Kayit icin hangi belgeler/kimlik bilgileri onceden tanimlanmali?
   - Odeme modeli: on odemeli bakiye mi, fatura mi?
2. **Sozlesme ve kimlik bilgilerini alin**, `.env` icine yazin:
   ```
   TRABIS_REGISTRAR_NAME=<kurulus adi>
   TRABIS_API_BASE_URL=https://...
   TRABIS_API_KEY=...
   TRABIS_API_SECRET=...
   ```
3. **`app/providers/trabis.py` icindeki dort fonksiyonu doldurun:**

   | Fonksiyon | Doner | Not |
   |---|---|---|
   | `lookup(domain)` | `LookupResult` | Opsiyonel; izleme WHOIS ile de calisir |
   | `available(domain)` | `bool` | Kayittan hemen once registrar tarafi dogrulama |
   | `register(domain, dry_run=True)` | `dict` | Sandbox varsa once orada test edin |
   | `owns(domain)` | `(bool, dict)` | Kayit sonrasi dogrulama |

   Hata durumlarinda `app/providers/base.py` icindeki `RateLimited`,
   `Inconclusive`, `NotConfigured`, `ProviderError` siniflarini kullanin —
   `acquire.py` bu siniflara gore davranir.

4. **Test edin.** `tests/` altina kurulus yanitlarindan turetilmis fixture'larla
   yeni bir test dosyasi ekleyin (`test_trabis.py`). Ag erisimi gerektirmesin.
5. **Sandbox -> canli.** Once sandbox'ta, sonra dusuk degerli bir test domainiyle
   deneyin. Ancak bundan sonra `TRABIS_ENABLED=true`.

## Yapilmayacaklar

- nic.tr veya kayit kurulusunun web formunu kazimak
- CAPTCHA/anti-bot mekanizmasini asmak
- Yetkisiz EPP baglantisi denemek
- WHOIS sunucusunu limitin uzerinde sorgulamak

Bunlarin hepsi kullanim sartlarina aykiridir ve hesap/IP engeline yol acar —
tam da domaine ihtiyaciniz olan anda.

## Manuel kayit hazirligi (otomasyon devreye girene kadar)

Domain serbest kaldiginda dakikalar onemlidir. Onceden hazir olsun:

- Kayit kurulusu panelinde acik ve dogrulanmis hesap
- Yeterli bakiye / odeme yontemi tanimli
- Kimlik / vergi numarasi, iletisim bilgileri kayitli
- NS kayitlari belirlenmis
- Telegram uyarisinin ulastigi telefonda panelin oturumu acik

`/domain-incident <domain>` slash komutu bu adimlari olay aninda hatirlatir.
