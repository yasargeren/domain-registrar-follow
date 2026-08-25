---
description: Telegram ve e-posta uyari kanallarini test et
allowed-tools: Bash(python3 -m app.cli test-alerts), Bash(python3 -m app.cli config)
---

# Uyari kanali testi

!`python3 -m app.cli config`

!`python3 -m app.cli test-alerts`

## Gorev
Hangi kanallar calisti, hangileri hata verdi? Hata varsa en olasi nedeni ve
duzeltmesini yaz (Gmail icin App Password gerekliligi, TELEGRAM_CHAT_ID'yi
almak icin once bota mesaj atma zorunlulugu, SMTP port 587/465 farki gibi).
`.env` dosyasinin icerigini OKUMA; sadece `app.cli config` ciktisindaki
maskelenmis ozeti kullan.
