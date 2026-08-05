#!/bin/sh
set -eu

: "${NOIZ_API_KEY:?NOIZ_API_KEY is required}"
export NOIZ_VOICE_ID="${NOIZ_VOICE_ID:-183203aa0}"
exec python3 /opt/puregamma-ai/voice_dialog.py "$@"
