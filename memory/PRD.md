# PRD — Kenbot Dashboard + Bot Intelligence

## Date: 2026-04-12

## Ce qui a été fait

### Session 1 - Fix PHOTOS_ADDED
- 3 bugs corrigés dans runner_cron_prod.py (poussé sur GitHub)
- Dashboard admin créé avec React + FastAPI

### Session 2 - Dashboard Supabase Live
- Dashboard connecté aux vraies données Supabase
- 6 onglets: Dashboard, Inventaire, Posts FB, Events, Architecture, Changelog
- Bouton "Run Cron" avec options (Dry Run, Max targets, Force stock)

### Session 3 - Intelligence Véhicule
- Module vehicle_intelligence.py (27 marques, 43 modèles, 194 trims)
- Module llm_v3.py (GPT-4o, Daniel Giroux, 5 styles d'intro)
- Décodage VIN via NHTSA (vin_decoder.py)

### Session 4 - Audit Variables Environnement
- 30 variables Render mappées, 9 orphelines, ~20 absentes

### Session 5 - Test Génération IA
- 5 véhicules réels testés avec succès

### Session 6 - Onglet Preview Texte
- Humanisation sticker Stellantis (✅ MAJ + ▫️ min)
- Filtre anti-vulgarité

### Session 7 - Intégration VIN NHTSA + Humanisation Sticker dans Runner
- vin_decoder.py intégré dans runner_cron_prod.py
- _humanize_sticker_text() via OpenAI

### Session 8 - Cockpit Kenbot
- Simulation Dry Run, Sync Status, Audit Prix, Marquer Vendus

### Session 10 - Déploiement Standalone
- kenbot-dashboard/ séparé (Render backend + Vercel frontend)

### Session 11 - Détection VENDU/SOLD
- Logique SOLD dans runner_cron_prod.py
- 4 endpoints Cockpit

### Session 12 - Corrections Critiques (2026-04-12)
- **FIX: `publish_with_photos` inexistant** → remplacé par publish_photos_unpublished + create_post_with_attached_media
- **FIX: Duplicate key `23505` sur slug** → upsert_post changé de on_conflict="stock" à on_conflict="slug" (PK) + fallback 3 niveaux
- **FIX: Double appel `_build_ad_text`** → PHOTOS_ADDED réutilise msg déjà généré (÷2 appels OpenAI)
- **AJOUT: Pré-cache PDFs Stellantis 2018+** → Au début du cron, vérifie/télécharge tous les PDFs sticker pour Stellantis 2018+
- **AJOUT: `ensure_sticker_cached` amélioré** → retourne pdf_bytes directement + upsert_sticker_pdf isolé (FK ne casse plus le return)
- **AJOUT: `_extract_year()` + `_is_stellantis_2018_plus()`** → Extraction année depuis titre ou VIN position 10

## Architecture

```
/app
├── kenbot-runner/ (Bot)
│   ├── runner_cron_prod.py (1430 lignes - cron principal)
│   ├── llm_v3.py, vehicle_intelligence.py, vin_decoder.py
│   ├── fb_api.py, supabase_db.py, kennebec_scrape.py
│   └── sticker_to_ad.py, ad_builder.py
└── kenbot-dashboard/ (Dashboard standalone)
    ├── api/server.py (FastAPI sur Render)
    └── frontend/src/App.js (React sur Vercel)
```

## Backlog
- P0: Push GitHub → vérifier logs cron (corrections critiques)
- P1: Multi-dealer Luxura (config séparée)
- P2: Alertes/notifications (token FB expiré, échec cron)
- P2: A/B testing styles d'intro
- P3: Découper runner_cron_prod.py en modules (1430 lignes)
