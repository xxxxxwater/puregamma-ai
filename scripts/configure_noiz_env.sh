#!/bin/sh
set -eu

IFS= read -r noiz_key
[ -n "$noiz_key" ] || { echo "missing key" >&2; exit 1; }

cd /opt/puregamma-ai
tmp="$(mktemp /opt/puregamma-ai/.env.noiz.XXXXXX)"
trap 'rm -f "$tmp"' EXIT
grep -v '^NOIZ_API_KEY=' .env | grep -v '^NOIZ_VOICE_ID=' > "$tmp"
printf 'NOIZ_API_KEY=%s\nNOIZ_VOICE_ID=183203aa0\n' "$noiz_key" >> "$tmp"
chmod --reference=.env "$tmp"
chown --reference=.env "$tmp"
mv "$tmp" .env
trap - EXIT
echo "Noiz environment configured"
