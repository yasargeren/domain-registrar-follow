---
description: Registrar tarafinda kuru satin alma provasi (para harcamaz)
argument-hint: [domain]
allowed-tools: Bash(python3 -m app.cli dry-run:*), Bash(python3 -m app.cli ping)
---

# Kuru satin alma provasi: $1

Bu komut Porkbun `domain/create` endpoint'ini `dryRun: true` ile cagirir.
**Para harcamaz**, ama kimlik dogrulama, fiyat, bakiye ve musaitlik zincirinin
tamamini gercek API uzerinde test eder.

Once baglantiyi dogrula:
!`python3 -m app.cli ping`

Sonra provayi calistir:
!`python3 -m app.cli dry-run $1`

## Gorev
Sonucu degerlendir:
- `wouldSucceed` ve `sufficientFunds` degerleri ne?
- Bakiye yetersizse ne kadar yuklenmeli?
- Fiyat tavani (MAX_REGISTRATION_COST_USD) uygun mu?
- Canli kayda gecmeden once kalan eksikler neler?

Canli kayit komutunu (`app.cli register`) SEN calistirma; kullaniciya
terminalde elle calistirmasi icin ver.
