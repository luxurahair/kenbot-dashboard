# 🛡️ Kenbot Daemon V3 — Local Mac Agent + AI Mode

Un mini-Emergent qui tourne sur **ton Mac**, avec :

| Loop / Feature   | Rôle                                                              |
|------------------|-------------------------------------------------------------------|
| 📥 queue         | Exécute les JSON drop dans `commands/inbox/`                      |
| 🛡️ watchdog      | Snapshot env vars + **auto-restore** si vars critiques perdues    |
| 🌐 http          | Webhook localhost:7777 (`POST /cmd`, dashboard, status, health)   |
| 🔥 **AI mode**   | "redémarre le runner" → daemon traduit via GPT → exécute          |
| 📊 **Dashboard** | `http://localhost:7777/?t=TOKEN` — HTML live (status + outbox + logs) |
| 🔔 **Push iPhone** | Notifications via ntfy.sh (gratuit, hors Wi-Fi)                  |
| 🎯 **Templates** | `commands/templates/*.json` rejouables                            |
| 📲 Apple Shortcut | Piloter depuis iPhone (voir section dédiée)                       |

## Installation

### 1. Pré-requis (1 fois)

```bash
# Aucune dépendance Python additionnelle requise (xai/grok utilise urllib stdlib)

# Push iPhone : crée un topic ntfy obscur (ex: kenbot-daniel-xyz-7k2)
# - Aucun compte requis
# - Installe l'app "ntfy" sur ton iPhone (App Store)
# - Dans l'app: + → Subscribe to topic → entre ton topic
```

### 2. Édite la config

```bash
cd ~/Desktop/kenbot-dashboard
nano kenbot-daemon/com.dgauto.kenbot-daemon.plist
```

À changer (3 lignes) :
- `KENBOT_DAEMON_TOKEN` → token webhook (`openssl rand -hex 32`)
- `XAI_API_KEY`         → ta clé xai/grok (commence par `xai-`) — déjà dans tes services Luxura Render
- `KENBOT_NTFY_TOPIC`   → ton topic ntfy secret (optionnel)

> **AI providers supportés** : `xai` (Grok-4, défaut, $$$), `openai` (GPT, $$), `emergent` (proxy gratuit limité)
> Modèle par défaut : **`grok-4-fast-non-reasoning`** (~10x moins cher que grok-4 et largement assez bon pour de la traduction FR→JSON)

### 3. Installe

```bash
bash kenbot-daemon/install.sh
```

### 4. Teste

```bash
TOKEN="<ton token>"
curl http://localhost:7777/health
curl -H "X-Daemon-Token: $TOKEN" http://localhost:7777/status
```

Puis ouvre dans Safari : `http://localhost:7777/?t=<TON_TOKEN>` → **dashboard live**.

## 🔥 AI Mode — langage naturel

```bash
curl -X POST http://localhost:7777/cmd \
  -H "X-Daemon-Token: $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"action":"ai","prompt":"redémarre le news cron"}'
# → AI traduit en {"action":"restart","service":"kenbot-news-publisher"} → exécute
```

Phrases qui marchent (testées) :
- "redémarre kenbot-runner svp"
- "fais une sauvegarde de tout"
- "liste les env vars du runner"
- "donne-moi la liste des env vars de calcauto"

## 🎯 Templates

```bash
# Joue un template
curl -X POST http://localhost:7777/cmd \
  -H "X-Daemon-Token: $TOKEN" \
  -d '{"action":"template","name":"morning-checkup"}'

# Template avec variables {{var}}
curl -X POST http://localhost:7777/cmd \
  -H "X-Daemon-Token: $TOKEN" \
  -d '{"action":"template","name":"env-set-generic","vars":{"service":"kenbot-runner","key":"MY_KEY","value":"123"}}'
```

Templates fournis :
- `snapshot-all`         : snapshot des 3 projets
- `morning-checkup`      : snapshot + env-list des 2 services critiques
- `restart-news-cron`    : redémarre news-publisher + runner
- `env-set-generic`      : set d'env var avec vars `{{service}}/{{key}}/{{value}}`

Ajoute tes propres templates dans `commands/templates/*.json` — le daemon les détecte automatiquement.

## 📲 Apple Shortcut (iPhone)

Crée un Shortcut sur ton iPhone pour piloter le daemon à la voix ("Hey Siri, redémarre le runner") :

1. App **Shortcuts** → **+** → Nouveau raccourci
2. Ajoute action **"Obtenir contenu de l'URL"**
   - URL : `http://<IP-MAC-LOCAL>:7777/cmd`
   - Méthode : **POST**
   - Headers :
     - `X-Daemon-Token`: `<ton token>`
     - `Content-Type`: `application/json`
   - Corps de la requête (JSON) :
     ```json
     {"action":"ai","prompt":"Texte demandé"}
     ```
3. Ajoute action **"Demander une saisie"** → connecte le résultat dans le JSON via la variable `Texte demandé`
4. Nomme : **"Kenbot"**
5. Active : **"Avec Siri"** → ajoute la phrase déclencheur

Maintenant tu peux dire à ton iPhone (sur le même Wi-Fi que le Mac) :
> *"Dis Siri, lance Kenbot"*
> *"Redémarre le runner"* → tâche exécutée en 3 secondes

> ⚠️ Le Mac doit être joignable depuis l'iPhone (même Wi-Fi, ou via **Tailscale** pour accès distant)

## 🔔 Push notification ntfy

Les événements suivants déclenchent une push iPhone :
- ✅ Commande exécutée OK
- ❌ Commande échouée
- ⚠️ Watchdog : auto-restore d'une env var critique

Configuration : `KENBOT_NTFY_TOPIC=ton-topic-secret` dans le plist. Si vide → désactivé silencieusement.

## 📊 Dashboard live

`http://localhost:7777/?t=<TOKEN>`

Auto-refresh 10s. Affiche :
- Heartbeat (âge en secondes)
- Inbox pending / Processing / Outbox total
- Status watchdog + AI
- 10 derniers résultats
- 50 dernières lignes de log

## Actions supportées (résumé)

| Action       | Payload                                                             |
|--------------|---------------------------------------------------------------------|
| `ai`         | `{action, prompt: "phrase en français"}`                            |
| `template`   | `{action, name: "snapshot-all", vars: {…}}`                         |
| `restart`    | `{action, service}`                                                 |
| `env-set`    | `{action, service, key, value}`                                     |
| `env-list`   | `{action, service}`                                                 |
| `snapshot`   | `{action, project: "kenbot\|luxura\|calcauto\|all"}`                |
| `kenbotctl`  | `{action, args: [...]}` (passe-plat brut)                           |
| `shell`      | `{action, cmd}` — **DÉSACTIVÉ par défaut** (`KENBOT_ALLOW_SHELL=1`) |

## Sécurité

- HTTP listen `127.0.0.1` uniquement
- Token `X-Daemon-Token` requis pour `/cmd`, `/status`, `/` (dashboard)
- `subprocess.run` avec **args list** (pas de shell injection)
- Action `shell` désactivée par défaut
- AI mode peut être désactivé via `KENBOT_AI_ENABLED=0`
- Token URL accepté : `/?t=TOKEN` (utile pour Shortcut, mais évite de le partager)

## Désinstaller

```bash
bash kenbot-daemon/uninstall.sh
```
