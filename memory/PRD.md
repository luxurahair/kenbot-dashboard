# PRD — Kenbot Dashboard + Bot Intelligence

## Date: 2026-04-12

## Ce qui a été fait

### Session 1-11 (résumé)
- Dashboard React + FastAPI connecté Supabase live
- Intelligence véhicule (27 marques, 43 modèles, 194 trims)
- llm_v3.py (GPT-4o, Daniel Giroux, 5 styles d'intro)
- VIN decoder NHTSA (vin_decoder.py)
- Cockpit (Sync Status, Audit Prix, Marquer Vendus)
- Détection VENDU/SOLD dans le cron
- Séparation kenbot-dashboard standalone (Render + Vercel)

### Session 12 - Corrections Critiques (2026-04-12)
- **FIX: `publish_with_photos` inexistant** → remplacé par publish_photos_unpublished + create_post_with_attached_media
- **FIX: Duplicate key `23505` sur slug** → upsert_post on_conflict="slug" + fallback 3 niveaux
- **FIX: Double appel `_build_ad_text`** → PHOTOS_ADDED réutilise msg déjà généré (÷2 appels OpenAI)
- **AJOUT: Pré-cache PDFs Stellantis 2018+** → vérifie/télécharge tous les PDFs au début du cron
- **AJOUT: `ensure_sticker_cached` amélioré** → retourne pdf_bytes directement, upsert_sticker_pdf isolé
- **AJOUT: `_extract_year()` + `_is_stellantis_2018_plus()`** → extraction année titre/VIN position 10
- **AJOUT: Détection NO_PHOTO par comparaison FB vs Kennebec** → Si FB a 0-1 photo et Kennebec a plusieurs → PHOTOS_ADDED. Remplace la détection par flags/text hints.
- **AJOUT: Programme de test complet** (`tests/test_pipeline_complet.py`) — 88 tests: VIN, NHTSA, PDF extraction, structure annonce, footer, lien sticker, no_photo

## Architecture
```
/app
├── kenbot-runner/ (Bot)
│   ├── runner_cron_prod.py (1464 lignes - cron principal)
│   ├── llm_v3.py, vehicle_intelligence.py, vin_decoder.py
│   ├── fb_api.py, supabase_db.py, kennebec_scrape.py
│   ├── sticker_to_ad.py, ad_builder.py, footer_utils.py
│   └── tests/test_pipeline_complet.py (88 tests)
└── kenbot-dashboard/ (Dashboard standalone)
    ├── api/server.py (FastAPI sur Render)
    └── frontend/src/App.js (React sur Vercel)
```

## Backlog
- P0: Push GitHub → vérifier logs cron (corrections critiques)
- P1: Phase A — Pipeline OpenAI unifié (JSON structuré)
- P1: Multi-dealer Luxura (config séparée)
- P2: Phase B — Review pass IA (contrôle qualité pré-publication)
- P2: Alertes/notifications (token FB expiré, échec cron)
- P3: Découper runner_cron_prod.py en modules (1464 lignes)
