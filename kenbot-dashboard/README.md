# KENBOT DASHBOARD — Centre de Contrôle

Dashboard web pour monitorer et contrôler le bot Kenbot (Kennebec Dodge Chrysler).

## Architecture

```
kenbot-dashboard/
├── api/                          # Backend FastAPI (Render)
│   ├── server.py                 # API REST + Cockpit + Preview + Architecture
│   ├── vehicle_intelligence.py   # Base de connaissance véhicules (copie)
│   ├── vin_decoder.py            # Décodage VIN NHTSA (copie)
│   ├── requirements.txt          # Dépendances Python
│   ├── start.py                  # Script de démarrage
│   └── render.yaml               # Config Render
├── frontend/                     # Frontend React (Vercel)
│   ├── src/
│   │   ├── App.js                # Application principale (8 onglets)
│   │   └── App.css               # Styles
│   ├── public/
│   ├── package.json
│   └── vercel.json               # Config Vercel
└── README.md
```

## Onglets

| Onglet | Description |
|---|---|
| **Cockpit** | Stats live: actifs, vendus, no_photo, audit prix. Actions manuelles. |
| **Dashboard** | Vue d'ensemble système: connexion Supabase, derniers events |
| **Inventaire** | Liste complète des véhicules scrappés avec VIN, prix, km |
| **Posts FB** | Tous les posts Facebook: ACTIVE, SOLD, photo_count |
| **Preview Texte** | Générer/prévisualiser les textes IA pour un véhicule |
| **Events** | Journal d'événements (NEW, SOLD, UNSOLD, PHOTOS_ADDED, etc.) |
| **Architecture** | Diagramme des composants et flux |
| **Changelog** | Historique des versions et corrections |

## Déploiement

### Backend (Render)
1. Créer un **Web Service** sur Render
2. Connecter au repo GitHub
3. Root directory: `kenbot-dashboard/api`
4. Build command: `pip install -r requirements.txt`
5. Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`

### Frontend (Vercel)
1. Importer le repo sur Vercel
2. Root directory: `kenbot-dashboard/frontend`
3. Framework: Create React App
4. Build command: `yarn build`

## Variables d'Environnement

### Backend (Render)
| Variable | Obligatoire | Description |
|---|---|---|
| `SUPABASE_URL` | ✅ | URL du projet Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | Clé service_role Supabase |
| `OPENAI_API_KEY` | ✅ | Clé API OpenAI (pour Preview Texte) |
| `CORS_ORIGINS` | Non | Origines CORS autorisées (défaut: `*`) |

### Frontend (Vercel)
| Variable | Obligatoire | Description |
|---|---|---|
| `REACT_APP_BACKEND_URL` | ✅ | URL du backend Render (ex: `https://kenbot-api.onrender.com`) |

## API Endpoints

### Système
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/` | Version API + status Supabase |
| GET | `/api/system/status` | Stats complètes (inventaire, posts, events) |

### Données
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/inventory` | Liste inventaire complet |
| GET | `/api/posts` | Liste posts Facebook |
| GET | `/api/events?limit=30` | Derniers événements |
| GET | `/api/changelog` | Historique versions |
| GET | `/api/architecture` | Composants + flux système |

### Cockpit
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/cockpit/data` | Stats cockpit (actifs, vendus, no_photo, prix) |

### Preview Texte
| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/generate-text/{stock}` | Génère texte IA pour un véhicule |

## Version Actuelle: 4.0.0 (2026-04-12)

### Nouveautés
- Architecture mise à jour avec tous les composants (12 modules)
- Changelog v4.0.0: UNSOLD, SEO, Cleanup, comparaison par STOCK
- Pipeline documenté avec 6 états: UNSOLD → PHOTOS_ADDED → PRICE_CHANGED → NEW → SOLD → CLEANUP
