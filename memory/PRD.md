# PRD — Kenbot Dashboard + PHOTOS_ADDED Fix

## Date: 2026-04-11

## Projet
**kenbot** — Bot d'inventaire automobile automatise pour Kennebec Dodge
- Scrape kennebecdodge.ca (76 vehicules)
- Publie sur Facebook (86 posts actifs)
- Machine d'etat: NEW/SOLD/RESTORE/PRICE_CHANGED/PHOTOS_ADDED
- 31,955 events traces dans Supabase

## Architecture
- Repos: luxurahair/kenbot-runner, kenbot-api, kennebec-meta-feed
- Production: Render (cron 60 min)
- DB: Supabase (xjhqkhlocxtawiuokrlp)
- Stack: Python 3.11, FastAPI, BeautifulSoup, Supabase, Facebook Graph API

## Dashboard Emergent (LIVE)
- Connecte a Supabase en temps reel
- 6 onglets: Dashboard, Inventaire, Posts FB, Events, Architecture, Changelog
- Donnees live: 46 actifs, 30 vendus, 82 posts, 31,955 events
- Design: Swiss Brutalist (Chivo/IBM Plex)

## Fix PHOTOS_ADDED (pousse sur GitHub)
1. FIX #1: no_photo=True quand fallback utilise (_is_no_photo_fallback)
2. FIX #2: Ordre arguments _build_ad_text corrige
3. FIX #3: Mots-cles detection elargis

## IMPORTANT - Colonnes manquantes
La table posts dans Supabase n'a PAS les colonnes no_photo et photo_count.
SQL a executer dans Supabase SQL Editor:
```sql
ALTER TABLE posts ADD COLUMN IF NOT EXISTS no_photo BOOLEAN DEFAULT FALSE;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS photo_count INTEGER DEFAULT 0;
```

## Backlog
- P0: Ajouter colonnes no_photo/photo_count dans Supabase (SQL ci-dessus)
- P1: Script migration anciens posts NO_PHOTO
- P1: Bouton "Run Now" dans dashboard
- P2: Multi-dealer (Luxura)
- P2: Alertes erreurs (webhook/email)
- P3: Unification couche texte
