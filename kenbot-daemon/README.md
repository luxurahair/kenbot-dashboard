# 🛡️ Kenbot Daemon V2 — Local Mac Agent

Comme un mini-Emergent qui tourne sur **ton Mac**, avec 3 boucles concurrentes :

| Loop          | Rôle                                                          |
|---------------|---------------------------------------------------------------|
| 📥 **queue**     | Exécute les JSON drop dans `commands/inbox/`                  |
| 🛡️ **watchdog**  | Snapshot env vars + **auto-restore** si vars critiques perdues |
| 🌐 **http**      | Webhook localhost:7777 (POST /cmd, GET /status)               |

## Installation

```bash
cd ~/Desktop/kenbot-dashboard
# 1. Édite kenbot-daemon/com.dgauto.kenbot-daemon.plist
#    → change KENBOT_DAEMON_TOKEN (un secret pour ton webhook)
# 2. Installe :
bash kenbot-daemon/install.sh
# 3. Vérifie :
tail -f kenbot-daemon/logs/daemon.log
```

## Désinstaller

```bash
bash kenbot-daemon/uninstall.sh
```

## Utilisation #1 — Par fichier JSON (le plus simple)

```bash
# Restart un service
cat > kenbot-daemon/commands/inbox/restart-runner.json <<EOF
{"action": "restart", "service": "kenbot-runner"}
EOF

# Attends 10s puis lis le résultat :
cat kenbot-daemon/commands/outbox/result_restart-runner.json
```

## Utilisation #2 — Par webhook HTTP (depuis iPhone Shortcuts, Siri, curl…)

```bash
TOKEN="<celui du plist>"

# Redémarrer
curl -X POST http://localhost:7777/cmd \
  -H "X-Daemon-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"restart","service":"kenbot-runner"}'

# Set env var
curl -X POST http://localhost:7777/cmd \
  -H "X-Daemon-Token: $TOKEN" \
  -d '{"action":"env-set","service":"kenbot-runner","key":"MY_KEY","value":"123"}'

# Snapshot
curl -X POST http://localhost:7777/cmd \
  -H "X-Daemon-Token: $TOKEN" \
  -d '{"action":"snapshot","project":"all"}'

# Status du daemon
curl -H "X-Daemon-Token: $TOKEN" http://localhost:7777/status

# Healthcheck (pas d'auth)
curl http://localhost:7777/health
```

## Actions supportées

| Action       | Payload                                                        |
|--------------|----------------------------------------------------------------|
| `restart`    | `{action, service}`                                            |
| `env-set`    | `{action, service, key, value}`                                |
| `env-list`   | `{action, service}`                                            |
| `snapshot`   | `{action, project: "kenbot\|luxura\|calcauto\|all"}`           |
| `kenbotctl`  | `{action, args: ["env-set","--service","X",...]}` (passe-plat) |
| `shell`      | `{action, cmd: "..."}` — **DÉSACTIVÉ par défaut**              |

## Configuration (variables d'environnement)

| Variable                     | Défaut       | Rôle                                       |
|------------------------------|--------------|--------------------------------------------|
| `KENBOT_REPO_DIR`            | `~/Desktop/kenbot-dashboard` | Racine du repo (où vit `devops/`)    |
| `KENBOT_DAEMON_DIR`          | `<repo>/kenbot-daemon`       | Dossier de travail du daemon         |
| `KENBOT_QUEUE_POLL`          | `10`         | Secondes entre 2 polls inbox               |
| `KENBOT_WATCHDOG_INTERVAL`   | `1800`       | Secondes entre 2 snapshots watchdog        |
| `KENBOT_WATCHDOG_PROJECTS`   | `kenbot,luxura,calcauto` | Projets surveillés           |
| `KENBOT_WATCHDOG_ENABLED`    | `1`          | `0` pour désactiver le watchdog            |
| `KENBOT_HTTP_PORT`           | `7777`       | Port webhook                               |
| `KENBOT_HTTP_ENABLED`        | `1`          | `0` pour désactiver le webhook             |
| `KENBOT_DAEMON_TOKEN`        | *(vide)*     | **Secret X-Daemon-Token** — vide = refuse tout |
| `KENBOT_ALLOW_SHELL`         | `0`          | `1` pour autoriser action `shell` (dangereux) |
| `KENBOT_NOTIFY_MACOS`        | `1`          | Notifications natives macOS                |

## Sécurité

- Webhook écoute uniquement sur `127.0.0.1` (jamais exposé au réseau)
- Token X-Daemon-Token requis pour `/cmd` et `/status`
- Si le token est vide, le webhook **refuse toutes** les requêtes (par sécurité)
- `subprocess.run` avec **args list** (pas de shell injection)
- Action `shell` désactivée par défaut

## Que fait le watchdog ?

Toutes les 30 min (configurable) :
1. Lance `snapshot --project all` (3 projets)
2. Compare avec le snapshot précédent
3. Pour chaque service : si une **var critique** (cf. `CRITICAL_VARS` dans `protect_render_envvars.py`) était présente avant et a disparu → **restauration automatique** depuis l'ancien snapshot
4. Notification macOS + log si auto-restore déclenché

→ **Plus jamais de perte silencieuse d'env vars** (le problème récurrent #4 de tes handoffs).

## Combo iPhone Shortcut

Tu peux créer un Apple Shortcut "Restart Kenbot" qui fait :
```
URL: http://<ip-mac-local>:7777/cmd
Method: POST
Headers: X-Daemon-Token: <ton-token>
Body: {"action":"restart","service":"kenbot-runner"}
```
*(Le Mac doit être sur le même réseau Wi-Fi, ou via Tailscale/ZeroTier pour accès distant.)*

## Logs

- `kenbot-daemon/logs/daemon.log` — log principal (rotation 2 MB × 5)
- `kenbot-daemon/logs/launchd.out.log` — stdout brut launchd
- `kenbot-daemon/logs/launchd.err.log` — stderr brut launchd

## Heartbeat

Le fichier `kenbot-daemon/heartbeat.txt` est mis à jour toutes les 30s.
Si la dernière ligne date de >2 min → le daemon est mort.
