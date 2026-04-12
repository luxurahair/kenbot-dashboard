# LOGIQUE DE PUBLICATION — ÉTAT ACTUEL
# Date: 2026-04-12
# Pour review avec ChatGPT

## FLUX PRINCIPAL (runner_cron_prod.py main())

```
1. SCRAPE Kennebec (3 pages)
   → current = {slug: vehicle_data}

2. CRÉER scrape_run (pour FK sticker_pdfs)
   → upsert_scrape_run(sb, run_id)

3. PRÉ-CACHE PDFs Stellantis 2018+
   Pour chaque véhicule Stellantis année >= 2018:
   → ensure_sticker_cached(vin) 
     → Cherche pdf_ok/{VIN}.pdf dans Supabase Storage
     → Si pas trouvé: télécharge depuis chrysler.com
     → Retourne {status, path, pdf_bytes}
   
   Log: [STICKER PRECACHE DONE] total=38 cache_hit=29 new_download=9

4. DÉTECTION DES CIBLES
   a) NEW: slugs pas dans inv_db
   b) PRICE_CHANGED: prix différent > seuil
   c) PHOTOS_ADDED: Comparaison FB vs Kennebec
      → Si photo_count DB <= 1 ET kennebec_photos > 1 → TRIGGER
      → Si no_photo flag = True → TRIGGER
      → Si base_text contient "photos suivront" → TRIGGER
   d) SOLD: slugs dans posts_db mais PAS dans current (disparu du site)

5. ORDRE DE TRAITEMENT (targets[:MAX_TARGETS])
   PHOTOS_ADDED → PRICE_CHANGED → NEW → SOLD
```

## GÉNÉRATION DE TEXTE (_build_ad_text)

```
Pour chaque véhicule cible:

1. DÉCODAGE VIN (NHTSA) — pour TOUS les véhicules
   → decode_vin(vin) → specs (moteur, HP, transmission, 4WD, places)
   → format_specs_for_prompt(specs) → texte pour le prompt IA

2. SI Stellantis + USE_STICKER_AD:
   a) Chercher base_text existant dans posts DB (fallback)
   b) Chercher PDF via ensure_sticker_cached(vin)
      → Extraire options du PDF (pdfminer spans → groupes)
      → build_ad_from_options() → texte brut avec ✅/▫️
   c) Si pas de PDF → fallback base_text existant

3. PRIORITÉ 1: Stellantis avec sticker → humanisation IA
   → _humanize_sticker_text(raw_text, vehicle, event, vin_specs)
   → OpenAI GPT-4o: intro 3-4 phrases + titre vendeur + options humanisées
   → Filtre anti-vulgarité
   → Return texte humanisé

4. PRIORITÉ 2: llm_v3 (génération intelligente avec VIN)
   → generate_smart_text_v3(vehicle, event, options_text, vin_specs)
   → Utilise vehicle_intelligence.py pour le contexte
   → Return texte complet

5. PRIORITÉ 3: Sticker brut + intro AI ancienne
   → _maybe_add_ai_intro(vehicle, sticker_text)

6. PRIORITÉ 4: text_engine_client (service kdc-dgtext externe)
   → POST /generate {slug, event, vehicle}
   → Return facebook_text
```

## PUBLICATION FACEBOOK

```
A) EVENT = SOLD
   → update_post_text(post_id, "🚨 VENDU 🚨\n\n..." + base_text)
   → upsert_post(status=SOLD, sold_at=now)

B) EVENT = PRICE_CHANGED  
   → _build_ad_text(event=PRICE_CHANGED)
   → update_post_text(post_id, nouveau_texte)
   → upsert_post(status=ACTIVE, base_text=nouveau_texte)

C) EVENT = PHOTOS_ADDED (avec post_id existant)
   → _build_ad_text(event=NEW) — msg DÉJÀ généré en amont
   → delete_post(ancien_post_id)
   → publish_photos_unpublished(photos[:10])
   → create_post_with_attached_media(texte, media_ids)
   → upsert_post(post_id=NOUVEAU, photo_count=len(photos))

D) EVENT = PHOTOS_ADDED (SANS post_id = reset)
   → _build_ad_text(event=NEW) — msg DÉJÀ généré en amont  
   → publish_photos_unpublished(photos[:10])
   → create_post_with_attached_media(texte, media_ids)
   → upsert_post(post_id=NOUVEAU, photo_count=len(photos))

E) EVENT = NEW (nouveau véhicule)
   → _build_ad_text(event=NEW) — msg DÉJÀ généré en amont
   → publish_photos_unpublished(photos[:10]) 
   → create_post_with_attached_media(texte, media_ids)
   → upsert_post(status=ACTIVE, no_photo=fallback?, photo_count=N)
```

## CE QUI A ÉTÉ CORRIGÉ DANS CETTE SESSION

```
1. publish_with_photos → SUPPRIMÉ (n'existait pas)
   Remplacé par: publish_photos_unpublished + create_post_with_attached_media

2. publish_photos_as_comment_batch → SUPPRIMÉ (403 Facebook)
   On prend les 10 premières photos, c'est tout.

3. Double _build_ad_text dans PHOTOS_ADDED → CORRIGÉ
   Réutilise msg déjà généré (÷2 appels OpenAI)

4. Duplicate key slug 23505 → CORRIGÉ  
   upsert_post: on_conflict="slug" + fallback update 3 niveaux

5. FK sticker_pdfs_run_id_fkey → CORRIGÉ
   upsert_scrape_run() AVANT le pré-cache

6. Pré-cache PDFs Stellantis 2018+ → AJOUTÉ
   Télécharge tous les PDFs au début du cron

7. Détection NO_PHOTO FB vs Kennebec → AJOUTÉ
   Si FB a 0-1 photo et Kennebec a plusieurs → PHOTOS_ADDED

8. ensure_sticker_cached amélioré → retourne pdf_bytes directement
   Plus de double téléchargement
```

## CE QUI VIENT DE KDC-DGTEXT (pas encore fusionné)

```
engine/dg_text.py:
  - build_facebook_dg() — Format long avec specs détaillées
  - build_marketplace_dg() — Format court Marketplace
  - Specs: transmission, cylindres, entraînement, carburant, passagers, couleurs
  - Footer DG complet avec "pas un robot, promis 😄"

engine/classifier.py:
  - classify() → exotic/truck/suv/minivan/sedan/coupe/ev/default
  - Plus riche que vehicle_intelligence.py pour les catégories

engine/marketplace_smart.py:
  - generate_marketplace_text() ≤800 chars
  - Profils: exotic/truck/luxury/sport/daily
  - Anti-invention strict

engine/llm.py:
  - generate_ad_text() — Intro AI courte (220 chars)
  - Prompt Daniel Giroux vendeur

engine/text_pipeline.py:
  - Pipeline complet PDF → options → build_ad
  - parse_sticker_lines_to_options()
  - build_publish_text()
  - build_marketplace_text()

profiles/exotic.py, truck.py, suv.py, default.py:
  - Templates déterministes par type de véhicule
  - Pas d'IA, toujours cohérents
```

## SCHÉMA DB SUPABASE

```
inventory:
  slug, stock, url, title, vin, price_int, km_int, status, updated_at

posts:
  slug (PK), stock (UNIQUE), post_id, status, published_at, 
  last_updated_at, sold_at, base_text, no_photo, photo_count

events:
  id, created_at, slug, type, payload (JSON)

scrape_runs:
  run_id (PK), created_at, status, note

sticker_pdfs:
  vin (PK), status, storage_path, bytes, sha256, reason, 
  run_id (FK→scrape_runs), updated_at
```
