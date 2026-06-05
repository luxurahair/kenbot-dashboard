# 🚀 Mini Emergent v1.0

Outil interne pour gérer **Kenbot** et **Luxura** en toute sécurité.

---

## Commandes principales

```bash
cd ~/kenbot-dashboard

# === Kenbot (Automobile) ===
python devops/kenbotctl.py render-list --project kenbot
python devops/kenbotctl.py diagnostic --project kenbot
python devops/kenbotctl.py protect --project kenbot

# === Luxura (Cheveux) ===
python devops/kenbotctl.py render-list --project luxura
Commande,Description
render-list,Liste tous les services Render
env-list --service XXX,Liste les variables d’un service
diagnostic,Diagnostic complet du système
protect,Snapshot des variables Render
restart --service XXX,Redémarre un service Render
