# KENBOT — Bot Facebook Automatisé pour Kennebec Dodge Chrysler

Bot intelligent qui scrape l'inventaire de véhicules, génère des annonces Facebook avec IA (GPT-4o), et gère automatiquement le cycle de vie des publications.

## Architecture

```
kenbot-runner/                          # Bot principal (Render Cron)
├── runner_cron_prod.py                 # Orchestrateur cron (~1600 lignes)
│   ├── Scrape Kennebec (3 pages)
│   ├── Pré-cache PDFs Stellantis 2018+
│   ├── Index par STOCK (clé de comparaison)
│   ├── Détection: NEW / SOLD / UNSOLD / PRICE_CHANGED / PHOTOS_ADDED
│   ├── Génération texte IA (VIN + Sticker + llm_v3)
│   ├── Publication Facebook (max 10 photos/post)
│   └── Cleanup double footer
│
├── kennebec_scrape.py                  # Scraper HTML + extraction VIN
├── vin_decoder.py                      # Décodage VIN via NHTSA API (17 chars strict)
├── vehicle_intelligence.py             # 27 marques, 43 modèles, 194 trims
├── llm_v3.py                           # GPT-4o: 5 styles d'intro, anti-clichés
├── sticker_to_ad.py                    # Extraction PDF Window Sticker (PDFMiner)
├── ad_builder.py                       # Construction annonce ✅/▫️ structurée
├── footer_utils.py                     # Footer unique Daniel Giroux + hashtags SEO
├── fb_api.py                           # Facebook Graph API wrapper
├── supabase_db.py                      # Supabase PostgreSQL wrapper
├── meta_compare_supabase.py            # Rapport CSV meta vs site
└── tests/
    ├── test_pipeline_complet.py        # 88 tests pipeline bout-en-bout
    └── test_sold_unsold_logic.py       # 11 tests logique SOLD/UNSOLD par stock

kenbot-dashboard/                       # Dashboard Web (Vercel + Render)
├── api/server.py                       # FastAPI backend
└── frontend/src/App.js                 # React frontend
```

## Pipeline Cron (toutes les 60 min)

```
1. SCRAPE kennebecdodge.ca (3 pages) → 47 véhicules
2. SCRAPE_RUN créé dans Supabase (pour FK sticker_pdfs)
3. PRÉ-CACHE PDFs Stellantis 2018+ (38 véhicules, cache hit ~100%)
4. INDEX par STOCK (source de vérité pour toutes comparaisons)
5. DÉTECTION:
   ├── UNSOLD    — Post marqué VENDU mais stock encore sur Kennebec → restaurer
   ├── PHOTOS_ADDED — FB a 0-1 photo ET Kennebec > 1 → delete + recreate
   ├── PRICE_CHANGED — Prix différent > 200$ → update texte + intro rabais
   ├── NEW       — Slug pas dans inv_db → nouveau post
   ├── SOLD      — Stock PAS sur Kennebec + cooldown 3 jours → marquer VENDU
   └── CLEANUP   — Corriger double footer sur posts existants (max 10/run)
6. RAPPORT meta_vs_site.csv uploadé dans Supabase Storage
```

## Génération de Texte IA

```
Priorité 1: Stellantis + Sticker → _humanize_sticker_text (GPT-4o)
   - Intro 3-4 phrases québécoises + options ✅ MAJUSCULES / ▫️ minuscules
   - Lien Window Sticker PDF

Priorité 2: llm_v3 → generate_smart_text_v3 (GPT-4o)
   - vehicle_intelligence.py → type, vibe, ton marketing
   - vin_decoder.py → moteur, HP, transmission, 4WD
   - 5 styles d'intro: direct, storytelling, question, expertise, opportunité

Priorité 3: text_engine_client (service kdc-dgtext externe)

Footer: footer_utils.py (source unique)
   - Échanges (auto, moto, bateau, VTT, côte-à-côte)
   - Daniel Giroux 418-222-3939
   - Hashtags SEO dynamiques (#DodgeHornet2024 #Beauce #Pickup etc.)
```

## Variables d'Environnement (Render)

### Obligatoires
| Variable | Description |
|---|---|
| `SUPABASE_URL` | URL du projet Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Clé service_role Supabase |
| `KENBOT_FB_PAGE_ID` | ID de la page Facebook |
| `KENBOT_FB_ACCESS_TOKEN` | Token d'accès Facebook (permanent, pages_manage_posts) |
| `OPENAI_API_KEY` | Clé API OpenAI (GPT-4o) |

### Optionnelles (avec valeurs par défaut)
| Variable | Défaut | Description |
|---|---|---|
| `KENBOT_BASE_URL` | `https://www.kennebecdodge.ca` | URL du site concessionnaire |
| `KENBOT_INVENTORY_PATH` | `/fr/inventaire-occasion/` | Chemin inventaire |
| `KENBOT_TEXT_ENGINE_URL` | *(vide)* | URL du service kdc-dgtext |
| `KENBOT_MAX_TARGETS` | `25` | Nombre max de véhicules traités par run |
| `KENBOT_SLEEP_BETWEEN` | `3` | Secondes entre chaque publication FB |
| `KENBOT_POST_COOLDOWN_DAYS` | `7` | Jours avant de re-publier un même stock |
| `KENBOT_PRICE_CHANGE_THRESHOLD` | `200` | Seuil minimum de changement de prix ($) |
| `KENBOT_REFRESH_NO_PHOTO_DAILY` | `true` | Activer la détection PHOTOS_ADDED |
| `KENBOT_REFRESH_NO_PHOTO_LIMIT` | `25` | Limite PHOTOS_ADDED par run |
| `KENBOT_USE_AI` | `true` | Utiliser GPT-4o pour le texte |
| `KENBOT_USE_STICKER_AD` | `true` | Utiliser les PDF Window Sticker |
| `KENBOT_STICKERS_BUCKET` | `kennebec-stickers` | Bucket Supabase pour les PDFs |
| `USE_HUMANIZE` | `true` | Humaniser les stickers Stellantis |

## Base de Données Supabase

### Tables
| Table | PK | Description |
|---|---|---|
| `inventory` | slug | Inventaire scrappé (stock, vin, prix, km, status) |
| `posts` | slug | Posts Facebook (post_id, status, base_text, photo_count, no_photo) |
| `events` | id | Journal d'événements (NEW, SOLD, UNSOLD, PRICE_CHANGED, etc.) |
| `scrape_runs` | run_id | Historique des runs cron |
| `sticker_pdfs` | vin | Cache des PDFs Window Sticker (status ok/bad, storage_path) |

### Storage Buckets
| Bucket | Contenu |
|---|---|
| `kennebec-stickers` | `pdf_ok/{VIN}.pdf` — PDFs Window Sticker validés |
| `kennebec-outputs` | `reports/meta_vs_site.csv` — Rapports de comparaison |

## Tests

```bash
# Pipeline complet (VIN, NHTSA, PDF, structure annonce, footer, no_photo)
python tests/test_pipeline_complet.py          # 88 tests
python tests/test_pipeline_complet.py --with-ai # Inclut test OpenAI

# Logique SOLD / UNSOLD / PRICE_CHANGED par stock
python tests/test_sold_unsold_logic.py          # 11 tests
```

## Corrections Récentes (v4.0.0 — 2026-04-12)

- **UNSOLD**: Restaure automatiquement les faux VENDU (stock encore sur Kennebec)
- **Comparaison par STOCK**: Plus de faux SOLD quand un slug change
- **Double footer corrigé**: `ad_builder.py` ne rajoute plus les échanges
- **Cleanup automatique**: Corrige les posts FB existants avec double footer
- **Hashtags SEO**: Dynamiques par véhicule (#DodgeHornet2024 #Beauce etc.)
- **PRICE_CHANGED**: Affiche le montant du rabais (📉 RÉDUCTION DE PRIX — 2 000 $ DE RABAIS!)
- **Photos en commentaires**: Supprimé (causait 403 FB). Max 10 photos par post.
