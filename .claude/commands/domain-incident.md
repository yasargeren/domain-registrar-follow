---
description: "AVAILABLE alarmi geldiginde izlenecek acil aksiyon listesi"
argument-hint: [domain]
allowed-tools: Bash(python3 -m app.cli check:*), Bash(python3 -m app.cli attempts:*), Bash(python3 -m app.cli history:*)
---

# ACIL: $1 musait gorunuyor

!`python3 -m app.cli check $1`
!`python3 -m app.cli attempts $1 --limit 10`

## Gorev — sirayla dogrula ve raporla
1. Musaitlik gercek mi? Sorgu hatasi/rate-limit degil mi? (Inconclusive ise DUR.)
2. Domain `.com` mu `.com.tr` mi?
   - `.com`  : registrar (Porkbun) tarafinda `dry-run` ile dogrula, bakiye yeterli mi?
   - `.com.tr`: otomatik kayit YOK. Kullaniciyi akredite kayit kurulusu panelinden
     manuel kayda yonlendir; hangi bilgilerin hazir olmasi gerektigini listele
     (kimlik/vergi no, iletisim, NS kayitlari).
3. Kayit denemeleri tablosunda blocked satir varsa hangi kapi (G1..G8) engelledi?
4. Kullaniciya tek paragraf halinde "su an sunu yap" talimati ver.

Canli kaydi sen baslatma.
