#!/usr/bin/env bash
set -euo pipefail

PLIST="$HOME/Library/LaunchAgents/ai.puregamma.imessage-relay.plist"
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>ai.puregamma.imessage-relay</string>
  <key>ProgramArguments</key>
  <array>
    <string>uvicorn</string>
    <string>relay:app</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>8787</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
PLIST

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Installed $PLIST"
