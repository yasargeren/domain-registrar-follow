---
description: Bir domain icin canli registry sorgusu yap ve yorumla
argument-hint: [domain]
allowed-tools: Bash(python3 -m app.cli check:*), Bash(python3 -m app.cli check-all)
---

# Canli sorgu: $1

!`python3 -m app.cli check $1`

## Gorev
Ciktiyi yorumla:
- Domain hangi yasam dongusu asamasinda?
- .com ise: EPP status kodlari ne anlama geliyor (redemptionPeriod, pendingDelete, clientHold...)?
- Tahmini drop tarihi varsa bunun bir **tahmin** oldugunu belirt.
- Su an yapilmasi gereken somut adim ne?

Sorgu hata verdiyse (RateLimited / Inconclusive) bunun "domain musait" anlamina
GELMEDIGINI acikca yaz.
