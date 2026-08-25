---
description: Sunucuya kurulum/guncelleme adimlarini yurut (dogrulamali)
allowed-tools: Bash(docker compose build), Bash(docker compose ps), Bash(docker compose logs:*), Bash(make test), Bash(git status), Bash(git diff:*)
---

# Kurulum / guncelleme

Sirayla:
1. `make test` ile testleri calistir; kirmizi test varsa DEVAM ETME.
2. `git status` ile commit edilmemis degisiklikleri goster.
3. `.env` var mi kontrol et (icerigini okumadan: `test -f .env && echo var`).
4. `docker compose build`
5. Kullaniciya `docker compose up -d` komutunu ver (baslatmayi sen yapma,
   onay iste).
6. Baslatildiktan sonra `docker compose ps` ve ilk 30 satir logla saglik dogrula.

Her adimda ciktilari ozetle ve bir sonrakine gecmeden once sorun olup olmadigini soyle.
