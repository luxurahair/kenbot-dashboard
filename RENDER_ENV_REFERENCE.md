# KENBOT RUNNER — Reference des Variables d'Environnement (Render)

> Source: Screenshots Render du 2026-04-11
> Service: kenbot-runner (Render Cron)

---

## VARIABLES SYSTEME

| Variable | Valeur | Description |
|----------|--------|-------------|
| `KENBOT_BASE_URL` | `https://www.kennebecdodge.ca` | URL du site inventaire a scraper |
| `KENBOT_INVENTORY_PATH` | `/fr/inventaire-occasion/` | Path des pages inventaire |
| `KENBOT_RUN_MODE` | `FULL` | Mode de run (FULL = pipeline complet) |
| `KENBOT_TEXT_ENGINE_URL` | `https://kenbot-text-engine.onrender.com` | URL du service de generation texte externe |
| `USE_AI` | `1` | Activer l'AI OpenAI pour les intros |

## VARIABLES FACEBOOK

| Variable | Valeur | Description |
|----------|--------|-------------|
| `KENBOT_FB_PAGE_ID` | *(masque)* | ID de la page Facebook |
| `KENBOT_FB_ACCESS_TOKEN` | *(masque)* | Token d'acces Facebook Graph API |

## VARIABLES PUBLICATION

| Variable | Valeur | Description |
|----------|--------|-------------|
| `KENBOT_MAX_TARGETS` | `6` | Max vehicules a traiter par run |
| `KENBOT_MIN_POST_TEXT_LEN` | `300` | Longueur minimum du texte pour publier |
| `KENBOT_POST_COOLDOWN_DAYS` | `7` | Jours avant re-publication du meme stock |
| `KENBOT_SLEEP_BETWEEN_POSTS` | `60` | Secondes entre chaque publication |
| `KENBOT_PUBLISH_MISSING` | `1` | Publier les vehicules manquants |
| `KENBOT_REBUILD_POSTS` | `1` | Reconstruire le map des posts existants |

## VARIABLES PHOTOS

| Variable | Valeur | Description |
|----------|--------|-------------|
| `KENBOT_ALLOW_NO_PHOTO` | `1` | Autoriser publication sans photo (avec fallback) |
| `KENBOT_NO_PHOTO_BUCKET` | `kennebec-outputs` | Bucket Supabase du fallback no_photo |
| `KENBOT_NO_PHOTO_PATH` | `assets/no_photo.jpg` | Path du fichier fallback dans le bucket |
| `KENBOT_PHOTO_RETRIES` | `3` | Nombre de tentatives de telechargement photo |
| `KENBOT_REFRESH_NO_PHOTO_DAILY` | `1` | Verifier les posts NO_PHOTO quotidiennement |
| `KENBOT_REFRESH_NO_PHOTO_LIMIT` | `25` | Max posts NO_PHOTO a traiter par run |

## VARIABLES SUPABASE

| Variable | Valeur | Description |
|----------|--------|-------------|
| `SUPABASE_URL` | `https://xjhqkhlocxtawiuokrlp.supabase.co/` | URL du projet Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | `eyJhbGci...SeQ` | Cle service_role Supabase |
| `SB_BUCKET_OUTPUTS` | `kennebec-outputs` | Bucket pour les outputs (textes, feeds, assets) |
| `SB_BUCKET_RAW` | `kennebec-raw` | Bucket pour les pages HTML brutes |
| `SB_BUCKET_STICKERS` | `kennebec-stickers` | Bucket pour les PDF sticker Stellantis |

## VARIABLES OPENAI

| Variable | Valeur | Description |
|----------|--------|-------------|
| `OPENAI_API_KEY` | `sk-proj-i_w8hIOP-rM7...Lr6kA` | Cle API OpenAI pour generation texte AI |

## VARIABLES NETTOYAGE / MAINTENANCE

| Variable | Valeur | Description |
|----------|--------|-------------|
| `KENBOT_KEEP_RUNS` | `5` | Nombre de scrape_runs a garder |
| `KENBOT_OUTPUT_RUNS_KEEP` | `3` | Nombre de runs d'output a garder |
| `KENBOT_SNAP_KEEP` | `3` | Nombre de snapshots a garder |
| `KENBOT_RAW_KEEP` | `1` | Nombre de raw pages a garder |
| `KENBOT_CLEAN_WITHWITHOUT_DAILY` | `1` | Nettoyage quotidien des with/without |
| `KENBOT_CLEAN_WITHWITHOUT_KEEP_ACTIVE_ONLY` | `1` | Garder seulement les actifs lors du nettoyage |
| `KENBOT_CLEAN_WITHWITHOUT_LIMIT` | `5000` | Limite d'items pour le nettoyage |

## VARIABLES META / FEED

| Variable | Valeur | Description |
|----------|--------|-------------|
| `KENBOT_BUILD_META_FEEDS` | `1` | Construire le CSV feed Meta |
| `KENBOT_BUILD_ALL_OUTPUTS` | `0` | Construire TOUS les outputs (desactive) |
| `KENBOT_COMPARE_META_VS_SITE` | `0` | Comparer meta feed vs site (desactive) |
| `KENBOT_META_FEED_PATH` | `feeds/meta_vehicle.csv` | Path du feed Meta dans le bucket |
| `KENBOT_META_REPORT_PATH` | `reports/meta_vs_site.csv` | Path du rapport comparaison |

## VARIABLES AUTOFIX

| Variable | Valeur | Description |
|----------|--------|-------------|
| `KENBOT_AUTOFIX` | `1` | Activer l'autofix des posts |
| `KENBOT_MAX_FIX` | `6` | Max posts a fixer par run |

---

## TABLES SUPABASE

| Table | Description |
|-------|-------------|
| `inventory` | Etat courant de l'inventaire (slug, stock, title, vin, price_int, km_int, status, last_seen, updated_at) |
| `posts` | Posts Facebook (slug, stock, post_id, status, published_at, last_updated_at, sold_at, base_text, **no_photo**, **photo_count**) |
| `events` | Journal des evenements (slug, type, payload, created_at) |
| `scrape_runs` | Historique des runs (run_id, created_at, status, note) |
| `sticker_pdfs` | Cache des PDF sticker Stellantis (vin, status, storage_path, etc.) |

## BUCKETS SUPABASE STORAGE

| Bucket | Public | Contenu |
|--------|--------|---------|
| `kennebec-outputs` | OUI | Textes FB/Marketplace, feed Meta CSV, assets (no_photo.jpg) |
| `kennebec-raw` | NON | Pages HTML brutes scrapees |
| `kennebec-stickers` | NON | PDF sticker Stellantis (pdf_ok/ et pdf_bad/) |
| `kennebec-facebook-snapshots` | NON | Snapshots des posts Facebook |
