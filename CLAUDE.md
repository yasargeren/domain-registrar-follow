# CLAUDE.md — domain-registrar-follow

Bu dosya Claude Code'un bu depoda nasil calisacagini tanimlar. Kod degisikligi
yapmadan once bu kurallari oku.

## Proje amaci

Baskasinin uzerine kayitli uc domainin registrar/registry durumunu 7/24 izlemek,
yasam dongusu asamalarini (expiry -> grace -> redemption -> pendingDelete -> drop)
takip etmek, her kritik gecişte Telegram + e-posta uyarisi gondermek ve domain
serbest kaldiginda kaydi gerceklestirmek.

Izlenen domainler: `ornek1.com.tr`, `ornek2.com.tr`, `ornek.com`

## Mimari (kisa)

```
                 app/monitor.py  (7/24 dongu, domain basina zamanlayici)
                        |
        +---------------+----------------+
        |                                |
 providers/rdap.py                providers/whois_tr.py
 (.com  - Verisign RDAP)          (.com.tr - nic.tr WHOIS port 43)
        |                                |
        +--------------> app/lifecycle.py (durum makinesi)
                                |
                +---------------+----------------+
                |                                |
        app/notify/  (telegram, e-posta, webhook)   app/acquire.py
                                                    (G1..G8 guvenlik kapilari)
                                                            |
                                        providers/porkbun.py   providers/trabis.py
                                        (.com kayit - CANLI)   (.com.tr - fail-closed)
```

Durum ve gecmis: SQLite (`data/domains.db`) — `domains`, `events`, `alerts`,
`registration_attempts` tablolari.

## Degismez kurallar (ihlal etme)

1. **Para harcayan komutu sen calistirma.** `python -m app.cli register ...`,
   `domain/create` cagrisi, `AUTO_REGISTER=true` yapma — hepsi kullanicinin isi.
   Bunlari `.claude/hooks/guard-registration.sh` zaten engeller; hook'u atlatmaya
   calisma. Gerekirse komutu yaz ve kullanicidan terminalde calistirmasini iste.
2. **`.env` icerigini okuma, yazdirma, loglama.** Yapilandirmayi gormek icin
   `python3 -m app.cli config` (maskelenmis ozet) kullan.
3. **Belirsizlik musaitlik degildir.** `RateLimited` / `Inconclusive` durumunda
   domain ASLA "available" sayilmaz. Yeni kod yazarken de bu kurali koru:
   musaitlik yalnizca acik sinyalle (RDAP 404 / WHOIS "No match") belirlenir.
4. **API uydurma.** Bir registrar endpoint'ini dokumantasyonla dogrulamadan
   yazma. TRABIS adapteri bilerek fail-closed; akredite kayit kurulusunun resmi
   API sozlesmesi olmadan doldurma.
5. **Scraping yok.** nic.tr/TRABIS web formlarini kazima, CAPTCHA/anti-bot
   mekanizmasini asma girisimi yapma. Sadece port-43 WHOIS ve resmi API'ler.
6. **Rate limit'e saygi.** nic.tr icin `WHOIS_TR_MIN_INTERVAL` (varsayilan 60s),
   Porkbun checkDomain icin 10s alt siniri dusurme.
7. **Guvenlik kapilarini zayiflatma.** `app/acquire.py` icindeki G1..G8
   kontrolleri urunun en kritik kodu. Degistirirsen `tests/test_acquire_guards.py`
   testlerini de guncelle ve calistir.

## Sik kullanilan komutlar

```bash
make test                              # tum testler (ag erisimi gerekmez)
python3 -m app.cli status              # kayitli son durum
python3 -m app.cli check ornek.com  # canli sorgu
python3 -m app.cli check-all
python3 -m app.cli history --limit 20
python3 -m app.cli attempts
python3 -m app.cli config              # maskelenmis yapilandirma
python3 -m app.cli test-alerts         # uyari kanallari testi
python3 -m app.cli dry-run ornek.com  # registrar provasi (para harcamaz)
python3 -m app.cli stop / resume       # kill-switch
docker compose up -d && docker compose logs -f domain-monitor
```

Slash komutlari: `/domain-status`, `/domain-check`, `/domain-dry-run`,
`/domain-alerts-test`, `/domain-logs`, `/domain-deploy`, `/domain-incident`.
Salt okunur analiz icin `domain-watch` subagent'i var.

## Kod standartlari

- Python 3.10+ ile uyumlu kal (uretim imaji 3.12).
- Dis bagimlilik eklemekten kacin; su an sadece `requests` + `python-dotenv`.
  Testler stdlib `unittest` ile calisir, ag erisimi gerektirmez.
- Yeni bir provider eklerken `app/providers/base.py` icindeki `LookupResult`
  sozlesmesine uy ve hata sinifi olarak `RateLimited` / `Inconclusive` /
  `NotConfigured` kullan.
- Yapilandirma degeri okurken fonksiyon icinde `config.X` seklinde eris
  (import zamaninda sabitleme; test edilebilirligi bozuyor).
- Log ve kullanici mesajlari Turkce, kod/dokumantasyon yorumlari Ingilizce.
- Sir iceren degeri asla logging'e verme.

## Degisiklik yaptiktan sonra

1. `make test` — hepsi yesil olmali.
2. Provider parser'i degistiysen `tests/fixtures/` altina gercek ciktidan
   turetilmis yeni bir fixture ekle.
3. Guvenlik kapisi degistiyse README'deki kontrol listesini de guncelle.

## Bilinmesi gereken alan bilgisi

- `.com` drop takvimi: bitis -> ~45 gun auto-renew grace -> 30 gun redemption
  -> 5 gun pendingDelete -> drop. `app/lifecycle.estimated_drop_window()` bunu
  hesaplar ama **tahmindir**; registrar politikasina gore kayar.
- Yuksek degerli bir `.com` icin tek registrar denemesi genelde yetmez; profesyonel
  drop-catch/backorder servisi paralel kullanilmalidir. Bu depo onun yerine gecmez.
- `.com.tr` TRABIS tarafinda kayit yalnizca akredite kayit kurulusu uzerinden
  yapilir; bu depo TR tarafinda **izleme** yapar, kaydi kullanici baslatir.
