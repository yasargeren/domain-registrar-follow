.PHONY: help venv install test status check dry-run alerts-test up down logs ps build stop-switch resume

help:
	@grep -E '^[a-zA-Z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-16s %s\n", $$1, $$2}'

venv:            ## .venv olustur
	python3 -m venv .venv && .venv/bin/pip install -U pip -r requirements.txt

install: venv    ## bagimliliklari kur

test:            ## testleri calistir (ag erisimi gerekmez)
	python3 -m unittest discover -s tests -v

status:          ## izlenen domainlerin son durumu
	python3 -m app.cli status

check:           ## tek seferlik canli sorgu:  make check DOMAIN=ornek.com
	python3 -m app.cli check $(DOMAIN)

dry-run:         ## registrar tarafinda kuru satin alma testi
	python3 -m app.cli dry-run $(DOMAIN)

alerts-test:     ## Telegram + e-posta kanallarini test et
	python3 -m app.cli test-alerts

build:           ## docker imajini kur
	docker compose build

up:              ## monitoru baslat
	docker compose up -d

down:            ## monitoru durdur
	docker compose down

ps:              ## konteyner durumu
	docker compose ps

logs:            ## canli log
	docker compose logs -f domain-monitor

stop-switch:     ## ACIL: tum kayit denemelerini durdur
	@mkdir -p data && date -u +%FT%TZ > data/STOP && echo "KILL SWITCH AKTIF -> data/STOP"

resume:          ## kill switch'i kaldir
	@rm -f data/STOP && echo "kill switch kaldirildi"
