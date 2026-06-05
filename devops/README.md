# Mini Emergent v1.0

Outil interne pour gérer Kenbot et Luxura (inspiré d'Emergent).

## Commandes principales

```bash
cd /ton/projet/kenbot-dashboard

# Commandes de base
python devops/kenbotctl.py render-list --project kenbot
python devops/kenbotctl.py diagnostic --project kenbot
python devops/kenbotctl.py protect --project kenbot

# Pour Luxura
python devops/kenbotctl.py render-list --project luxura
Commandes disponibles

render-list → Liste tous les services Render
env-list --service XXX → Liste les variables d’un service
diagnostic → Diagnostic complet
protect → Snapshot des variables Render
restart --service XXX → Redémarre un service

Structure

contexts/ → Séparation Kenbot / Luxura
render_client.py → Communication avec Render API
protect_render_envvars.py → Sauvegarde automatique
supabase_client.py → Outils SQL (à venir)
