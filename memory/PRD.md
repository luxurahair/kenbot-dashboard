# PRD — Kenbot Dashboard & PHOTOS_ADDED Fix

## Date: 2026-04-10

## Projet
**kenbot** — Bot d'inventaire automobile automatisé pour Kennebec Dodge (Daniel Giroux, Saint-Georges, Beauce)
- Scrape l'inventaire de véhicules usagés sur kennebecdodge.ca
- Génère des textes publicitaires AI (OpenAI + Sticker PDF Stellantis)
- Publie/met à jour sur Facebook automatiquement
- Gère le cycle de vie: NEW / SOLD / RESTORE / PRICE_CHANGED / PHOTOS_ADDED
- Feed Meta CSV pour publicités

## Architecture
- **Repos GitHub:** luxurahair/kenbot-runner, luxurahair/kenbot-api, luxurahair/kennebec-meta-feed
- **Hébergement production:** Render (cron toutes les 60 min)
- **Base de données:** Supabase (tables: inventory, posts, events, sticker_pdfs, scrape_runs)
- **Storage:** Supabase Storage (kennebec-raw, kennebec-stickers, kennebec-outputs)
- **APIs:** Facebook Graph API, Kennebec Dodge website, OpenAI, Chrysler (stickers PDF)
- **Stack:** Python 3.11, FastAPI, requests, BeautifulSoup, PDFMiner, Supabase client

## Dashboard Emergent
- **Stack:** React + FastAPI + MongoDB
- **Design:** Swiss Brutalist (Archetype 4) - Chivo/IBM Plex Sans/IBM Plex Mono
- **Fonctionnalités:**
  - Overview: 4 stat cards (véhicules actifs, posts FB, sans photos, dernier run)
  - Cron runs table avec badges status
  - Posts mini-list avec badges NO PHOTO
  - Inventaire complet avec filtrage
  - Posts FB avec section NO PHOTO en rouge
  - Architecture interactive (machine d'état, composants, flux)
  - Changelog des fixes avec sévérités

## Problème résolu - PHOTOS_ADDED
3 bugs identifiés et corrigés dans `runner_cron_prod.py`:

### Bug 1 (CRITIQUE) - no_photo jamais True
Le flag `no_photo` était toujours `False` et `photo_count` à `1` lors de la création d'un post NEW avec le fallback NO_PHOTO.
**Fix:** Nouvelle fonction `_is_no_photo_fallback()` + `no_photo=True` / `photo_count=0`

### Bug 2 (CRITIQUE) - Arguments inversés
`_build_ad_text(sb, v, "NEW", run_id)` → crash (mauvais ordre)
**Fix:** `_build_ad_text(sb, run_id, slug, v, "NEW")`

### Bug 3 (MEDIUM) - Détection restrictive
Mots-clés de recherche insuffisants dans base_text
**Fix:** Ajout de "sans photo", "photo à venir", "photos à venir", "no_photo"

## Ce qui a été implémenté
- [x] Dashboard d'administration kenbot complet (React + FastAPI)
- [x] 5 onglets: Dashboard, Inventaire, Posts FB, Architecture, Changelog
- [x] Données de démo seeded dans MongoDB
- [x] Fix PHOTOS_ADDED dans `/app/kenbot-runner-fix/runner_cron_prod.py`
- [x] Documentation des fixes dans `/app/kenbot-runner-fix/CHANGELOG_FIX.md`
- [x] Tests 100% passés (backend 6/6 APIs, frontend all features)

## Backlog / Prochaines étapes
- P0: Pousser le fix runner_cron_prod.py sur GitHub → redéploiement Render
- P0: Script migration pour marquer anciens posts NO_PHOTO dans Supabase
- P1: Connecter le dashboard aux données réelles Supabase (avec credentials)
- P1: Bouton "Run Now" dans le dashboard pour trigger le cron manuellement
- P2: Alertes email/webhook quand PHOTOS_ADDED détecte des posts
- P2: Dashboard Luxura séparé (découplage Kennebec/Luxura)
- P3: Monitoring temps réel des runs cron via WebSocket
