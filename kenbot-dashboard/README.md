# kenbot-dashboard

Dashboard de monitoring et centre de contrôle pour le bot Kenbot (Kennebec Dodge).

## Architecture

```
kenbot-dashboard/
├── api/                    # Backend FastAPI (déployer sur Render)
│   ├── server.py
│   ├── vehicle_intelligence.py
│   ├── vin_decoder.py
│   ├── requirements.txt
│   └── render.yaml
├── frontend/               # Frontend React (déployer sur Vercel)
│   ├── src/
│   ├── package.json
│   └── vercel.json
└── README.md
```

## Déploiement

### Backend (Render)
1. Créer un nouveau **Web Service** sur Render
2. Connecter au repo `kenbot-dashboard`
3. Root directory: `api`
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
6. Variables d'environnement requises:
   - `SUPABASE_URL` — URL du projet Supabase
   - `SUPABASE_SERVICE_ROLE_KEY` — Clé service_role Supabase
   - `OPENAI_API_KEY` — Clé API OpenAI (pour génération texte)

### Frontend (Vercel)
1. Importer le repo `kenbot-dashboard` sur Vercel
2. Root directory: `frontend`
3. Framework: Create React App
4. Variable d'environnement:
   - `REACT_APP_BACKEND_URL` — URL du backend Render (ex: `https://kenbot-dashboard-api.onrender.com`)
5. Domaine custom: `kenbot.calcauto.ai` (ou `dashboard.calcauto.ai`)

## Fonctionnalités
- **Cockpit** — Stats live, simulation dry run, logs récents
- **Preview Texte** — Générer/prévisualiser les textes IA par véhicule
- **Humanisation Sticker** — Humaniser les annonces Stellantis Window Sticker
- **Décodage VIN** — Specs NHTSA automatiques (moteur, HP, sécurité)
- **Inventaire/Posts/Events** — Vue live des données Supabase
