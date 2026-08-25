---
description: Monitor loglarini incele ve anormallikleri cikar
allowed-tools: Bash(docker compose ps), Bash(docker compose logs:*), Bash(tail:*), Bash(grep:*)
---

# Log incelemesi

!`docker compose ps 2>/dev/null || echo "docker calismiyor / bu makinede degil"`

!`tail -n 120 logs/domain-monitor.log 2>/dev/null || echo "yerel log yok"`

## Gorev
- Tekrarlayan hata var mi? (RateLimited, Inconclusive, SMTP, Telegram)
- Poll araliklari beklenen davranista mi?
- nic.tr tarafinda limit yeme belirtisi var mi? Varsa WHOIS_TR_MIN_INTERVAL onerisi ver.
- Kritik bir durum degisikligi kacirilmis mi?
