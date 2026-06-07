# 🚀 Mini Emergent v1.0

Outil complémentaire pour gérer Render, GitHub, secrets et diagnostics.

## Commandes principales

```bash
cd ~/kenbot-dashboard

# Kenbot
python devops/kenbotctl.py render-list --project kenbot
python devops/kenbotctl.py diagnostic --project kenbot
python devops/kenbotctl.py protect --project kenbot

# Luxura
python devops/kenbotctl.py render-list --project luxura
Commandes disponibles

render-list → Liste les services Render
diagnostic → Diagnostic complet
protect → Snapshot des variables Render
restart --service XXX → Redémarre un service
