# Operasyon el kitabi

## Gunluk rutin

| Sıklık | Is | Komut |
|---|---|---|
| Gunluk | Heartbeat mesaji geldi mi? | Telegram/e-posta kutusu |
| Gunluk | Durum ozeti | `python3 -m app.cli status` veya `/domain-status` |
| Haftalik | Log taramasi | `/domain-logs` |
| Haftalik | DB yedegi | `sqlite3 data/domains.db ".backup data/backup-$(date +%F).db"` |
| Aylik | Registrar bakiyesi ve API anahtari gecerliligi | `python3 -m app.cli ping` |
| Kritik donemde (redemption/pendingDelete) | Gunde birkac kez kontrol | `/domain-check <domain>` |

## Olay mudahale: "DOMAIN MUSAIT" uyarisi geldi

1. **Dogrula.** `python3 -m app.cli check <domain>`
   Sonuc `Inconclusive`/`RateLimited` ise DUR — bu musaitlik degil.
2. **`.com` ise:**
   - `python3 -m app.cli dry-run ornek.com`
   - `wouldSucceed: true` ve `sufficientFunds: true` ise:
     `python3 -m app.cli register ornek.com` (elle, terminalde)
   - Bakiye yetersizse once Porkbun hesabina kredi yukleyin — API kart cekmez.
3. **`.com.tr` ise:** otomatik kayit yoktur. Akredite kayit kurulusunun paneline
   girip kaydi hemen yapin. Hazir bulundurun: kimlik/vergi numarasi, iletisim
   bilgileri, belge gerekiyorsa ilgili evrak, NS kayitlari.
4. Kayit sonrasi: `python3 -m app.cli check <domain>` ile registrar ve NS
   bilgilerini dogrulayin; `AUTO_REGISTER=false` yapip izlemeyi surdurun.

## Sorun giderme

| Belirti | Olasi neden | Cozum |
|---|---|---|
| `RateLimited: nic.tr refused the query` | nic.tr sorgu limiti | `WHOIS_TR_MIN_INTERVAL` degerini 120-300'e cikarin |
| `.com.tr` icin `Inconclusive: WHOIS answer could not be parsed` | nic.tr cikti formati degismis | Ham ciktiyi alin, `tests/fixtures/` altina ekleyin, `whois_tr.parse` guncelleyin |
| Telegram mesaji gelmiyor | Bot ile hic konusulmamis / chat id yanlis | Bota `/start` yazin, `getUpdates` ile chat id'yi tekrar alin |
| SMTP `535 Username and Password not accepted` | Normal sifre kullanilmis | Gmail App Password olusturun (2FA sart) |
| `porkbun: Invalid API key` | Anahtar yanlis veya domain bazinda API erisimi kapali | Porkbun panelinden API Access'i acin, `app.cli ping` ile dogrulayin |
| Konteyner `unhealthy` | Dongu takildi veya DB yazilamiyor | `docker compose logs`, `data/` izinleri, disk doluluk |
| Durum `UNKNOWN` kalmis | Ust uste sorgu hatasi | `/domain-logs`, ag/DNS erisimi, provider degisikligi |

## Yedekleme ve tasima

```bash
# yedek
tar czf domain-follow-backup-$(date +%F).tgz data/ .env

# yeni sunucuya tasima
scp domain-follow-backup-*.tgz sunucu:/opt/
# hedefte: tar xzf ..., chmod 600 .env, docker compose up -d
```

`data/domains.db` tum gecmisi (olaylar, kayit denemeleri) tutar; kaybederseniz
izleme calismaya devam eder ama gecmis ve uyari dedupe durumu sifirlanir.

## Guvenlik notlari

- `.env` dosyasi 600 izinle, git disinda tutulur. Icinde Telegram token'i,
  SMTP sifresi ve registrar API anahtari bulunur.
- Registrar hesabinda yalnizca gerekli minimum kredi bulundurun.
- Porkbun'da API erisimini sadece ilgili domainler icin acin, mumkunse
  IP kisitlamasi uygulayin.
- Uretim sunucusunda `.env` yerine Docker secrets veya bir secret manager
  kullanmak daha iyidir.
- Log dosyalarina sir yazilmaz; yine de `logs/` dizinini paylasmadan once kontrol edin.
