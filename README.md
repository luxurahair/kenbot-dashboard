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

kenbot-daemon/                          # 🆕 Daemon Mac V3 (LaunchAgent local)
├── kenbot_daemon.py                    # Process principal — HTTP /cmd + queue + watchdog
├── supabase_queue.py                   # 🛰️  Pont cloud → Mac via Supabase agent_queue
├── com.dgauto.kenbot-daemon.plist      # Config launchctl
└── logs/daemon.log                     # Logs runtime

tools/                                  # Outils DevOps
├── fb_token_refresh.py                 # 🔒 Refresh Page Token (SAFEGUARD type=PAGE)
└── push_cmd_to_mac.py                  # Push commande dans agent_queue Supabase
```

## 🤖 Agents & Daemons (Vue d'ensemble)

Le système comporte **plusieurs daemons** qui collaborent pour donner un contrôle total sur l'iMac et les services cloud :

| Daemon / Service | Fichier source | Repo | Rôle |
|---|---|---|---|
| **V1 — Mac Remote** | `~/kenebec-ai/beauce-publisher/agent/mac_remote_daemon.py` | `kenebec-ai` | Reçoit commandes whitelistées depuis l'onglet **MAC REMOTE** du dashboard (ping, git_pull, restart, kill_chrome…) — UI en boutons |
| **V3 — Kenbot Daemon** | `~/kenbot-dashboard/kenbot-daemon/kenbot_daemon.py` | `kenbot-dashboard` | Polling Supabase `agent_queue` + HTTP webhook `localhost:7777` + traduction Grok (xAI) |
| **Beauce Publisher** (Agent #1) | `~/kenebec-ai/beauce-publisher/agent/dgauto_publish_one.py` | `kenebec-ai` | Publie auto sur groupes Facebook Beauce |
| **Maintainer** (Agent #2) | `~/kenebec-ai/beauce-publisher/agent/maintainer.py` | `kenebec-ai` | Garde session Facebook chaude |

### 🛰️ Canal Supabase Queue (cloud → Mac)

Bridge sécurisé entre les agents cloud et le Mac local, via la table Supabase `agent_queue` :

```
☁️  Cloud agent (Render/CI/AI)
    │
    │ POST {action, payload, signature(HMAC-SHA256)}
    ▼
🗄️  Supabase agent_queue (status=pending, target=mac_daemon)
    │
    │ Daemon V3 polle toutes les 10s
    ▼
🖥️  Mac V3 daemon
    │ - Vérifie signature HMAC
    │ - Exécute action (read_file, write_file, ai, restart, etc.)
    │ - Écrit result dans la table
    ▼
☁️  Cloud relit le résultat
```

**Sécurité** : chaque commande est signée HMAC-SHA256 avec `KENBOT_AGENT_HMAC_SECRET`. La signature est vérifiée avant exécution. Le shell brut (`action: shell`) est désactivé par défaut (`KENBOT_ALLOW_SHELL=1` pour activer).

**Actions disponibles** :
- `read_file` / `write_file` — limité à `REPO_DIR` et `DAEMON_DIR`
- `ai` — prompt en langage naturel → Grok traduit → exécution
- `restart` / `env-set` / `env-list` / `snapshot` — wrappe `devops/kenbotctl.py`
- `template` — workflow JSON multi-étapes
- `kenbotctl` — wrappe le CLI complet

### 🐛 Bug fix critique 2026-06-10

**Bug** : `supabase_queue.py` utilisait `if resp.length` pour vérifier la réponse HTTP. Mais Supabase répond avec `Transfer-Encoding: chunked` → `resp.length = None` → la fonction `_supa_request` retournait silencieusement `None`. Le daemon polling tournait mais ne voyait **jamais** les commandes pending.

**Fix** ([commit `c9dff2da`](https://github.com/luxurahair/kenbot-dashboard/commit/c9dff2da)) : lire le body d'abord, puis vérifier qu'il n'est pas vide.

### 🎙️ Voice Grok iPhone (en construction)

Permet de parler à Siri depuis n'importe où dans le monde pour piloter le Mac et les services Render :

```
🎙️ "Dis Siri, Kenbot, redémarre l'API"
      ↓ Apple Shortcut
☁️ POST kenbot-dashboard-api.onrender.com/api/grok/voice
      ↓ pousse dans agent_queue (action=ai)
🖥️ Daemon V3 → Grok traduit → exécute → écrit result
      ↓
🔊 Siri lit la réponse à voix haute
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

## Corrections Récentes (v4.2.0 — 2026-06-10)

### 🤖 Daemon V3 + Canal Supabase
- **NEW**: Daemon Mac V3 (`kenbot-daemon/kenbot_daemon.py`) — process LaunchAgent local avec HTTP `/cmd`, queue Supabase et watchdog auto-recovery
- **NEW**: Bridge cloud→Mac via table Supabase `agent_queue` (signature HMAC-SHA256)
- **FIX critique**: `supabase_queue.py` ne récupérait jamais les commandes à cause d'un bug `resp.length is None` sur les réponses HTTP `Transfer-Encoding: chunked` Supabase
- **NEW**: Traduction langage naturel via xAI Grok intégrée au daemon (`AI_SYSTEM_PROMPT`)

### 🔒 Sécurité Token Facebook (Page Token permanent)
- **FIX critique**: 13 services Render Luxura propageaient un USER token (invalidable au changement de mot de passe FB) au lieu d'un PAGE token permanent. Échange via `/me/accounts` → tous les services maintenant sur Page Token (`type=PAGE`, `expires_at=0`)
- **FIX**: `kenbot-news-publisher` et `kenbot-runner` pointaient vers la mauvaise page (`FB_PAGE_ID=Luxura`). Corrigés vers KDC Auto Kennebec (`820789524460241`)
- **NEW**: `tools/fb_token_refresh.py` v2 avec SAFEGUARD `verify_page_token()` qui refuse de propager si `type != PAGE`, support multi-projet (`--project luxura|kenbot`), Graph API v23.0

## 🎙️ Voice Grok iPhone (v4.3.0 — 2026-06-11)

### Pipeline cloud → Mac entièrement opérationnel via Siri

**Architecture** :
```
🎙️ "Dis Siri, Kenbot, redémarre le runner"
   │ (dictée Apple Shortcut)
   ▼
☁️ POST kenbot-dashboard-api.onrender.com/api/grok/voice
   │ (header X-Voice-Token + body JSON {prompt})
   ▼
🛰️ Supabase agent_queue (signature HMAC-SHA256)
   │
   ▼
🖥️ Daemon V3 Mac (poll 10s) → xAI Grok traduit → execute_command
   │
   ▼
☁️ Result stocké dans agent_queue → API renvoie {speech: "Service redémarré."}
   ▼
🔊 Siri lit la réponse à voix haute
```

**Composants nouveaux** :
- `kenbot-dashboard/api/routers/grok_voice.py` — endpoint FastAPI `/api/grok/voice` côté Render
- `tools/grok_voice_shortcut_guide.md` — guide step-by-step Apple Shortcut iPhone
- `GROK_VOICE_TOKEN` env var sur kenbot-dashboard-api (Render)
- Prompt système Grok amélioré : reconnaît GitHub/Render/Vercel/Supabase comme proper nouns + anglicismes québécois + mapping intelligent status→snapshot

**Phrases qui marchent** (à dire à Siri) :
- *"Redémarre kenbot-runner"* → `restart`
- *"Combien j'ai de variables sur kenbot-dashboard-api"* → `env-list`
- *"Vérifie l'état de Render"* → `snapshot all`
- *"Diagnostic kenbot"* → `kenbotctl diagnostic --project kenbot`
- *"Lis-moi le README"* → `read_file path=README.md`

### 🛡️ Crisis Recovery (env vars Render écrasées)
- **INCIDENT 2026-06-11** : un PUT bulk a accidentellement écrasé les 23 env vars de `kenbot-dashboard-api`
- **MITIGATION** : 2 deploys annulés en urgence + restauration via snapshot `memory/render_envvars_snapshot.json` en moins de 60 secondes
- **LESSON** : ne JAMAIS faire `PUT /env-vars` (bulk) sans backup — préférer `PUT /env-vars/{KEY}` ciblé


