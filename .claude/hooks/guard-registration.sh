#!/usr/bin/env bash
# PreToolUse guard: para harcayan veya guvenlik ayarini gevseten komutlari engeller.
# Claude Code hook sozlesmesi: stdin'den JSON gelir, exit 2 = komutu engelle.
set -uo pipefail

INPUT="$(cat)"

CMD="$(printf '%s' "$INPUT" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("")
    sys.exit(0)
ti = data.get("tool_input") or {}
print(ti.get("command") or ti.get("file_path") or "")
' 2>/dev/null)"

[ -z "$CMD" ] && exit 0

block() {
  echo "ENGELLENDI: $1" >&2
  echo "" >&2
  echo "Bu islem gercek para harcayabilir veya guvenlik kapisini gevsetir." >&2
  echo "Kullanicidan acik onay alin ve komutu terminalde ELLE calistirin." >&2
  exit 2
}

# 1) canli kayit komutlari
echo "$CMD" | grep -Eq 'app\.cli[[:space:]]+register' && \
  block "canli domain kaydi (app.cli register)"

echo "$CMD" | grep -Eq 'domain/create' && \
  block "registrar create endpoint'ine dogrudan istek"

# 2) guvenlik kapisini acan degisiklikler
echo "$CMD" | grep -Eqi 'AUTO_REGISTER[[:space:]]*=[[:space:]]*(true|1|yes|on)' && \
  block "AUTO_REGISTER acilmaya calisiliyor"

echo "$CMD" | grep -Eq 'acquisition|--profile[[:space:]]+acquire' && \
  block "acquisition profili baslatiliyor"

# 3) kill-switch'i kaldirma
echo "$CMD" | grep -Eq '(rm|unlink).*(data/STOP)' && \
  block "kill-switch dosyasi siliniyor (data/STOP)"

# 4) .env icerigini okuma/yazma (sir sizintisi)
echo "$CMD" | grep -Eq '(cat|less|more|head|tail|bat|strings)[[:space:]]+([^|]*[[:space:]])?\.env([[:space:]]|$)' && \
  block ".env dosyasi okunuyor (icinde API anahtarlari var)"

exit 0
