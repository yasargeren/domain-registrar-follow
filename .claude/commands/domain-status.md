---
description: Izlenen domainlerin guncel durumunu ve son olaylari ozetle
allowed-tools: Bash(python3 -m app.cli status), Bash(python3 -m app.cli history:*), Bash(python3 -m app.cli attempts:*), Bash(docker compose ps)
---

# Domain durum raporu

Asagidaki ciktilar uzerinden kisa bir operasyon raporu yaz.

## Kayitli durum
!`python3 -m app.cli status`

## Son olaylar
!`python3 -m app.cli history --limit 15`

## Kayit denemeleri
!`python3 -m app.cli attempts --limit 10`

## Gorev
Her domain icin tek satirda: durum, bitis tarihi, bir sonraki beklenen asama,
ve senin onerin (bekle / hazirlan / hemen aksiyon).
Sadece yukaridaki ciktilara dayan; tahmin uretme. Bir domain UNKNOWN ise veya
`last_error` doluysa bunu ilk siraya al ve olasi nedeni yaz.
