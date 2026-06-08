#!/usr/bin/env bash
# install.sh — installe le daemon Kenbot comme LaunchAgent macOS
set -euo pipefail

REPO_DIR="${KENBOT_REPO_DIR:-$HOME/Desktop/kenbot-dashboard}"
DAEMON_DIR="$REPO_DIR/kenbot-daemon"
PLIST_SRC="$DAEMON_DIR/com.dgauto.kenbot-daemon.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.dgauto.kenbot-daemon.plist"

if [[ ! -f "$PLIST_SRC" ]]; then
    echo "❌ Plist source introuvable : $PLIST_SRC"
    exit 1
fi

echo "📋 Vérifie la configuration dans $PLIST_SRC :"
echo "    - KENBOT_DAEMON_TOKEN (change le secret par défaut !)"
echo "    - Paths absolus (Users/danielgiroux/...)"
read -r -p "Continuer ? [y/N] " ok
[[ "$ok" == "y" || "$ok" == "Y" ]] || exit 1

mkdir -p "$DAEMON_DIR/commands/inbox" "$DAEMON_DIR/commands/processing" "$DAEMON_DIR/commands/outbox" "$DAEMON_DIR/logs"
chmod +x "$DAEMON_DIR/kenbot_daemon.py"

# Décharge si déjà chargé
if launchctl list | grep -q com.dgauto.kenbot-daemon; then
    echo "↩️  Déchargement de l'ancienne version..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

cp "$PLIST_SRC" "$PLIST_DST"
launchctl load "$PLIST_DST"
echo "✅ Daemon chargé. Vérifie : tail -f $DAEMON_DIR/logs/daemon.log"
