# AUDIT — Variables d'Environnement Render vs Code Source
> Date: 2026-02-XX | Fichiers analysés: runner.py, runner_cron_prod.py, supabase_db.py, llm.py, llm_v3.py, autofix_from_report.py, meta_compare_supabase.py, audit_fb_live_compare.py, unsold_ghost_posts.py, tools/*.py

---

## RESUME

| Catégorie | Nombre |
|-----------|--------|
| Variables Render correctement utilisées dans le code | **30** |
| Variables Render **ORPHELINES** (jamais lues par le code) | **9** |
| Variables du code **absentes de Render** (avec default) | **~20** |
| Divergences de valeurs par défaut | **4** (non bloquantes) |

---

## 1. VARIABLES CORRECTEMENT MAPPEES (Render → Code)

| Variable Render | Valeur Render | Fichiers qui la lisent |
|---|---|---|
| `KENBOT_BASE_URL` | `https://www.kennebecdodge.ca` | runner.py:67, runner_cron_prod.py:84, meta_compare_supabase.py:22, tools/audit_sold_ghosts.py:10 |
| `KENBOT_INVENTORY_PATH` | `/fr/inventaire-occasion/` | runner.py:68, runner_cron_prod.py:85, tools/audit_sold_ghosts.py:11 |
| `KENBOT_TEXT_ENGINE_URL` | `https://kenbot-text-engine.onrender.com` | runner.py:69, runner_cron_prod.py:86, autofix_from_report.py:24 |
| `USE_AI` | `1` | runner_cron_prod.py:102 |
| `KENBOT_FB_PAGE_ID` | *(masque)* | runner.py:70, runner_cron_prod.py:87 |
| `KENBOT_FB_ACCESS_TOKEN` | *(masque)* | runner.py:71, runner_cron_prod.py:88, autofix_from_report.py:23, audit_fb_live_compare.py:7, unsold_ghost_posts.py:8, tools/* |
| `KENBOT_MAX_TARGETS` | `6` | runner.py:83, runner_cron_prod.py:95 |
| `KENBOT_MIN_POST_TEXT_LEN` | `300` | runner_cron_prod.py:103 |
| `KENBOT_POST_COOLDOWN_DAYS` | `7` | runner_cron_prod.py:104 |
| `KENBOT_SLEEP_BETWEEN_POSTS` | `60` | runner.py:84, runner_cron_prod.py:98, autofix_from_report.py:22 |
| `KENBOT_REBUILD_POSTS` | `1` | runner.py:81 |
| `KENBOT_ALLOW_NO_PHOTO` | `1` | runner_cron_prod.py:106, tools/audit_and_fix_live.py:28 |
| `KENBOT_NO_PHOTO_BUCKET` | `kennebec-outputs` | runner_cron_prod.py:107, tools/audit_and_fix_live.py:32 |
| `KENBOT_NO_PHOTO_PATH` | `assets/no_photo.jpg` | runner_cron_prod.py:108, tools/audit_and_fix_live.py:33 |
| `KENBOT_PHOTO_RETRIES` | `3` | runner_cron_prod.py:105 |
| `KENBOT_REFRESH_NO_PHOTO_DAILY` | `1` | runner_cron_prod.py:110 |
| `KENBOT_REFRESH_NO_PHOTO_LIMIT` | `25` | runner_cron_prod.py:111 |
| `SUPABASE_URL` | `https://xjhqkhlocxtawiuokrlp.supabase.co/` | runner.py:72, runner_cron_prod.py:89, supabase_db.py:23, tools/audit_and_fix_live.py:34 |
| `SUPABASE_SERVICE_ROLE_KEY` | *(masque)* | runner.py:73, runner_cron_prod.py:90, supabase_db.py:24 |
| `SB_BUCKET_OUTPUTS` | `kennebec-outputs` | runner.py:78, runner_cron_prod.py:93, meta_compare_supabase.py:18, autofix_from_report.py:18, tools/* |
| `SB_BUCKET_RAW` | `kennebec-raw` | runner.py:75, tools/audit_and_fix_live.py:18 |
| `SB_BUCKET_STICKERS` | `kennebec-stickers` | runner.py:76, runner_cron_prod.py:92, tools/bulk_update_fb_text_from_stickers.py:17 |
| `OPENAI_API_KEY` | *(masque)* | llm.py:141, llm_v3.py:22, runner_cron_prod.py:102+369 |
| `KENBOT_OUTPUT_RUNS_KEEP` | `3` | tools/cleanup_outputs_now.py:7, tools/cleanup_outputs_runs_now.py:9, tools/cleanup_runs_recursive_now.py:9 |
| `KENBOT_SNAP_KEEP` | `3` | runner.py:88, tools/cleanup_snapshots_runs_now.py:9 |
| `KENBOT_RAW_KEEP` | `1` | runner.py:87 |
| `KENBOT_META_FEED_PATH` | `feeds/meta_vehicle.csv` | meta_compare_supabase.py:19 |
| `KENBOT_META_REPORT_PATH` | `reports/meta_vs_site.csv` | meta_compare_supabase.py:20, autofix_from_report.py:19 |
| `KENBOT_AUTOFIX` | `1` | autofix_from_report.py:26 |
| `KENBOT_MAX_FIX` | `6` | autofix_from_report.py:21 |

---

## 2. VARIABLES RENDER ORPHELINES (definies dans Render mais JAMAIS lues par le code)

| Variable Render | Valeur | Impact |
|---|---|---|
| `KENBOT_RUN_MODE` | `FULL` | **MOYEN** — Aucun `os.getenv("KENBOT_RUN_MODE")` dans le code. Si l'intention etait de controler un mode partial vs full, cette logique n'existe pas. La variable est ignoree. |
| `KENBOT_PUBLISH_MISSING` | `1` | **MOYEN** — Jamais lue. Le runner publie toujours les vehicules manquants sans consulter cette variable. Comportement identique que la valeur soit 0 ou 1. |
| `KENBOT_KEEP_RUNS` | `5` | **BAS** — Jamais lue directement. Le code utilise `KENBOT_OUTPUT_RUNS_KEEP` (=3) pour le cleanup. Cette variable est probablement confondue avec celle-la. |
| `KENBOT_CLEAN_WITHWITHOUT_DAILY` | `1` | **MOYEN** — Jamais lue. Le nettoyage with/without se fait via les scripts tools/ mais aucun ne consulte cette variable pour savoir si le nettoyage doit etre quotidien. |
| `KENBOT_CLEAN_WITHWITHOUT_KEEP_ACTIVE_ONLY` | `1` | **MOYEN** — Jamais lue. Le script `cleanup_outputs_with_without_by_inventory.py` ne consulte pas cette variable. |
| `KENBOT_CLEAN_WITHWITHOUT_LIMIT` | `5000` | **MOYEN** — Jamais lue. Pas de `os.getenv("KENBOT_CLEAN_WITHWITHOUT_LIMIT")` dans le code. |
| `KENBOT_BUILD_META_FEEDS` | `1` | **MOYEN** — Jamais lue. Le script `meta_compare_supabase.py` s'execute sans verifier cette variable. |
| `KENBOT_BUILD_ALL_OUTPUTS` | `0` | **BAS** — Jamais lue. Probablement prevue pour controler un mode complet de build. |
| `KENBOT_COMPARE_META_VS_SITE` | `0` | **BAS** — Jamais lue. Le script `meta_compare_supabase.py` s'execute toujours, cette variable ne le controle pas. |

**Recommandation:** Ces 9 variables representent une "dette de configuration". Soit le code doit etre mis a jour pour les lire et agir en consequence, soit elles devraient etre retirees de Render pour eviter la confusion.

---

## 3. VARIABLES DU CODE ABSENTES DE RENDER (avec valeurs par defaut)

### 3a. Variables runner.py / runner_cron_prod.py (critiques)

| Variable dans le code | Default | Fichier | Risque |
|---|---|---|---|
| `KENBOT_DRY_RUN` | `"0"` | runner.py:80, unsold_ghost_posts.py:20 | BAS — Mode test. Le default "0" est correct pour la prod. |
| `KENBOT_FORCE_STOCK` | `""` | runner.py:82 | BAS — Debug: forcer le traitement d'un stock specifique. Pas besoin en prod. |
| `KENBOT_CACHE_STICKERS` | `"1"` | runner.py:85 | BAS — Active par defaut, OK. |
| `KENBOT_STICKER_MAX` | `"999"` | runner.py:86 | BAS — Limite haute par defaut, OK. |
| `KENBOT_MAX_PHOTOS` | `"15"` | runner.py:89, runner_cron_prod.py:96 | BAS — Default raisonnable. |
| `KENBOT_POST_PHOTOS` | `"10"` | runner.py:90, runner_cron_prod.py:97 | BAS — Default raisonnable. |
| `KENBOT_TMP_PHOTOS_DIR` | `"/tmp/kenbot_photos"` | runner.py:91 | BAS — Path tmp standard. |
| `KENBOT_PRICE_CHANGE_THRESHOLD` | `"200"` | runner.py:95, runner_cron_prod.py:99 | **MOYEN** — Seuil de detection changement de prix. $200 est le default mais pourrait etre configurable en prod. |
| `SB_BUCKET_SNAPSHOTS` | `"kennebec-facebook-snapshots"` | runner.py:77 | **MOYEN** — Le bucket snapshots est utilise mais pas dans Render. Le default correspond au bucket existant donc OK, mais ajouter a Render pour coherence. |
| `KENBOT_FB_USE_STICKER_AD` | `"1"` | runner_cron_prod.py:100 | BAS — Active par defaut, OK. |
| `OPENAI_MODEL` | `"gpt-4o-mini"` | llm.py:19 | **MOYEN** — Le modele OpenAI est hard-code en default. Pourrait etre utile de le configurer dans Render. |

### 3b. Variables tools/ (utilitaires manuels — faible priorite)

| Variable | Default | Fichier |
|---|---|---|
| `KENBOT_NO_PHOTO_URL` | `""` | tools/audit_and_fix_live.py:29 |
| `KENBOT_FIX_SLEEP` | `"12"` | tools/audit_and_fix_live.py:25 |
| `KENBOT_FIX_LIMIT` | `"999"` | tools/audit_and_fix_live.py:26 |
| `KENBOT_BULK_LIMIT` | `"200"` | tools/bulk_update_fb_text_from_stickers.py:13 |
| `KENBOT_BULK_SLEEP` | `"12"` | tools/bulk_update_fb_text_from_stickers.py:14 |
| `KENBOT_CLEANUP_DRY_RUN` | `"1"` | tools/cleanup_*.py |
| `KENBOT_OUTPUTS_RUNS_PREFIX` | `"runs"` | tools/cleanup_outputs_runs_now.py:8 |
| `KENBOT_PAGES` | `"3"` | tools/audit_sold_ghosts.py:12 |
| `KENBOT_FB_FIX_SLEEP` | `"8"` | tools/fix_fb_diff_rebuild_like_new.py:18 |
| `KENBOT_FB_FIX_SKIP_NO_PHOTO` | `"1"` | tools/fix_fb_diff_rebuild_like_new.py:21 |
| `KENBOT_FB_AUDIT_LIMIT` | `"25"` | audit_fb_live_compare.py:8 |

---

## 4. DIVERGENCES DE VALEURS PAR DEFAUT (Render vs Code)

| Variable | Valeur Render | Default dans le code | Impact |
|---|---|---|---|
| `KENBOT_MAX_TARGETS` | `6` | `4` | Pas de bug: Render override le default a 6. |
| `KENBOT_SLEEP_BETWEEN_POSTS` | `60` | `30` | Pas de bug: Render override le default a 60s. |
| `KENBOT_SNAP_KEEP` | `3` | `10` (runner.py) | Pas de bug: Render override a 3 snapshots gardes. |
| `KENBOT_RAW_KEEP` | `1` | `2` (runner.py) | Pas de bug: Render override a 1 raw page gardee. |

> Ces divergences ne sont PAS des bugs car Render ecrase les defaults. Mais si Render etait indisponible, le code utiliserait des valeurs differentes de l'intention en production.

---

## 5. ALIAS / FALLBACKS DETECTES

| Variable primaire (Render) | Alias fallback (code) | Fichiers |
|---|---|---|
| `KENBOT_FB_PAGE_ID` | `FB_PAGE_ID` | runner.py:70, runner_cron_prod.py:87 |
| `KENBOT_FB_ACCESS_TOKEN` | `FB_PAGE_ACCESS_TOKEN` | runner.py:71, runner_cron_prod.py:88, tools/* |

> Les alias sont maintenus pour compatibilite arriere. Pas de probleme tant que les variables primaires sont definies dans Render.

---

## 6. ACTIONS RECOMMANDEES

### Priorite HAUTE
1. **Implementer `KENBOT_RUN_MODE`** ou la retirer de Render — elle suggere un controle FULL vs PARTIAL qui n'existe pas dans le code.
2. **Implementer `KENBOT_PUBLISH_MISSING`** — le runner devrait consulter cette variable avant de publier les vehicules manquants.
3. **Ajouter `SB_BUCKET_SNAPSHOTS`** a Render pour coherence (valeur: `kennebec-facebook-snapshots`).

### Priorite MOYENNE
4. **Implementer les 3 variables CLEAN_WITHWITHOUT** dans `tools/cleanup_outputs_with_without_by_inventory.py`.
5. **Implementer les 3 variables BUILD/COMPARE META** dans `runner_cron_prod.py` ou `meta_compare_supabase.py`.
6. **Ajouter `OPENAI_MODEL`** a Render pour pouvoir changer de modele sans redeploy.
7. **Ajouter `KENBOT_PRICE_CHANGE_THRESHOLD`** a Render.

### Priorite BASSE
8. Clarifier `KENBOT_KEEP_RUNS` vs `KENBOT_OUTPUT_RUNS_KEEP` — confusion possible.
9. Les variables tools/ absentes de Render sont acceptables (utilitaires manuels avec bons defaults).
