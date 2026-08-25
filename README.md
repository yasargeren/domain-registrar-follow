# domain-registrar-follow

🇬🇧 [English README](README.en.md)

`ornek1.com.tr`, `ornek2.com.tr` ve `ornek.com` domainlerinin registrar/registry
durumunu 7/24 izler, yasam dongusu degisimlerinde (expiry → grace → redemption →
pendingDelete → drop) Telegram + e-posta uyarisi gonderir ve domain serbest
kaldiginda kayit surecini yurutur.

> **Onemli:** Bu depo *fail-closed* tasarlanmistir. Varsayilan ayarlarla hicbir
> satin alma yapmaz. Canli kayit icin bilincli olarak birden fazla guvenlik
> kapisinin acilmasi gerekir (asagida "Guvenlik kapilari").

## Icindekiler

- [Ne yapar / ne yapmaz](#ne-yapar--ne-yapmaz)
- [Mimari](#mimari)
- [Kurulum — Docker (onerilen)](#kurulum--docker-onerilen)
- [Kurulum — Sunucuda (Docker olmadan / systemd)](#kurulum--sunucuda-docker-olmadan--systemd)
- [Yapilandirma (.env)](#yapilandirma-env)
- [Yasam dongusu ve poll stratejisi](#yasam-dongusu-ve-poll-stratejisi)
- [Uyari kanallari](#uyari-kanallari)
- [Guvenlik kapilari (G1-G8)](#guvenlik-kapilari-g1-g8)
- [Canli kayda gecis (kontrol listesi)](#canli-kayda-gecis-kontrol-listesi)
- [Operasyon komutlari](#operasyon-komutlari)
- [Sorun giderme](#sorun-giderme)
- [Claude Code ile kullanim](#claude-code-ile-kullanim)
- [Yasal / etik not](#yasal--etik-not)

## Ne yapar / ne yapmaz

| Yapar | Yapmaz |
|---|---|
| `.com` icin Verisign RDAP ile EPP durum takibi | Registry/registrar limitlerini asmaz |
| `.com.tr` icin TRABIS WHOIS (port 43) takibi | Web formu kazimaz, CAPTCHA asmaz |
| Duruma gore degisen poll araligi (15dk / 5dk / 1dk) | Uydurma API endpoint'i cagirmaz |
| Telegram + e-posta + webhook uyarilari | Drop-catch garantisi vermez |
| `.com` icin Porkbun API ile otomatik kayit | `.com.tr` icin otomatik kayit yapmaz (akredite kayit kurulusu gerekir) |
| Her denemeyi kayit altina alir, dogrulama yapar | Bakiye/limit olmadan sessizce denemez |

## Mimari

```
                 app/monitor.py  (7/24 dongu, domain basina zamanlayici)
                        |
        +---------------+----------------+
        |                                |
 providers/rdap.py                providers/whois_tr.py
 (.com  - Verisign RDAP)          (.com.tr - TRABIS WHOIS port 43)
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

## Kurulum — Docker (onerilen)

Gereksinimler: Docker + Docker Compose plugin (`docker compose version`).

```bash
git clone <bu-repo-url> domain-registrar-follow
cd domain-registrar-follow

cp .env.example .env && chmod 600 .env
$EDITOR .env                       # domainler + uyari kanallari + (istersen) kayit ayarlari

docker compose up -d --build       # imaji kurar, konteyneri arka planda baslatir
docker compose ps                  # "healthy" olmali (ilk ~20sn start_period)
docker compose logs -f domain-monitor
```

Tek seferlik operasyon komutlari (ayni imaj, `cli` profili):

```bash
docker compose run --rm cli status
docker compose run --rm cli check ornek.com
docker compose run --rm cli check-all
docker compose run --rm cli test-alerts
docker compose run --rm cli dry-run ornek.com
```

Guncelleme (kod degisti):

```bash
git pull
docker compose up -d --build --force-recreate
```

Durdurma:

```bash
docker compose down          # konteyneri durdurur, data/ ve logs/ diskte kalir
```

`docker-compose.yml` `restart: unless-stopped` kullanir — host yeniden
baslarsa Docker daemon'i ile birlikte konteyner de otomatik ayaga kalkar
(Docker Desktop/daemon'in kendisi sistem baslangicinda calisacak sekilde
ayarli olmali).

## Kurulum — Sunucuda (Docker olmadan / systemd)

Docker kullanmak istemiyorsan dogrudan Python ile de calisir.

```bash
git clone <bu-repo-url> domain-registrar-follow
cd domain-registrar-follow

python3 -m venv .venv
.venv/bin/pip install -U pip -r requirements.txt

cp .env.example .env && chmod 600 .env
$EDITOR .env

.venv/bin/python -m unittest discover -s tests   # 44 test, ag erisimi gerekmez
.venv/bin/python -m app.cli check-all             # ilk canli sorgu
.venv/bin/python -m app.cli test-alerts           # uyari kanallarini dogrula
```

Surekli calismasi icin systemd birimi (`/etc/systemd/system/domain-monitor.service`):

```ini
[Unit]
Description=Domain Registrar Follow Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=domainmon
Group=domainmon
WorkingDirectory=/opt/domain-registrar-follow
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/domain-registrar-follow/.venv/bin/python -m app.monitor
Restart=on-failure
RestartSec=10
# .env dosyasi python-dotenv ile otomatik yuklenir; ekstra EnvironmentFile gerekmez.

# Zayiflatma
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/domain-registrar-follow/data /opt/domain-registrar-follow/logs
ProtectHome=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo useradd --system --home /opt/domain-registrar-follow --shell /usr/sbin/nologin domainmon
sudo cp -r . /opt/domain-registrar-follow
sudo chown -R domainmon:domainmon /opt/domain-registrar-follow
sudo chmod 600 /opt/domain-registrar-follow/.env

sudo systemctl daemon-reload
sudo systemctl enable --now domain-monitor
sudo systemctl status domain-monitor
journalctl -u domain-monitor -f
```

Saglik kontrolu (opsiyonel, cron ile):

```bash
*/5 * * * * /opt/domain-registrar-follow/.venv/bin/python -m app.healthcheck || echo "domain-monitor unhealthy" | mail -s "ALERT" you@example.com
```

### Docker + host'ta systemd ile otomatik baslatma

`docker-compose.yml` zaten `restart: unless-stopped` kullanir. Host acilisinda
Docker daemon'in kendisi otomatik baslamiyorsa (ya da compose'u ayrica bir
birimle yonetmek istersen):

```ini
# /etc/systemd/system/domain-acquisition.service
[Unit]
Description=Domain Acquisition Monitor
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/domain-registrar-follow
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
RemainAfterExit=yes
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload && sudo systemctl enable --now domain-acquisition
```

## Yapilandirma (.env)

`.env.example` dosyasini kopyalayip doldur (`cp .env.example .env && chmod 600 .env`).
Tum degerler icin aciklama dosyanin icinde satir yorumu olarak var. Onemli
basliklar:

| Grup | Degiskenler | Not |
|---|---|---|
| Genel | `DOMAINS`, `DB_PATH`, `LOG_PATH`, `TZ` | varsayilanlar bu 3 domain icin hazir |
| Poll araliklari | `POLL_NORMAL_SECONDS`, `POLL_EXPIRING_SECONDS`, `POLL_CRITICAL_SECONDS` | duruma gore otomatik secilir |
| .com izleme | `RDAP_BASE_URL` | Verisign RDAP, kimlik gerektirmez |
| .com.tr izleme | `WHOIS_TR_HOST=whois.trabis.gov.tr`, `WHOIS_TR_MIN_INTERVAL` | port 43, rate limit'e saygili |
| Telegram | `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | asagida detay |
| E-posta | `EMAIL_ENABLED`, `SMTP_*`, `EMAIL_TO` | asagida detay |
| Kayit guvenligi | `AUTO_REGISTER`, `ACQUIRE_ALLOWLIST`, `MAX_REGISTRATION_COST_USD`, `KILL_SWITCH_FILE` | bkz. Guvenlik kapilari |
| Porkbun (.com) | `PORKBUN_ENABLED`, `PORKBUN_API_KEY`, `PORKBUN_SECRET_API_KEY` | bkz. [docs/PORKBUN.md](docs/PORKBUN.md) |
| TRABIS (.com.tr) | `TRABIS_ENABLED`, ... | bkz. [docs/TRABIS-ENTEGRASYON.md](docs/TRABIS-ENTEGRASYON.md) — varsayilan fail-closed |

**`.env` asla commit edilmez** (`.gitignore` icinde), sadece `.env.example`
git'e girer ve secret icermez.

### Telegram kanali kurulumu

1. Telegram'da [@BotFather](https://t.me/BotFather)'a git, `/newbot` yaz, bot
   olustur → sana bir **token** verir.
2. Yeni botuna bir mesaj at (chat_id'nin API'ye dusmesi icin).
3. `https://api.telegram.org/bot<TOKEN>/getUpdates` adresini ac (tarayici veya
   curl), donen JSON'daki `message.chat.id` degeri senin `chat_id`'n.
4. `.env`:
   ```
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=<token>
   TELEGRAM_CHAT_ID=<chat_id>
   ```
5. Birden fazla kisiye gondermek icin: bir Telegram grubu ac, botu + kisileri
   gruba ekle, `TELEGRAM_CHAT_ID`'yi grubun (negatif) id'siyle degistir.

### E-posta (SMTP) kanali kurulumu — Gmail ornegi

1. Gmail hesabinda 2FA (iki adimli dogrulama) acik olmali.
2. https://myaccount.google.com/apppasswords → yeni **App Password** olustur
   (normal Gmail sifren degil, 16 haneli ozel sifre).
3. `.env`:
   ```
   EMAIL_ENABLED=true
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USE_TLS=true
   SMTP_USERNAME=<gmail-adresin>
   SMTP_PASSWORD=<app-password>
   EMAIL_TO=alici1@example.com,alici2@example.com
   EMAIL_MIN_SEVERITY=WARNING     # sadece WARNING/CRITICAL mail gonder
   ```
   Birden fazla aliciyi virgulle ayirarak `EMAIL_TO`'ya ekleyebilirsin.

## Yasam dongusu ve poll stratejisi

```
ACTIVE ── 15 dk
   │  bitis < 30 gun
EXPIRING ── 5 dk
   │  bitis gecti
EXPIRED_GRACE ── 5 dk          (.com: ~45 gun auto-renew grace)
   │  redemptionPeriod
REDEMPTION ── 1 dk             (.com: 30 gun)
   │  pendingDelete
PENDING_DELETE ── 1 dk         (.com: 5 gun)
   │  drop
AVAILABLE ── 1 dk + UYARI + (AUTO_REGISTER ise) kayit denemesi
```

`UNKNOWN` durumu sorgu basarisiz oldugunda olusur ve **asla** musaitlik olarak
yorumlanmaz; ust uste hata olursa ayri bir uyari gider ve ustel geri cekilme
uygulanir.

> **.com.tr icin kisit:** TRABIS, redemption/pendingDelete ara asamalarini
> WHOIS'te ayri ayri yayinlamiyor — domain sadece "kayitli" ya da "no match"
> olarak gorunuyor. `.com.tr` icin gercekci sinyal seti: ACTIVE/EXPIRING/
> EXPIRED_GRACE → AVAILABLE. `.com` icin RDAP'ten gelen EPP kodlari sayesinde
> tum asamalar ayri ayri gorunur.

## Uyari kanallari

| Kanal | Ayar | Not |
|---|---|---|
| Telegram | `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | yukaridaki kurulum adimlarina bak |
| E-posta | `EMAIL_ENABLED`, `SMTP_*`, `EMAIL_TO` | Gmail icin **App Password** gerekir (2FA acik olmali) |
| Webhook | `WEBHOOK_ENABLED`, `WEBHOOK_URL` | Slack/Teams/n8n/SIEM icin JSON POST |

`EMAIL_MIN_SEVERITY` ile e-postayi sadece WARNING/CRITICAL ile sinirlayabilirsiniz;
Telegram her seviyeyi alir. Ayni uyarinin tekrari `ALERT_DEDUPE_SECONDS` boyunca
bastirilir, kayit denemeleri ise **hicbir zaman** bastirilmaz.

## Guvenlik kapilari (G1-G8)

`app/acquire.py` icindeki her kayit denemesi su kapilardan gecer:

| Kapi | Kontrol | Ayar |
|---|---|---|
| G1 | Domain allowlist'te mi | `ACQUIRE_ALLOWLIST` |
| G2 | Kill-switch dosyasi yok mu | `KILL_SWITCH_FILE` (`make stop-switch`) |
| G3 | Canli kayit acik mi | `AUTO_REGISTER` |
| G4 | Zaman penceresindeki deneme butcesi | `REGISTRATION_MAX_ATTEMPTS_PER_WINDOW` |
| G5 | Registrar adapteri yapilandirilmis mi | `PORKBUN_ENABLED` / `TRABIS_ENABLED` |
| G6 | Registrar tarafinda musaitlik dogrulandi mi | — (RDAP tek basina yetmez) |
| G7 | Fiyat tavani asilmadi mi | `MAX_REGISTRATION_COST_USD` |
| G8 | `dryRun` provasi basarili mi | `REGISTER_DRY_RUN_FIRST` |

Acil durdurma:

```bash
make stop-switch     # data/STOP olusturur; tum kayit denemeleri durur
make resume          # geri acar
```

## Canli kayda gecis (kontrol listesi)

- [ ] `make test` yesil
- [ ] `python3 -m app.cli check-all` uc domain icin de dogru durumu donuyor
- [ ] `python3 -m app.cli test-alerts` Telegram + e-posta ulasti
- [ ] En az 3-5 gun `AUTO_REGISTER=false` ile izleme yapildi, log temiz
- [ ] Porkbun hesabi acildi, API erisimi **domain bazinda** etkinlestirildi
- [ ] `python3 -m app.cli ping` basarili (kimlik + IP dogru)
- [ ] Hesaba yeterli **kredi** yuklendi (Porkbun API kart cekmez, bakiyeden duser)
- [ ] `python3 -m app.cli dry-run ornek.com` → `wouldSucceed: true`, `sufficientFunds: true`
- [ ] `MAX_REGISTRATION_COST_USD` makul bir tavana ayarlandi
- [ ] `.env` izinleri 600, git'e girmedi
- [ ] Docker restart testi yapildi (`docker compose restart` sonrasi durum korunuyor)
- [ ] Sunucu saati NTP ile senkron
- [ ] `data/domains.db` yedegi alinacak sekilde ayarlandi
- [ ] Ancak bundan sonra: `AUTO_REGISTER=true`

## Operasyon komutlari

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

Slash komutlari (Claude Code icin): `/domain-status`, `/domain-check`,
`/domain-dry-run`, `/domain-alerts-test`, `/domain-logs`, `/domain-deploy`,
`/domain-incident`. Salt okunur analiz icin `domain-watch` subagent'i var.

## Sorun giderme

**`.com.tr` sorgulari "WHOIS connection failed" / DNS hatasi veriyor**
`whois.nic.tr` domaini artik yok — registry `whois.trabis.gov.tr`'ye tasindi.
`.env.example` ve `app/config.py` bu degeri zaten dogru default olarak
kullaniyor; eski bir `.env`'in varsa `WHOIS_TR_HOST=whois.trabis.gov.tr` olarak
guncelle.

**Alert gelmiyor**
`python3 -m app.cli config` ile `telegram_enabled` / `email_enabled` degerlerini
kontrol et, sonra `python3 -m app.cli test-alerts` calistir.

**`nic.tr` / TRABIS rate limit hatasi**
`WHOIS_TR_MIN_INTERVAL` degerini dusurme; sorgu sikligini artirmak istersen
`POLL_*` degerlerini degil bu degeri degistirmen gerekir ve onerilmez.

## Claude Code ile kullanim

Depo Claude Code icin hazirlanmistir:

- `CLAUDE.md` — proje kurallari ve degismez guvenlik sinirlari
- `.claude/commands/` — `/domain-status`, `/domain-check`, `/domain-dry-run`,
  `/domain-alerts-test`, `/domain-logs`, `/domain-deploy`, `/domain-incident`
- `.claude/agents/domain-watch.md` — salt okunur analiz subagent'i
- `.claude/hooks/guard-registration.sh` — canli kayit, `AUTO_REGISTER=true`,
  kill-switch silme ve `.env` okuma girisimlerini engelleyen PreToolUse hook'u
- `.claude/settings.json` — izin listeleri (`Read(./.env)` reddedilir)

## Detayli dokumanlar

- [docs/OPERASYON.md](docs/OPERASYON.md) — gunluk operasyon, olay mudahale, sorun giderme
- [docs/TRABIS-ENTEGRASYON.md](docs/TRABIS-ENTEGRASYON.md) — `.com.tr` kayit kurulusu entegrasyon rehberi
- [docs/PORKBUN.md](docs/PORKBUN.md) — `.com` registrar kurulumu ve API notlari

## Dizin yapisi

```
app/
  config.py         env tabanli yapilandirma (+ maskelenmis ozet)
  monitor.py        7/24 dongu, domain basina zamanlayici, heartbeat
  lifecycle.py      durum makinesi, poll araligi, drop tahmini
  acquire.py        G1-G8 guvenlik kapilari, kayit + dogrulama
  cli.py            operator komutlari
  db.py             SQLite (durum, olaylar, uyari dedupe, denemeler)
  healthcheck.py    konteyner saglik probu
  notify/           telegram, e-posta (SMTP), webhook
  providers/        rdap (.com), whois_tr (.com.tr), porkbun, trabis, registry
tests/              44 test, ag erisimi gerekmez
.claude/            Claude Code komutlari, subagent, hook, izinler
```

## Yasal / etik not

- `.com.tr` kaydi TRABIS akredite kayit kuruluslari uzerinden yapilir; bu depo
  TR tarafinda yalnizca **izleme** yapar.
- Registry/registrar servislerine sorgu yaparken yayinlanan limitlere ve
  kullanim sartlarina uyun. Varsayilan araliklar bilinerek muhafazakardir.
- Yuksek degerli bir `.com` domain icin profesyonel drop-catch/backorder
  servisleriyle paralel calismak gerekir; bu depo tek basina yakalama garantisi
  vermez.

## Lisans

Bu depo icin bir lisans dosyasi eklenmemistir; kullanmadan once repo sahibiyle
lisans kosullarini teyit edin.
