# PRD — kenbot-runner Bug Fix: PHOTOS_ADDED Detection

## Date: 2026-04-10

## Projet
**kenbot-runner** — Bot automatisé pour le concessionnaire Kennebec Dodge (Daniel Giroux)
- Scrape l'inventaire de véhicules usagés sur kennebecdodge.ca
- Génère des textes publicitaires (AI + sticker PDF)
- Publie/met à jour sur Facebook automatiquement
- Gère les transitions NO_PHOTO → WITH_PHOTO (PHOTOS_ADDED)

## Architecture
- **Repo GitHub:** luxurahair/kenbot-runner
- **Hébergement:** Render (cron toutes les 60 min)
- **Base de données:** Supabase (tables: inventory, posts, events, sticker_pdfs)
- **APIs:** Facebook Graph API, Kennebec Dodge website, OpenAI (textes AI), Chrysler (stickers PDF)
- **Stack:** Python 3.11, requests, BeautifulSoup, Supabase client

## Problème signalé
Le cron ne détecte pas les posts publiés avec l'image placeholder "NO PHOTO" pour les mettre à jour quand les vraies photos deviennent disponibles.

## Root Cause Analysis
3 bugs identifiés dans `runner_cron_prod.py`:

1. **Bug critique**: Le flag `no_photo` est toujours mis à `False` et `photo_count` à `1` lors de la création d'un post NEW avec le fallback NO_PHOTO. La détection PHOTOS_ADDED ne trouve donc jamais ces posts.

2. **Bug crash**: L'appel `_build_ad_text(sb, v, "NEW", run_id)` dans la section PHOTOS_ADDED a les arguments dans le mauvais ordre → crash systématique.

3. **Bug détection**: Les mots-clés de recherche dans `base_text` sont trop restrictifs et ne matchent pas les textes générés.

## Ce qui a été implémenté
- ✅ Fonction `_is_no_photo_fallback()` pour détecter le fallback NO_PHOTO
- ✅ Correction du flag `no_photo: True` / `photo_count: 0` lors de la création NEW avec fallback
- ✅ Correction de l'ordre des arguments de `_build_ad_text` dans PHOTOS_ADDED
- ✅ Ajout de mots-clés de détection supplémentaires
- ✅ Logs détaillés pour le debugging
- ✅ Vérification que les photos téléchargées pour PHOTOS_ADDED ne sont pas le fallback

## Fichier corrigé
- `/app/kenbot-runner-fix/runner_cron_prod.py`
- `/app/kenbot-runner-fix/CHANGELOG_FIX.md`

## Backlog / Améliorations futures
- P0: Pousser le fix sur GitHub et vérifier le prochain run Render
- P1: Ajouter des colonnes `no_photo` et `photo_count` explicitement dans Supabase si elles n'existent pas
- P1: Script de migration pour marquer les anciens posts NO_PHOTO dans Supabase
- P2: Monitoring/alertes quand le cron PHOTOS_ADDED traite des posts
- P2: Dashboard web pour visualiser l'état des posts (avec/sans photos)
