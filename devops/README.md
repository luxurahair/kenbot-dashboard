# 🚀 Mini Emergent v3

CLI unifiée pour gérer les services Render des **3 projets logiques** :
- 🚗 **Kenbot** (Auto)
- 💇 **Luxura** (Cheveux)
- 🧾 **CalcAuto AiPro** (OCR factures Stellantis)

## Architecture

```
devops/
├── kenbotctl.py             # CLI principal — toutes les commandes
├── render_client.py         # Wrapper Render API (list/env/restart)
├── diagnostic.py            # Diagnostic complet par projet
├── protect_render_envvars.py# Snapshot RÉEL des env vars + alertes
└── contexts/
    ├── __init__.py          # 3 BaseContext (KENBOT, LUXURA, CALCAUTO)
    ├── base.py              # Une SEULE classe paramétrée
    ├── kenbot.py            # rétro-compat → KENBOT
    ├── luxura.py            # rétro-compat → LUXURA
    └── calcauto.py          # rétro-compat → CALCAUTO
```

## Commandes

```bash
cd ~/kenbot-dashboard

# === Liste services par projet ===
python devops/kenbotctl.py kenbot      # Kenbot uniquement
python devops/kenbotctl.py luxura      # Luxura uniquement
python devops/kenbotctl.py calcauto    # CalcAuto uniquement
python devops/kenbotctl.py all         # Tous (33 services)

# === Redémarrer un service ===
python devops/kenbotctl.py restart --service kenbot-dashboard-api

# === Lister les env vars d'un service ===
python devops/kenbotctl.py env-list --service kenbot-news-publisher

# === Snapshot des env vars (alerte si vars critiques manquantes) ===
python devops/kenbotctl.py snapshot                       # 3 projets
python devops/kenbotctl.py snapshot --project kenbot      # un seul

# === Diagnostic complet (via CLI ou script direct) ===
python devops/kenbotctl.py diagnostic --project kenbot
python devops/diagnostic.py --project kenbot

# === Snapshot direct (équivalent CLI) ===
python devops/protect_render_envvars.py --project all
```

## Filtres par projet

| Projet     | Mots-clés                    | Exclusions          | Services |
|------------|------------------------------|---------------------|----------|
| `kenbot`   | `kenbot`, `beauce`, `facebook` | `calcauto`, `aipro` | 21       |
| `luxura`   | `luxura`                     | —                   | 9        |
| `calcauto` | `calcauto`, `aipro`          | —                   | 1        |

## Vars critiques surveillées

Le `snapshot` alerte si une de ces variables disparaît :

- **Kenbot** : `KENBOT_FB_PAGE_ID`, `KENBOT_FB_PAGE_ACCESS_TOKEN`, `KENBOT_API_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `BEAUCE_AGENT_TOKEN`, `TWILIO_ACCOUNT_SID`
- **Luxura** : `LUXURA_API_URL`, `SUPABASE_URL`
- **CalcAuto** : `GOOGLE_VISION_API_KEY`, `SUPABASE_URL`

## Ajouter un 4ᵉ projet

```python
# devops/contexts/__init__.py
NEWPROJ = BaseContext("newproj", keywords=["xyz"])
ALL_PROJECTS["newproj"] = NEWPROJ
```
Aucune autre modification — le CLI, snapshot et diagnostic le reconnaissent automatiquement.
