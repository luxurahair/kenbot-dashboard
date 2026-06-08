#!/usr/bin/env bash
# uninstall.sh — décharge le daemon Kenbot
set -euo pipefail
PLIST_DST="$HOME/Library/LaunchAgents/com.dgauto.kenbot-daemon.plist"
launchctl unload "$PLIST_DST" 2>/dev/null || true
rm -f "$PLIST_DST"
echo "✅ Daemon Kenbot déchargé. (Fichiers du daemon conservés dans kenbot-daemon/)"
