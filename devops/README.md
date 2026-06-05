# 🚀 Mini Emergent v1.0

Outil interne pour gérer **Kenbot** et **Luxura** en toute sécurité.

---

## Commandes principales

```bash
# Aller dans le projet
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
Commandes disponibles





























CommandeDescriptionrender-listListe tous les services Renderenv-list --service XXXListe les variables d’un servicediagnosticDiagnostic complet du systèmeprotectSnapshot des variables Renderrestart --service XXXRedémarre un service Render

Structure

contexts/ → Séparation claire Kenbot / Luxura
render_client.py → Communication avec Render API
protect_render_envvars.py → Sauvegarde automatique des variables
supabase_client.py → Outils SQL Supabase
diagnostic.py → Diagnostics avancés


Important :

Toujours utiliser --project kenbot ou --project luxura pour ne pas mélanger les variables.
Le fichier .secrets.env doit être rempli et protégé (chmod 600 .secrets.env).
