# domain-registrar-follow

🇹🇷 [Türkçe README](README.md)

Monitors the registrar/registry status of `ornek1.com.tr`, `ornek2.com.tr` and
`ornek.com` (domains currently registered to someone else), tracks their
lifecycle transitions (expiry → grace → redemption → pendingDelete → drop),
sends Telegram + email alerts on every critical transition, and drives the
registration process once a domain becomes free.

> **Important:** this repository is designed **fail-closed**. With default
> settings it never purchases anything. Live registration requires
> deliberately opening several independent safety gates (see "Safety gates"
> below).

## Contents

- [What it does / doesn't do](#what-it-does--doesnt-do)
- [Architecture](#architecture)
- [Setup — Docker (recommended)](#setup--docker-recommended)
- [Setup — bare server (no Docker / systemd)](#setup--bare-server-no-docker--systemd)
- [Configuration (.env)](#configuration-env)
- [Lifecycle and poll strategy](#lifecycle-and-poll-strategy)
- [Alert channels](#alert-channels)
- [Safety gates (G1-G8)](#safety-gates-g1-g8)
- [Go-live checklist](#go-live-checklist)
- [Operator commands](#operator-commands)
- [Troubleshooting](#troubleshooting)
- [Using it with Claude Code](#using-it-with-claude-code)
- [Legal / ethical note](#legal--ethical-note)

## What it does / doesn't do

| Does | Doesn't |
|---|---|
| Tracks EPP status for `.com` via Verisign RDAP | Never exceeds registry/registrar rate limits |
| Tracks `.com.tr` via TRABIS WHOIS (port 43) | Never scrapes web forms or bypasses CAPTCHA/anti-bot |
| Adaptive poll interval by state (15min / 5min / 1min) | Never calls a made-up API endpoint |
| Telegram + email + webhook alerts | Gives no drop-catch guarantee |
| Automatic `.com` registration via the Porkbun API | Never auto-registers `.com.tr` (requires an accredited Registration Organization) |
| Logs and verifies every registration attempt | Never attempts silently without checking balance/limits |

## Architecture

```
                 app/monitor.py  (24/7 loop, per-domain scheduler)
                        |
        +---------------+----------------+
        |                                |
 providers/rdap.py                providers/whois_tr.py
 (.com  - Verisign RDAP)          (.com.tr - TRABIS WHOIS port 43)
        |                                |
        +--------------> app/lifecycle.py (state machine)
                                |
                +---------------+----------------+
                |                                |
        app/notify/  (telegram, email, webhook)     app/acquire.py
                                                    (G1..G8 safety gates)
                                                            |
                                        providers/porkbun.py   providers/trabis.py
                                        (.com registration - LIVE)  (.com.tr - fail-closed)
```

State and history live in SQLite (`data/domains.db`) — `domains`, `events`,
`alerts`, `registration_attempts` tables.

## Setup — Docker (recommended)

Requirements: Docker + the Docker Compose plugin (`docker compose version`).

```bash
git clone <this-repo-url> domain-registrar-follow
cd domain-registrar-follow

cp .env.example .env && chmod 600 .env
$EDITOR .env                       # domains + alert channels + (optionally) registration settings

docker compose up -d --build       # builds the image, starts the container in the background
docker compose ps                  # should report "healthy" (after a ~20s start_period)
docker compose logs -f domain-monitor
```

One-off operator commands (same image, `cli` profile):

```bash
docker compose run --rm cli status
docker compose run --rm cli check ornek.com
docker compose run --rm cli check-all
docker compose run --rm cli test-alerts
docker compose run --rm cli dry-run ornek.com
```

Updating (after pulling new code):

```bash
git pull
docker compose up -d --build --force-recreate
```

Stopping:

```bash
docker compose down          # stops the container; data/ and logs/ stay on disk
```

`docker-compose.yml` uses `restart: unless-stopped` — if the host reboots, the
container comes back up automatically as long as the Docker daemon itself is
configured to start on boot (Docker Desktop / dockerd).

## Setup — bare server (no Docker / systemd)

Works directly with Python if you'd rather not use Docker.

```bash
git clone <this-repo-url> domain-registrar-follow
cd domain-registrar-follow

python3 -m venv .venv
.venv/bin/pip install -U pip -r requirements.txt

cp .env.example .env && chmod 600 .env
$EDITOR .env

.venv/bin/python -m unittest discover -s tests   # 44 tests, no network access needed
.venv/bin/python -m app.cli check-all             # first live lookup
.venv/bin/python -m app.cli test-alerts           # verify alert channels
```

systemd unit for running continuously (`/etc/systemd/system/domain-monitor.service`):

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
# .env is loaded automatically via python-dotenv; no extra EnvironmentFile needed.

# Hardening
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

Health check (optional, via cron):

```bash
*/5 * * * * /opt/domain-registrar-follow/.venv/bin/python -m app.healthcheck || echo "domain-monitor unhealthy" | mail -s "ALERT" you@example.com
```

### Docker + systemd on the host, for boot-time startup

`docker-compose.yml` already uses `restart: unless-stopped`. If the Docker
daemon itself doesn't start automatically on boot (or you'd rather manage
compose with its own unit):

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

## Configuration (.env)

Copy `.env.example` and fill it in (`cp .env.example .env && chmod 600 .env`).
Every value is documented with an inline comment in that file. Key groups:

| Group | Variables | Note |
|---|---|---|
| General | `DOMAINS`, `DB_PATH`, `LOG_PATH`, `TZ` | defaults are already set for these 3 domains |
| Poll intervals | `POLL_NORMAL_SECONDS`, `POLL_EXPIRING_SECONDS`, `POLL_CRITICAL_SECONDS` | picked automatically by state |
| `.com` monitoring | `RDAP_BASE_URL` | Verisign RDAP, no credentials needed |
| `.com.tr` monitoring | `WHOIS_TR_HOST=whois.trabis.gov.tr`, `WHOIS_TR_MIN_INTERVAL` | port 43, rate-limit friendly |
| Telegram | `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | details below |
| Email | `EMAIL_ENABLED`, `SMTP_*`, `EMAIL_TO` | details below |
| Registration safety | `AUTO_REGISTER`, `ACQUIRE_ALLOWLIST`, `MAX_REGISTRATION_COST_USD`, `KILL_SWITCH_FILE` | see Safety gates |
| Porkbun (.com) | `PORKBUN_ENABLED`, `PORKBUN_API_KEY`, `PORKBUN_SECRET_API_KEY` | see [docs/PORKBUN.md](docs/PORKBUN.md) |
| TRABIS (.com.tr) | `TRABIS_ENABLED`, ... | see [docs/TRABIS-ENTEGRASYON.md](docs/TRABIS-ENTEGRASYON.md) — fail-closed by default |

**`.env` is never committed** (it's in `.gitignore`); only `.env.example`
ships in git, and it contains no secrets.

### Setting up the Telegram channel

1. On Telegram, message [@BotFather](https://t.me/BotFather), send `/newbot`,
   create a bot — you get a **token**.
2. Send your new bot any message (so its chat shows up in the API).
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` (browser or curl);
   the `message.chat.id` field in the response is your `chat_id`.
4. `.env`:
   ```
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=<token>
   TELEGRAM_CHAT_ID=<chat_id>
   ```
5. To notify multiple people: create a Telegram group, add the bot and the
   people to it, and set `TELEGRAM_CHAT_ID` to the group's (negative) id.

### Setting up email (SMTP) — Gmail example

1. Your Gmail account needs 2FA (two-step verification) enabled.
2. Go to https://myaccount.google.com/apppasswords and create an **App
   Password** (not your regular Gmail password — a dedicated 16-character
   one).
3. `.env`:
   ```
   EMAIL_ENABLED=true
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USE_TLS=true
   SMTP_USERNAME=<your-gmail-address>
   SMTP_PASSWORD=<app-password>
   EMAIL_TO=recipient1@example.com,recipient2@example.com
   EMAIL_MIN_SEVERITY=WARNING     # only send email for WARNING/CRITICAL
   ```
   Add more recipients to `EMAIL_TO` as a comma-separated list.

## Lifecycle and poll strategy

```
ACTIVE ── 15 min
   │  expiry < 30 days away
EXPIRING ── 5 min
   │  expiry has passed
EXPIRED_GRACE ── 5 min          (.com: ~45-day auto-renew grace)
   │  redemptionPeriod
REDEMPTION ── 1 min             (.com: 30 days)
   │  pendingDelete
PENDING_DELETE ── 1 min         (.com: 5 days)
   │  drop
AVAILABLE ── 1 min + ALERT + (if AUTO_REGISTER) registration attempt
```

`UNKNOWN` is set when a lookup fails and is **never** interpreted as
availability; repeated failures raise a separate alert with exponential
backoff.

> **`.com.tr` limitation:** TRABIS does not expose the redemption/pendingDelete
> sub-phases separately in WHOIS — a domain is either "registered" or a "no
> match" answer. The realistic signal set for `.com.tr` is: ACTIVE/EXPIRING/
> EXPIRED_GRACE → AVAILABLE. For `.com`, the RDAP EPP status codes make every
> phase individually visible.

## Alert channels

| Channel | Setting | Note |
|---|---|---|
| Telegram | `TELEGRAM_ENABLED`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | see setup steps above |
| Email | `EMAIL_ENABLED`, `SMTP_*`, `EMAIL_TO` | Gmail requires an **App Password** (2FA must be on) |
| Webhook | `WEBHOOK_ENABLED`, `WEBHOOK_URL` | JSON POST for Slack/Teams/n8n/SIEM |

`EMAIL_MIN_SEVERITY` lets you restrict email to WARNING/CRITICAL only;
Telegram receives every severity. Repeats of the same alert are suppressed for
`ALERT_DEDUPE_SECONDS`; registration attempts are **never** suppressed.

## Safety gates (G1-G8)

Every registration attempt in `app/acquire.py` passes through these gates:

| Gate | Check | Setting |
|---|---|---|
| G1 | Domain is on the allowlist | `ACQUIRE_ALLOWLIST` |
| G2 | Kill-switch file is absent | `KILL_SWITCH_FILE` (`make stop-switch`) |
| G3 | Live registration is enabled | `AUTO_REGISTER` |
| G4 | Attempt budget for the time window isn't exhausted | `REGISTRATION_MAX_ATTEMPTS_PER_WINDOW` |
| G5 | Registrar adapter is configured | `PORKBUN_ENABLED` / `TRABIS_ENABLED` |
| G6 | Registrar-side availability confirmed | — (registry RDAP alone isn't enough) |
| G7 | Price cap not exceeded | `MAX_REGISTRATION_COST_USD` |
| G8 | `dryRun` rehearsal succeeded | `REGISTER_DRY_RUN_FIRST` |

Emergency stop:

```bash
make stop-switch     # creates data/STOP; all registration attempts halt
make resume          # removes it
```

## Go-live checklist

- [ ] `make test` is green
- [ ] `python3 -m app.cli check-all` returns the correct state for all three domains
- [ ] `python3 -m app.cli test-alerts` reached Telegram + email
- [ ] Monitored for at least 3-5 days with `AUTO_REGISTER=false`, logs are clean
- [ ] Porkbun account created, API access enabled **per domain**
- [ ] `python3 -m app.cli ping` succeeds (correct identity + IP)
- [ ] Sufficient **credit** loaded into the account (Porkbun's API doesn't charge a card, it draws from balance)
- [ ] `python3 -m app.cli dry-run ornek.com` → `wouldSucceed: true`, `sufficientFunds: true`
- [ ] `MAX_REGISTRATION_COST_USD` set to a sane cap
- [ ] `.env` permissions are 600, not committed to git
- [ ] Docker restart tested (`docker compose restart` preserves state)
- [ ] Server clock is NTP-synced
- [ ] `data/domains.db` is set up to be backed up
- [ ] Only after all of the above: `AUTO_REGISTER=true`

## Operator commands

```bash
make test                              # run all tests (no network access needed)
python3 -m app.cli status              # last recorded state of monitored domains
python3 -m app.cli check ornek.com  # live lookup
python3 -m app.cli check-all
python3 -m app.cli history --limit 20
python3 -m app.cli attempts
python3 -m app.cli config              # masked configuration summary
python3 -m app.cli test-alerts         # test alert channels
python3 -m app.cli dry-run ornek.com  # registrar-side rehearsal (spends nothing)
python3 -m app.cli stop / resume       # kill switch
docker compose up -d && docker compose logs -f domain-monitor
```

Slash commands (for Claude Code): `/domain-status`, `/domain-check`,
`/domain-dry-run`, `/domain-alerts-test`, `/domain-logs`, `/domain-deploy`,
`/domain-incident`. A read-only `domain-watch` subagent is also available for
analysis.

## Troubleshooting

**`.com.tr` lookups fail with "WHOIS connection failed" / a DNS error**
`whois.nic.tr` no longer exists — the registry moved to `whois.trabis.gov.tr`.
`.env.example` and `app/config.py` already default to the correct host; if you
have an older `.env`, update it to `WHOIS_TR_HOST=whois.trabis.gov.tr`.

**No alerts arrive**
Check `telegram_enabled` / `email_enabled` with `python3 -m app.cli config`,
then run `python3 -m app.cli test-alerts`.

**`nic.tr` / TRABIS rate-limit errors**
Don't lower `WHOIS_TR_MIN_INTERVAL`. If you want to poll more often, that's
the wrong knob — leave it alone; increasing query frequency against TRABIS is
not recommended.

## Using it with Claude Code

This repo is set up for Claude Code:

- `CLAUDE.md` — project rules and the safety invariants that must not be broken
- `.claude/commands/` — `/domain-status`, `/domain-check`, `/domain-dry-run`,
  `/domain-alerts-test`, `/domain-logs`, `/domain-deploy`, `/domain-incident`
- `.claude/agents/domain-watch.md` — read-only analysis subagent
- `.claude/hooks/guard-registration.sh` — a PreToolUse hook that blocks live
  registration, setting `AUTO_REGISTER=true`, deleting the kill switch, and
  reading `.env`
- `.claude/settings.json` — permission lists (`Read(./.env)` is denied)

## Further documentation

- [docs/OPERASYON.md](docs/OPERASYON.md) — day-to-day operations, incident response, troubleshooting (Turkish)
- [docs/TRABIS-ENTEGRASYON.md](docs/TRABIS-ENTEGRASYON.md) — `.com.tr` Registration Organization integration guide (Turkish)
- [docs/PORKBUN.md](docs/PORKBUN.md) — `.com` registrar setup and API notes (Turkish)

## Directory layout

```
app/
  config.py         env-based configuration (+ masked summary)
  monitor.py        24/7 loop, per-domain scheduler, heartbeat
  lifecycle.py      state machine, poll interval, drop estimate
  acquire.py        G1-G8 safety gates, registration + verification
  cli.py            operator commands
  db.py             SQLite (state, events, alert dedupe, attempts)
  healthcheck.py    container health probe
  notify/           telegram, email (SMTP), webhook
  providers/        rdap (.com), whois_tr (.com.tr), porkbun, trabis, registry
tests/              44 tests, no network access needed
.claude/            Claude Code commands, subagent, hook, permissions
```

## Legal / ethical note

- `.com.tr` registration happens through TRABIS-accredited Registration
  Organizations; this repository only **monitors** the TR side.
- When querying registry/registrar services, respect their published rate
  limits and terms of use. The default intervals are deliberately
  conservative.
- For a high-value `.com` domain, running a professional drop-catch/backorder
  service in parallel is recommended; this repository alone does not
  guarantee you'll catch it.

## License

No license file is included in this repository; confirm licensing terms with
the repository owner before use.
