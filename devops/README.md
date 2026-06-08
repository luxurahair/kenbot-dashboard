# 🚀 Mini Emergent v1.1

Outil complémentaire pour gérer Render, GitHub, secrets et diagnostics
par **projet logique** (Kenbot, Luxura, CalcAuto).

## Commandes principales

```bash
cd ~/kenbot-dashboard

# === Kenbot (Automobile) ===
python devops/kenbotctl.py kenbot
python devops/diagnostic.py --project kenbot
python devops/protect_render_envvars.py --project kenbot

# === Luxura (Cheveux) ===
python devops/kenbotctl.py luxura
python devops/diagnostic.py --project luxura
python devops/protect_render_envvars.py --project luxura

# === CalcAuto AiPro (OCR factures Stellantis) ===
python devops/kenbotctl.py calcauto
python devops/diagnostic.py --project calcauto
python devops/protect_render_envvars.py --project calcauto

# === Tous les services ===
python devops/kenbotctl.py all
```

## Projets et services associés

| Projet     | Mots-clés détectés          | Exemples de services Render                                      |
|------------|------------------------------|------------------------------------------------------------------|
| `kenbot`   | `kenbot`, `beauce`, `facebook` (exclut `calcauto`) | kenbot-dashboard-api, kenbot-beauce-*, kenbot-news-*, kenbot-competitors-api |
| `luxura`   | `luxura`                     | luxura-multi-tape, luxura-multi-itip, luxura-multi-genius, luxura-multi-halo |
| `calcauto` | `calcauto`, `aipro`          | calcauto-aipro                                                   |

## Sous-commandes disponibles

| Commande            | Description                              |
|---------------------|------------------------------------------|
| `render-list`       | Liste les services Render                |
| `diagnostic`        | Diagnostic complet (services + env vars) |
| `protect`           | Snapshot des variables Render            |
| `restart --service` | Redémarre un service                     |
