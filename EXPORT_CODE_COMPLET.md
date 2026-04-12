# EXPORT CODE COMPLET — KENBOT RUNNER
# Date: 2026-04-12
# Pour review avec ChatGPT avant fusion avec kdc-dgtext

## Table des matières
1. runner_cron_prod.py (1448 lignes) — Orchestrateur principal
2. supabase_db.py (374 lignes) — DB Supabase  
3. llm_v3.py (346 lignes) — Génération IA v3
4. vehicle_intelligence.py (926 lignes) — Base de connaissance véhicules
5. vin_decoder.py (200 lignes) — Décodage VIN NHTSA
6. ad_builder.py (228 lignes) — Construction annonce sticker
7. footer_utils.py (327 lignes) — Footer Daniel Giroux
8. fb_api.py (259 lignes) — Facebook Graph API
9. text_engine_client.py (205 lignes) — Client text-engine
10. kennebec_scrape.py (461 lignes) — Scraper Kennebec


---

## FILE: runner_cron_prod.py
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner_cron_prod.py

Version propre et robuste, basée sur ton flux "simple qui publie" :
- Scrape 3 pages Kennebec
- Détection NEW / PRICE_CHANGED / PHOTOS_ADDED
- StickerToAd prioritaire pour Stellantis si PDF valide
- Intro AI optionnelle au-dessus du texte généré
- Anti-duplicate par cooldown sur stock
- Validation texte stricte avant publication / update
- Retries sur téléchargement des photos
- Meta compare lancé en fin de run sans jamais casser le cron
- PHOTOS_ADDED: Supprimer + Recréer le post avec les vraies photos
"""

import os
import time
import random
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

from kennebec_scrape import (
    fetch_html,
    parse_inventory_listing_urls,
    parse_vehicle_detail_simple,
    slugify,
)
from text_engine_client import generate_facebook_text
from fb_api import (
    publish_photos_unpublished,
    create_post_with_attached_media,
    update_post_text,
    delete_post,
)
from supabase_db import (
    get_client,
    get_inventory_map,
    get_posts_map,
    upsert_post,
    log_event,
    utc_now_iso,
    upload_bytes_to_storage,
    upsert_sticker_pdf,
)
from sticker_to_ad import extract_spans_pdfminer, extract_option_groups_from_spans
from ad_builder import build_ad as build_ad_from_options

# Import des modules centralisés pour footer et AI
from footer_utils import add_footer_if_missing, has_footer, get_dealer_footer
try:
    from llm import generate_ad_text, humanize_text, generate_intro_only
except ImportError:
    generate_ad_text = None
    humanize_text = None
    generate_intro_only = None

# Import llm_v3 - generation intelligente par vehicule
try:
    from llm_v3 import generate_smart_text as generate_smart_text_v3
    from vehicle_intelligence import build_vehicle_context
except ImportError:
    generate_smart_text_v3 = None
    build_vehicle_context = None

# Import vin_decoder - decodage VIN via NHTSA
try:
    from vin_decoder import decode_vin, format_specs_for_prompt
except ImportError:
    decode_vin = None
    format_specs_for_prompt = None

try:
    from meta_compare_supabase import meta_compare as meta_compare_fn
except Exception:
    meta_compare_fn = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

# -------------------------
# Env + Config
# -------------------------
for name in (".env.local", ".kenbot_env", ".env"):
    p = Path(name)
    if p.exists():
        load_dotenv(p, override=False)
        break

BASE_URL = os.getenv("KENBOT_BASE_URL", "https://www.kennebecdodge.ca").rstrip("/")
INVENTORY_PATH = os.getenv("KENBOT_INVENTORY_PATH", "/fr/inventaire-occasion/").strip()
TEXT_ENGINE_URL = (os.getenv("KENBOT_TEXT_ENGINE_URL") or "").strip()
FB_PAGE_ID = (os.getenv("KENBOT_FB_PAGE_ID") or os.getenv("FB_PAGE_ID") or "").strip()
FB_TOKEN = (os.getenv("KENBOT_FB_ACCESS_TOKEN") or os.getenv("FB_PAGE_ACCESS_TOKEN") or "").strip()
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

STICKERS_BUCKET = os.getenv("SB_BUCKET_STICKERS", "kennebec-stickers").strip()
OUTPUTS_BUCKET = os.getenv("SB_BUCKET_OUTPUTS", "kennebec-outputs").strip()

MAX_TARGETS = int(os.getenv("KENBOT_MAX_TARGETS", "10"))
MAX_PHOTOS = int(os.getenv("KENBOT_MAX_PHOTOS", "15"))
POST_PHOTOS = int(os.getenv("KENBOT_POST_PHOTOS", "10"))
SLEEP_BETWEEN = int(os.getenv("KENBOT_SLEEP_BETWEEN_POSTS", "30"))
PRICE_CHANGE_THRESHOLD = int(os.getenv("KENBOT_PRICE_CHANGE_THRESHOLD", "200"))
USE_STICKER_AD = os.getenv("KENBOT_FB_USE_STICKER_AD", "1").strip() == "1"
# USE_AI activé automatiquement si OPENAI_API_KEY est présent
USE_AI = os.getenv("USE_AI", "1" if os.getenv("OPENAI_API_KEY", "").strip() else "0").strip() == "1"
MIN_POST_TEXT_LEN = int(os.getenv("KENBOT_MIN_POST_TEXT_LEN", "300"))
POST_COOLDOWN_DAYS = int(os.getenv("KENBOT_POST_COOLDOWN_DAYS", "7"))
PHOTO_RETRIES = int(os.getenv("KENBOT_PHOTO_RETRIES", "3"))
ALLOW_NO_PHOTO = os.getenv("KENBOT_ALLOW_NO_PHOTO", "0").strip() == "1"
NO_PHOTO_BUCKET = (os.getenv("KENBOT_NO_PHOTO_BUCKET") or OUTPUTS_BUCKET).strip()
NO_PHOTO_PATH = (os.getenv("KENBOT_NO_PHOTO_PATH") or "assets/no_photo.jpg").strip().lstrip("/")
# PHOTOS_ADDED / REFRESH_NO_PHOTO: Utilise les variables existantes de votre système
REFRESH_NO_PHOTO_DAILY = os.getenv("KENBOT_REFRESH_NO_PHOTO_DAILY", "1").strip() == "1"
REFRESH_NO_PHOTO_LIMIT = int(os.getenv("KENBOT_REFRESH_NO_PHOTO_LIMIT", "25"))
if not TEXT_ENGINE_URL:
    raise SystemExit("KENBOT_TEXT_ENGINE_URL manquant")
if not FB_PAGE_ID or not FB_TOKEN:
    raise SystemExit("FB creds manquants")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("Supabase creds manquants")

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
    }
)

TMP_PHOTOS = Path("/tmp/kenbot_photos")
TMP_PHOTOS.mkdir(parents=True, exist_ok=True)

# -------------------------
# Helpers
# -------------------------
def _run_id() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.gmtime())

def _is_pdf_ok(blob: bytes) -> bool:
    if not blob:
        return False
    bb = blob.lstrip()
    return bb.startswith(b"%PDF") and b"%%EOF" in bb[-4096:]

def _is_stellantis_vin(vin: str) -> bool:
    vin = (vin or "").strip().upper()
    return len(vin) == 17 and vin.startswith(("1C", "2C", "3C", "ZAC", "ZFA"))

# Table de décodage année VIN (position 10, index 9)
_VIN_YEAR_MAP = {
    "J": 2018, "K": 2019, "L": 2020, "M": 2021,
    "N": 2022, "P": 2023, "R": 2024, "S": 2025, "T": 2026,
    "V": 2027, "W": 2028, "X": 2029, "Y": 2030,
    # Aussi les années plus anciennes
    "A": 2010, "B": 2011, "C": 2012, "D": 2013,
    "E": 2014, "F": 2015, "G": 2016, "H": 2017,
}

def _extract_year(v: Dict[str, Any]) -> int:
    """Extrait l'année du véhicule depuis le titre ou le VIN."""
    # Méthode 1: Titre (ex: "Dodge Hornet 2024")
    title = (v.get("title") or "").strip()
    import re as _re
    m = _re.search(r"\b(20[12]\d)\b", title)
    if m:
        return int(m.group(1))
    # Méthode 2: VIN position 10 (index 9)
    vin = (v.get("vin") or "").strip().upper()
    if len(vin) >= 10:
        yr_char = vin[9]
        if yr_char in _VIN_YEAR_MAP:
            return _VIN_YEAR_MAP[yr_char]
    return 0

def _is_stellantis_2018_plus(v: Dict[str, Any]) -> bool:
    """Retourne True si le véhicule est Stellantis ET année >= 2018."""
    vin = (v.get("vin") or "").strip().upper()
    if not _is_stellantis_vin(vin):
        return False
    year = _extract_year(v)
    return year >= 2018

def _norm_text(value: Any, suffix: str = "") -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        base = f"{int(value):,}".replace(",", " ")
        return f"{base} {suffix}".strip()
    txt = str(value).strip()
    return txt

def _vehicle_price_text(v: Dict[str, Any]) -> str:
    return _norm_text(v.get("price") if v.get("price") not in (None, "") else v.get("price_int"), "$")

def _vehicle_mileage_text(v: Dict[str, Any]) -> str:
    raw = v.get("mileage")
    if raw in (None, ""):
        raw = v.get("km")
    if raw in (None, ""):
        raw = v.get("km_int")
    return _norm_text(raw, "km")

def _run_meta_compare_safe() -> None:
    if not meta_compare_fn:
        print("[META SKIP] meta_compare_supabase.meta_compare introuvable", flush=True)
        return
    try:
        meta_compare_fn()
        print("[META] Comparaison meta vs site exécutée", flush=True)
    except Exception as e:
        print(f"[META ERROR] {e}", flush=True)

def _download_photo(url: str, out_path: Path, retries: int = 3) -> bool:
    for attempt in range(1, max(1, retries) + 1):
        try:
            r = SESSION.get(url, timeout=60)
            if r.status_code == 404:
                return False
            r.raise_for_status()
            out_path.write_bytes(r.content)
            return out_path.exists() and out_path.stat().st_size > 1024
        except Exception as e:
            print(f"[PHOTO RETRY] url={url} attempt={attempt}/{retries} err={e}", flush=True)
            time.sleep(min(2 * attempt, 6))
    return False

def _download_photos(sb, stock: str, urls: List[str], limit: int = MAX_PHOTOS) -> List[Path]:
    out: List[Path] = []
    stock = (stock or "UNKNOWN").strip().upper()
    folder = TMP_PHOTOS / stock
    folder.mkdir(parents=True, exist_ok=True)

    for i, u in enumerate((urls or [])[:limit], start=1):
        if not u:
            continue

        ext = ".jpg"
        low = u.lower()
        if ".png" in low:
            ext = ".png"
        elif ".webp" in low:
            ext = ".webp"

        p = folder / f"{stock}_{i:02d}{ext}"
        if p.exists() and p.stat().st_size > 1024:
            out.append(p)
            continue

        if _download_photo(u, p, retries=PHOTO_RETRIES):
            out.append(p)

    if out:
        return out

    if ALLOW_NO_PHOTO:
        try:
            blob = sb.storage.from_(NO_PHOTO_BUCKET).download(NO_PHOTO_PATH)
            if blob and len(blob) > 1000:
                p = folder / f"{stock}_NO_PHOTO.jpg"
                p.write_bytes(blob)
                print(f"[NO_PHOTO] fallback used: {NO_PHOTO_BUCKET}/{NO_PHOTO_PATH}", flush=True)
                return [p]
        except Exception as e:
            print(f"[NO_PHOTO] fallback failed: {e}", flush=True)

    return []


# =========================================================
# FIX #1: Fonction utilitaire pour détecter le fallback NO_PHOTO
# =========================================================
def _is_no_photo_fallback(photos: List[Path]) -> bool:
    """
    Détecte si les photos retournées par _download_photos sont
    le fallback NO_PHOTO (image placeholder).
    
    Retourne True si c'est un fallback, False si ce sont de vraies photos.
    """
    if not photos:
        return False
    # Le fallback est toujours 1 seul fichier avec "NO_PHOTO" dans le nom
    if len(photos) == 1 and "NO_PHOTO" in photos[0].name:
        return True
    return False


def ensure_sticker_cached(sb, vin: str, run_id: str) -> Dict[str, Any]:
    """
    Retourne {"status": "ok", "path": ..., "source": ..., "pdf_bytes": bytes}
    ou {"status": "bad/skip", ...}
    Les pdf_bytes sont inclus pour éviter un double téléchargement.
    """
    vin = (vin or "").strip().upper()
    if len(vin) != 17:
        return {"status": "skip", "reason": "invalid_vin"}

    ok_path = f"pdf_ok/{vin}.pdf"
    bad_path = f"pdf_bad/{vin}.pdf"

    # 1. Vérifier le cache Supabase Storage (pdf_ok/)
    try:
        blob = sb.storage.from_(STICKERS_BUCKET).download(ok_path)
        if _is_pdf_ok(blob):
            print(f"[PDF CACHE HIT] vin={vin} path={ok_path} size={len(blob)}", flush=True)
            return {"status": "ok", "path": ok_path, "source": "cache_ok", "pdf_bytes": blob}
    except Exception as e:
        print(f"[PDF CACHE MISS] vin={vin} err={e}", flush=True)

    # 2. Télécharger depuis Chrysler.com
    pdf_url = f"https://www.chrysler.com/hostd/windowsticker/getWindowStickerPdf.do?vin={vin}"

    fetched = b""
    source = ""

    # tentative simple requests
    try:
        r = SESSION.get(pdf_url, timeout=30)
        fetched = r.content or b""
        if _is_pdf_ok(fetched):
            source = "requests"
    except Exception as e:
        print(f"[PDF] requests failed vin={vin} err={e}", flush=True)

    # fallback playwright si requests a échoué
    if not source and sync_playwright is not None:
        for attempt in range(1, 4):
            try:
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/122.0.0.0 Safari/537.36"
                        ),
                        locale="fr-CA",
                    )
                    page = context.new_page()
                    response = page.goto(pdf_url, timeout=60000, wait_until="networkidle")
                    fetched = b""
                    if response is not None:
                        try:
                            fetched = response.body()
                        except Exception:
                            fetched = b""
                    browser.close()

                    if _is_pdf_ok(fetched):
                        source = f"playwright_attempt_{attempt}"
                        break
            except Exception as e:
                print(f"[PDF] Playwright attempt {attempt} failed vin={vin}: {e}", flush=True)
                time.sleep(random.uniform(2, 5))

    # 3. Si on a un PDF valide, le sauvegarder
    if source and _is_pdf_ok(fetched):
        try:
            upload_bytes_to_storage(sb, STICKERS_BUCKET, ok_path, fetched, "application/pdf", True)
        except Exception as e:
            print(f"[PDF] upload storage failed vin={vin}: {e}", flush=True)
        # upsert_sticker_pdf séparé pour éviter que FK casse le return
        try:
            upsert_sticker_pdf(sb, vin=vin, status="ok", storage_path=ok_path, data=fetched, reason="", run_id=run_id)
        except Exception as e:
            print(f"[PDF] upsert_sticker_pdf failed vin={vin}: {e} (non-bloquant)", flush=True)
        return {"status": "ok", "path": ok_path, "source": source, "pdf_bytes": fetched}

    # 4. Marquer comme bad (mais NE PAS écraser un pdf_ok existant)
    try:
        upload_bytes_to_storage(sb, STICKERS_BUCKET, bad_path, b"invalid", "application/octet-stream", True)
    except Exception:
        pass
    try:
        upsert_sticker_pdf(sb, vin=vin, status="bad", storage_path=bad_path, data=b"invalid", reason="fetch_failed", run_id=run_id)
    except Exception:
        pass

    return {"status": "bad", "reason": "fetch_failed"}

def _extract_options_from_sticker_bytes(pdf_bytes: bytes) -> List[Dict[str, Any]]:
    if not pdf_bytes or not _is_pdf_ok(pdf_bytes):
        return []

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp_path = f.name

        spans = extract_spans_pdfminer(tmp_path) or []
        groups = extract_option_groups_from_spans(spans) or []

        out: List[Dict[str, Any]] = []
        for g in groups:
            if not isinstance(g, dict):
                continue
            title = (g.get("title") or "").strip()
            details = g.get("details") or []
            if not title:
                continue
            if not isinstance(details, list):
                details = []
            out.append({"title": title, "details": details})
        return out
    except Exception as e:
        print(f"[WARN] _extract_options_from_sticker_bytes failed: {e}", flush=True)
        return []
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

def _ensure_contact_footer(text: str) -> str:
    """
    DEPRECATED: Utilise maintenant footer_utils.add_footer_if_missing()
    Garde pour compatibilité mais redirige vers le module centralisé.
    """
    return add_footer_if_missing(text)

def _maybe_add_ai_intro(v: Dict[str, Any], body: str, use_humanize: bool = True) -> str:
    """
    Ajoute une intro AI au texte ou humanise le texte complet.

    VERSION 2.0:
    - use_humanize=True: Réécrit l'intro du texte pour la rendre plus naturelle
    - use_humanize=False: Génère une intro séparée et l'ajoute au-dessus
    """
    if not os.getenv("OPENAI_API_KEY", "").strip():
        return body

    # Si humanize_text est disponible et activé, l'utiliser pour rendre le texte plus naturel
    if use_humanize and humanize_text is not None:
        try:
            humanized = humanize_text(body, v)
            if humanized and humanized != body:
                stock = (v.get('stock') or '').strip().upper()
                print(f"[AI HUMANIZE] Texte humanisé pour stock={stock}", flush=True)
                return humanized
        except Exception as e:
            stock = (v.get('stock') or '').strip().upper()
            print(f"[AI HUMANIZE ERROR] stock={stock} err={e}", flush=True)

    # Fallback: générer une intro séparée
    if not USE_AI:
        return body

    if generate_intro_only is None and generate_ad_text is None:
        return body

    try:
        from classifier import classify

        kind = (
            "price_changed"
            if v.get("old_price") not in (None, "") and v.get("new_price") not in (None, "")
            else classify(v)
        )

        # Utiliser generate_intro_only si disponible (plus adapté)
        if generate_intro_only is not None:
            intro = generate_intro_only(v, max_chars=250)
        elif generate_ad_text is not None:
            intro = generate_ad_text(v, kind, max_chars=250)
        else:
            return body

        intro = (intro or "").strip()
        if not intro:
            return body

        print(
            f"[AI INTRO] added for stock={(v.get('stock') or '').strip().upper()} kind={kind}",
            flush=True,
        )
        return (intro + "\n\n" + body).strip()

    except Exception as e:
        print(f"[AI INTRO ERROR] stock={(v.get('stock') or '').strip().upper()} err={e}", flush=True)
        return body

def _fmt_price(value: Any) -> str:
    try:
        n = int(value)
        return f"{n:,}".replace(",", " ") + " $"
    except Exception:
        return ""


def _price_changed_intro_variant2(title: str, old_price: Any, new_price: Any) -> str:
    old_txt = _fmt_price(old_price)
    new_txt = _fmt_price(new_price)

    if not old_txt or not new_txt:
        return ""

    title = (title or "").strip()
    if not title:
        return ""

    try:
        old_n = int(old_price)
        new_n = int(new_price)
    except Exception:
        return ""

    if new_n >= old_n:
        return ""

    return (
        f"💥 Nouveau prix pour ce {title} !\n\n"
        f"Avant : {old_txt}\n"
        f"Maintenant : {new_txt}\n\n"
        f"Si vous l'aviez à l'œil, c'est peut-être le bon moment pour passer à l'action."
    )


def _humanize_sticker_text(
    raw_text: str,
    v: Dict[str, Any],
    event: str,
    vin_specs_text: str = "",
) -> str:
    """
    Humanise un texte sticker_to_ad brut via OpenAI.
    - Ajoute une intro humaine 3-4 phrases
    - Humanise le titre
    - Traduit les noms d'options techniques en français lisible
    - ✅ OPTIONS en MAJUSCULES, ▫️ sous-options en minuscules
    - Conserve TOUT le footer, lien sticker, hashtags
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return ""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except Exception:
        return ""

    title = (v.get("title") or "").strip()
    stock = (v.get("stock") or "").strip().upper()

    # Construire le contexte véhicule
    ctx_info = ""
    if build_vehicle_context is not None:
        try:
            ctx = build_vehicle_context(v)
            parts = []
            if ctx.get("brand_identity"):
                parts.append(f"Marque: {ctx['brand_identity']}")
            if ctx.get("model_known_for"):
                parts.append(f"Modele: {ctx['model_known_for']}")
            if ctx.get("vehicle_type"):
                parts.append(f"Type: {ctx['vehicle_type']}")
            ctx_info = "\n".join(parts)
        except Exception:
            pass

    system_msg = (
        "Tu es Daniel Giroux, vendeur passionne chez Kennebec Dodge Chrysler a Saint-Georges.\n"
        "Tu recois une annonce Facebook generee a partir du Window Sticker d'un vehicule Stellantis.\n\n"
        "TON TRAVAIL — Humaniser cette annonce en respectant ces regles STRICTES:\n\n"
        "1. INTRO (3-4 phrases au debut):\n"
        "   Ajoute une intro percutante, quebecoise, passionnee, specifique au vehicule.\n"
        "   Pas de cliches, pas de vulgarite. Professionnel mais passionne.\n"
        "   ABSOLUMENT AUCUN mot vulgaire, grossier ou a caractere sexuel.\n"
        "   JAMAIS de 'sillonner', 'dominer', 'Beauce', 'routes de la Beauce' dans l'intro.\n\n"
        "2. TITRE:\n"
        "   Remplace SEULEMENT la premiere ligne (titre entre emojis) par un titre plus vendeur.\n\n"
        "3. OPTIONS — Structure STRICTE:\n"
        "   ✅ = OPTIONS PRINCIPALES en MAJUSCULES humanisees\n"
        "   ▫️ = sous-options en minuscules, en retrait\n"
        "   NE SUPPRIME AUCUNE LIGNE. Chaque ✅ et ▫️ doit rester.\n"
        "   Traduis les noms techniques en francais lisible.\n\n"
        "4. TOUT apres le lien sticker (footer, Daniel Giroux, hashtags) = COPIE EXACTE.\n\n"
        "NE RAJOUTE RIEN a la fin."
    )

    user_prompt = f"Humanise cette annonce:\n\n{raw_text}"
    if ctx_info:
        user_prompt += f"\n\nINFOS VEHICULE:\n{ctx_info}"
    if vin_specs_text:
        user_prompt += f"\n\nSPECS VIN (NHTSA):\n{vin_specs_text}"

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
            max_tokens=2000,
        )
        text = response.choices[0].message.content.strip()

        # Couper tout après les hashtags si l'IA a rajouté du texte
        lines = text.split("\n")
        output = []
        for line in lines:
            output.append(line)
            if line.strip().startswith("#") and "DanielGiroux" in line:
                break
        text = "\n".join(output).strip()

        # Filtre anti-vulgarité
        vulgar = ["couilles", "balls", "badass", "bitch", "cul ", "merde",
                  "crisse", "tabarnac", "calisse", "ostie", "fuck", "shit"]
        for vw in vulgar:
            if vw in text.lower():
                text_lines = text.split("\n")
                text = "\n".join(l for l in text_lines if vw not in l.lower())

        return text.strip()

    except Exception as e:
        print(f"[HUMANIZE_STICKER ERROR] stock={stock} err={e}", flush=True)
        return ""



def _build_ad_text(
    sb,
    run_id: str,
    slug: str,
    v: Dict[str, Any],
    event: str,
    old_price: Any = None,
    new_price: Any = None,
) -> str:
    vin = (v.get("vin") or "").strip().upper()
    stock = (v.get("stock") or "").strip().upper()
    title = (v.get("title") or "").strip()
    url = (v.get("url") or "").strip()
    price = _vehicle_price_text(v)
    mileage = _vehicle_mileage_text(v)

    # enrichit v pour que l'AI puisse comprendre un PRICE_CHANGED si besoin
    v_ai = dict(v or {})
    v_ai["old_price"] = old_price
    v_ai["new_price"] = new_price

    # ── Décodage VIN via NHTSA (pour tous les véhicules) ──
    vin_specs_text = ""
    if decode_vin is not None and len(vin) >= 11:
        try:
            vin_specs = decode_vin(vin)
            if vin_specs and format_specs_for_prompt is not None:
                vin_specs_text = format_specs_for_prompt(vin_specs)
                if vin_specs_text:
                    print(f"[VIN_DECODE OK] slug={slug} vin={vin} specs={len(vin_specs_text)} chars", flush=True)
        except Exception as e:
            print(f"[VIN_DECODE FAIL] slug={slug} vin={vin} err={e}", flush=True)

    # ── Récupérer le texte des options sticker pour Stellantis ──
    sticker_raw_text = ""
    sticker_options_text = ""
    is_stellantis = _is_stellantis_vin(vin)
    is_forced_sticker = _is_stellantis_2018_plus(v)  # 2018+ = FORCER le PDF
    
    if USE_STICKER_AD and is_stellantis:
        # D'abord, essayer de récupérer le sticker déjà en base (base_text du post existant)
        existing_sticker = ""
        try:
            existing_post = sb.table("posts").select("base_text").eq("stock", stock).limit(1).execute()
            if existing_post.data:
                bt = (existing_post.data[0].get("base_text") or "")
                if ("ACCESSOIRES" in bt or "Window Sticker" in bt or "✅" in bt) and len(bt) > 200:
                    existing_sticker = bt
        except Exception:
            pass

        # Récupérer le PDF (cache Supabase ou Chrysler.com)
        try:
            res = ensure_sticker_cached(sb, vin, run_id)
            if (res.get("status") or "").lower() == "ok":
                # Utiliser les bytes retournés directement (évite double téléchargement)
                pdf_bytes = res.get("pdf_bytes") or b""
                if not pdf_bytes:
                    # Fallback: re-télécharger si les bytes ne sont pas dans la réponse
                    pdf_bytes = sb.storage.from_(STICKERS_BUCKET).download(res["path"])
                
                options = _extract_options_from_sticker_bytes(pdf_bytes)
                if options:
                    opt_lines = []
                    for grp in options:
                        opt_lines.append(grp.get("title", ""))
                        for d in grp.get("details", []):
                            opt_lines.append(f"  - {d}")
                    sticker_options_text = "\n".join(opt_lines)

                    sticker_raw_text = build_ad_from_options(
                        title=title,
                        price=price,
                        mileage=mileage,
                        stock=stock,
                        vin=vin,
                        options=options,
                        vehicle_url=url,
                    )
                    print(f"[STICKER OK] slug={slug} vin={vin} options={len(options)} groups, text={len(sticker_raw_text)} chars", flush=True)
                else:
                    print(f"[STICKER NO OPTIONS] slug={slug} vin={vin} pdf_size={len(pdf_bytes)} - extraction returned 0 groups", flush=True)
            else:
                reason = res.get('reason', 'unknown')
                if is_forced_sticker:
                    print(f"[STICKER FORCED MISS] slug={slug} vin={vin} year=2018+ status={res.get('status')} reason={reason} — PDF requis mais indisponible!", flush=True)
                else:
                    print(f"[STICKER UNAVAIL] slug={slug} vin={vin} status={res.get('status')} reason={reason}", flush=True)
        except Exception as e:
            print(f"[STICKER FETCH] slug={slug} vin={vin} err={e}", flush=True)

        # Fallback: utiliser le texte sticker existant en base si le PDF n'a pas marché
        if not sticker_raw_text and existing_sticker:
            sticker_raw_text = existing_sticker
            print(f"[STICKER FALLBACK] Using existing base_text for slug={slug} ({len(existing_sticker)} chars)", flush=True)

    # ══════════════════════════════════════════════════════════════
    # PRIORITE 1 : Stellantis avec sticker → humanisation IA
    # ══════════════════════════════════════════════════════════════
    if USE_AI and sticker_raw_text and generate_smart_text_v3 is not None:
        try:
            # Ajouter le footer au texte brut avant humanisation
            raw_with_footer = _ensure_contact_footer(sticker_raw_text)

            # Humaniser le texte sticker complet via llm_v3
            humanized = _humanize_sticker_text(
                raw_with_footer, v_ai, event, vin_specs_text
            )
            if humanized and len(humanized) >= MIN_POST_TEXT_LEN:
                print(f"[STICKER+AI OK] slug={slug} stock={stock} chars={len(humanized)}", flush=True)
                return humanized
            elif humanized:
                print(f"[STICKER+AI SHORT] slug={slug} chars={len(humanized)}, fallback raw sticker", flush=True)
        except Exception as e:
            print(f"[STICKER+AI FAIL] slug={slug} err={e}, fallback", flush=True)

        # Fallback: sticker brut + ancienne intro AI
        txt = _maybe_add_ai_intro(v_ai, sticker_raw_text)
        if event == "PRICE_CHANGED":
            intro = _price_changed_intro_variant2(title, old_price, new_price)
            if intro:
                txt = intro + "\n\n" + txt
        return _ensure_contact_footer(txt)

    # ══════════════════════════════════════════════════════════════
    # PRIORITE 2 : llm_v3 (génération intelligente avec VIN)
    # ══════════════════════════════════════════════════════════════
    if USE_AI and generate_smart_text_v3 is not None:
        try:
            # Enrichir le vehicule avec les specs VIN pour le prompt
            if vin_specs_text:
                v_ai["_vin_specs_text"] = vin_specs_text

            smart_text = generate_smart_text_v3(
                vehicle=v_ai,
                event=event,
                options_text=sticker_options_text,
                old_price=old_price,
                new_price=new_price,
            )
            if smart_text and len(smart_text) >= MIN_POST_TEXT_LEN:
                print(f"[LLM_V3 OK] slug={slug} stock={stock} event={event} chars={len(smart_text)}", flush=True)
                return _ensure_contact_footer(smart_text)
            elif smart_text:
                print(f"[LLM_V3 SHORT] slug={slug} chars={len(smart_text)} < min={MIN_POST_TEXT_LEN}, fallback", flush=True)
        except Exception as e:
            print(f"[LLM_V3 FAIL] slug={slug} stock={stock} err={e}, fallback", flush=True)

    # ══════════════════════════════════════════════════════════════
    # PRIORITE 3 : StickerToAd brut (ancien pipeline sans AI)
    # ══════════════════════════════════════════════════════════════
    if sticker_raw_text:
        txt = _maybe_add_ai_intro(v_ai, sticker_raw_text)
        if event == "PRICE_CHANGED":
            intro = _price_changed_intro_variant2(title, old_price, new_price)
            if intro:
                txt = intro + "\n\n" + txt
        return _ensure_contact_footer(txt)

    # ══════════════════════════════════════════════════════════════
    # PRIORITE 4 : Fallback text engine externe
    # ══════════════════════════════════════════════════════════════
    payload = dict(v or {})
    payload.update(
        {
            "title": title,
            "stock": stock,
            "vin": vin,
            "url": url,
            "price": price,
            "mileage": mileage,
            "old_price": old_price,
            "new_price": new_price,
        }
    )

    if event == "PRICE_CHANGED":
        payload["sales_angle"] = (
            "Annonce une baisse de prix avec un ton vendeur humain, énergique et naturel. "
            "Mentionne clairement l'ancien prix puis le nouveau prix. "
            "Fais sentir l'opportunité sans être agressif."
        )

    txt = generate_facebook_text(TEXT_ENGINE_URL, slug, event, payload)
    txt = (txt or "").strip()

    # AI intro (ancien llm.py) pour enrichir le texte du text engine
    txt = _maybe_add_ai_intro(v_ai, txt)

    # Hook promo spécial baisse de prix
    if event == "PRICE_CHANGED":
        intro = _price_changed_intro_variant2(title, old_price, new_price)
        if intro:
            txt = intro + "\n\n" + txt

    return _ensure_contact_footer(txt)


def rebuild_posts_map(limit: int = 2000, cooldown_days: int = 7) -> Dict[str, Dict[str, Any]]:
    sb = get_client(SUPABASE_URL, SUPABASE_KEY)
    cut = datetime.now(timezone.utc) - timedelta(days=cooldown_days)

    rows = (
        sb.table("posts")
        .select("stock,post_id,published_at,last_updated_at,status")
        .eq("status", "ACTIVE")
        .order("last_updated_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )

    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        stock = (r.get("stock") or "").strip().upper()
        post_id = (r.get("post_id") or "").strip()
        published_at = (
            (r.get("published_at") or "").strip()
            or (r.get("last_updated_at") or "").strip()
        )

        if not stock or not post_id or not published_at:
            continue

        try:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        if dt < cut:
            continue

        if stock not in out:
            out[stock] = {
                "post_id": post_id,
                "published_at": published_at,
            }

    return out


# -------------------------
# MAIN
# -------------------------
def main() -> None:
    sb = get_client(SUPABASE_URL, SUPABASE_KEY)

    run_id = _run_id()
    now = utc_now_iso()

    inv_db = get_inventory_map(sb)
    posts_db = get_posts_map(sb)

    page_urls = [
        f"{BASE_URL}{INVENTORY_PATH}",
        f"{BASE_URL}{INVENTORY_PATH}?page=2",
        f"{BASE_URL}{INVENTORY_PATH}?page=3",
    ]

    detail_urls: List[str] = []
    for url in page_urls:
        try:
            html = fetch_html(SESSION, url, timeout=30)
            detail_urls += parse_inventory_listing_urls(BASE_URL, INVENTORY_PATH, html)
        except Exception as e:
            print(f"[WARN] fetch listing failed url={url} err={e}", flush=True)

    detail_urls = list(dict.fromkeys(detail_urls))
    if not detail_urls:
        print("[WARN] No detail urls found. Abort.", flush=True)
        return

    current: Dict[str, Dict[str, Any]] = {}
    for u in detail_urls:
        try:
            v = parse_vehicle_detail_simple(SESSION, u)
            stock = (v.get("stock") or "").strip().upper()
            title = (v.get("title") or "").strip()
            if not stock or not title:
                continue

            slug = slugify(title, stock)
            v["slug"] = slug
            current[slug] = v
        except Exception as e:
            print(f"[WARN] parse vehicle failed url={u} err={e}", flush=True)

    if not current:
        print("[WARN] No vehicles parsed. Abort.", flush=True)
        return

    # Enregistrer le run MAINTENANT (avant le pré-cache qui a besoin du run_id en FK)
    try:
        from supabase_db import upsert_scrape_run
        upsert_scrape_run(sb, run_id, status="RUNNING", note=f"inv_count={len(current)}")
        print(f"[RUN] scrape_run created: {run_id}", flush=True)
    except Exception as e:
        print(f"[RUN] scrape_run insert failed: {e} (non-bloquant)", flush=True)

    # =========================================================
    # PRÉ-CACHE: Forcer le téléchargement des PDFs Stellantis 2018+
    # =========================================================
    stellantis_2018_vins = []
    for slug, v in current.items():
        if _is_stellantis_2018_plus(v):
            vin = (v.get("vin") or "").strip().upper()
            if vin and len(vin) == 17:
                stellantis_2018_vins.append((slug, vin))

    if stellantis_2018_vins:
        print(f"[STICKER PRECACHE] {len(stellantis_2018_vins)} véhicules Stellantis 2018+ détectés, vérification des PDFs...", flush=True)
        cached_ok = 0
        cached_new = 0
        cached_fail = 0
        for slug, vin in stellantis_2018_vins:
            try:
                res = ensure_sticker_cached(sb, vin, run_id)
                status = (res.get("status") or "").lower()
                source = res.get("source", "")
                if status == "ok":
                    if source == "cache_ok":
                        cached_ok += 1
                    else:
                        cached_new += 1
                        print(f"[STICKER PRECACHE NEW] vin={vin} slug={slug} source={source}", flush=True)
                else:
                    cached_fail += 1
                    print(f"[STICKER PRECACHE FAIL] vin={vin} slug={slug} reason={res.get('reason')}", flush=True)
            except Exception as e:
                cached_fail += 1
                print(f"[STICKER PRECACHE ERROR] vin={vin} slug={slug} err={e}", flush=True)
        print(
            f"[STICKER PRECACHE DONE] total={len(stellantis_2018_vins)} "
            f"cache_hit={cached_ok} new_download={cached_new} fail={cached_fail}",
            flush=True,
        )

    new_slugs = [s for s in current if s not in inv_db]

    price_changed: List[str] = []
    for slug in (set(current) & set(inv_db)):
        old = inv_db.get(slug) or {}
        new = current.get(slug) or {}

        old_p = old.get("price_int")
        new_p = new.get("price_int")

        if isinstance(old_p, int) and isinstance(new_p, int):
            if abs(old_p - new_p) > PRICE_CHANGE_THRESHOLD:
                price_changed.append(slug)

    # =========================================================
    # PHOTOS_ADDED - Détection multi-méthodes
    # =========================================================
    photos_added: List[str] = []
    if REFRESH_NO_PHOTO_DAILY:
        for slug in (set(current) & set(posts_db)):
            post_data = posts_db.get(slug) or {}
            v = current.get(slug) or {}

            # Photos actuellement disponibles sur le site Kennebec
            current_photos = v.get("photos") or []
            nb_kennebec = len(current_photos)

            # Pas de photos sur Kennebec → rien à faire
            if nb_kennebec == 0:
                continue

            # Photo count stocké en DB (ce qu'on avait lors de la publication FB)
            photo_count_db = post_data.get("photo_count", None)
            has_no_photo_flag = post_data.get("no_photo", None)

            # ── Méthode 5 (PRINCIPALE): Comparer photos FB vs Kennebec ──
            # Si FB a 0 ou 1 photo ET Kennebec a > 1 → c'est un NO_PHOTO à updater
            if isinstance(photo_count_db, int) and photo_count_db <= 1 and nb_kennebec > 1:
                photos_added.append(slug)
                print(
                    f"[PHOTOS_ADDED DETECT] slug={slug} "
                    f"fb_photos={photo_count_db} kennebec_photos={nb_kennebec} "
                    f"method=FB_VS_KENNEBEC",
                    flush=True,
                )
                continue

            # ── Méthode 1: Flag no_photo explicite ──
            if has_no_photo_flag is True:
                photos_added.append(slug)
                print(
                    f"[PHOTOS_ADDED DETECT] slug={slug} "
                    f"no_photo_flag=True kennebec_photos={nb_kennebec} "
                    f"method=NO_PHOTO_FLAG",
                    flush=True,
                )
                continue

            # ── Méthode 2: Indices texte dans le base_text ──
            base_text = (post_data.get("base_text") or "").lower()
            text_has_no_photo_hint = (
                "photos suivront" in base_text or
                "photo non disponible" in base_text or
                "nouveau véhicule en inventaire" in base_text or
                "no_photo" in base_text or
                "sans photo" in base_text or
                "photo à venir" in base_text or
                "photos à venir" in base_text
            )
            if text_has_no_photo_hint:
                photos_added.append(slug)
                print(
                    f"[PHOTOS_ADDED DETECT] slug={slug} "
                    f"kennebec_photos={nb_kennebec} "
                    f"method=TEXT_HINT",
                    flush=True,
                )
                continue

            # ── Méthode 3: Anciennes entrées sans photo_count (NULL en DB) ──
            # Si photo_count est NULL et le post existe → vérifier si Kennebec a beaucoup de photos
            if photo_count_db is None and nb_kennebec > 5:
                # Probablement un ancien post sans tracking → vérifier le post n'a pas été
                # mis à jour récemment pour éviter une boucle
                last_updated = post_data.get("last_updated_at") or post_data.get("published_at") or ""
                skip_this = False
                if last_updated:
                    try:
                        from datetime import datetime as _dt, timezone as _tz
                        upd = _dt.fromisoformat(last_updated.replace("Z", "+00:00"))
                        hours_ago = (datetime.now(_tz.utc) - upd).total_seconds() / 3600
                        if hours_ago < 48:
                            skip_this = True
                    except Exception:
                        pass

                if not skip_this:
                    photos_added.append(slug)
                    print(
                        f"[PHOTOS_ADDED DETECT] slug={slug} "
                        f"photo_count=NULL kennebec_photos={nb_kennebec} "
                        f"method=NULL_COUNT_MANY_PHOTOS",
                        flush=True,
                    )

    print(f"[REFRESH_NO_PHOTO] {len(photos_added)} posts à mettre à jour avec photos (limit={REFRESH_NO_PHOTO_LIMIT})", flush=True)

    # =========================================================
    # VENDU / SOLD — Posts FB dont le véhicule a disparu du site
    # =========================================================
    sold_slugs: List[str] = []
    posts_in_db_not_in_site = set(posts_db.keys()) - set(current.keys())
    for slug in posts_in_db_not_in_site:
        post_data = posts_db.get(slug) or {}
        post_status = (post_data.get("status") or "").upper()
        post_id = (post_data.get("post_id") or "").strip()

        # Skip si déjà marqué SOLD ou pas de post_id
        if post_status == "SOLD" or not post_id:
            continue

        # Skip si le post est très récent (< 2 jours) — possible erreur de scrape
        published_at = post_data.get("published_at") or ""
        if published_at:
            try:
                from datetime import datetime as _dt, timezone as _tz
                pub = _dt.fromisoformat(published_at.replace("Z", "+00:00"))
                age_days = (datetime.now(_tz.utc) - pub).days
                if age_days < 2:
                    continue
            except Exception:
                pass

        sold_slugs.append(slug)

    print(f"[SOLD DETECT] {len(sold_slugs)} posts à marquer VENDU", flush=True)

    targets: List[Tuple[str, str]] = (
        [(s, "PHOTOS_ADDED") for s in photos_added[:REFRESH_NO_PHOTO_LIMIT]]
        + [(s, "PRICE_CHANGED") for s in price_changed]
        + [(s, "NEW") for s in new_slugs]
        + [(s, "SOLD") for s in sold_slugs]
    )

    if not targets:
        print(f"OK run_id={run_id} inv_count={len(current)} NEW=0 PRICE_CHANGED=0 PHOTOS_ADDED=0 SOLD=0", flush=True)
        _run_meta_compare_safe()
        return

    posts_map = rebuild_posts_map(limit=2000, cooldown_days=POST_COOLDOWN_DAYS)

    posted = 0
    updated = 0
    sold_count = 0
    skipped_dup = 0
    skipped_bad_text = 0
    skipped_no_photos = 0

    for slug, event in targets[:MAX_TARGETS]:
        v = current.get(slug) or {}
        stock = (v.get("stock") or "").strip().upper()

        # =========================================================
        # SOLD — Marquer le post Facebook comme VENDU
        # =========================================================
        if event == "SOLD":
            old_post = posts_db.get(slug) or {}
            post_id = (old_post.get("post_id") or "").strip()
            old_stock = (old_post.get("stock") or "").strip().upper()

            if not post_id:
                continue

            # Construire le message VENDU
            sold_prefix = (
                "🚨 VENDU 🚨\n\n"
                "Ce véhicule n'est plus disponible.\n\n"
                "👉 Vous recherchez un véhicule semblable ?\n"
                "Contactez-moi directement, je peux vous aider à en trouver un rapidement.\n\n"
                "Daniel Giroux\n"
                "📞 418-222-3939\n"
                "────────────────────\n\n"
            )

            # Récupérer le texte original et le préfixer avec VENDU
            base_text = old_post.get("base_text") or ""
            # Enlever un ancien préfixe VENDU si déjà présent (éviter doublon)
            if "🚨 VENDU 🚨" in base_text:
                base_text = base_text.split("────────────────────\n\n", 1)[-1]
            sold_message = sold_prefix + base_text

            try:
                update_post_text(post_id, FB_TOKEN, sold_message)

                upsert_post(
                    sb,
                    {
                        "slug": slug,
                        "post_id": post_id,
                        "status": "SOLD",
                        "sold_at": now,
                        "last_updated_at": now,
                        "base_text": sold_message,
                        "stock": old_stock,
                    },
                )

                sold_count += 1
                print(
                    f"[SOLD] ✅ slug={slug} stock={old_stock} post_id={post_id}",
                    flush=True,
                )
                log_event(sb, slug, "MARKED_SOLD", {
                    "run_id": run_id,
                    "post_id": post_id,
                    "stock": old_stock,
                })
                time.sleep(max(1, SLEEP_BETWEEN))

            except Exception as e:
                print(f"[ERROR SOLD] slug={slug} err={e}", flush=True)
                log_event(sb, slug, "SOLD_ERROR", {"err": str(e), "run_id": run_id})

            continue

        if not stock:
            continue

        if event == "NEW" and stock in posts_map:
            last_time = posts_map[stock].get("published_at")
            print(
                f"[ANTI-DUPLICATE] Skip stock={stock} recent_post={last_time} (cooldown={POST_COOLDOWN_DAYS}d)",
                flush=True,
            )
            skipped_dup += 1
            continue

        try:
            if event == "PRICE_CHANGED":
                old = inv_db.get(slug) or {}
                msg = _build_ad_text(
                    sb,
                    run_id,
                    slug,
                    v,
                    event="PRICE_CHANGED",
                    old_price=old.get("price_int"),
                    new_price=v.get("price_int"),
                ).strip()
            else:
                msg = _build_ad_text(
                    sb,
                    run_id,
                    slug,
                    v,
                    event="NEW",
                ).strip()

        except Exception as e:
            print(f"[TEXT ERROR] slug={slug} event={event} err={e}", flush=True)
            log_event(sb, slug, "TEXT_ERROR", {"err": str(e), "run_id": run_id, "event": event})
            continue

        if not msg or len(msg) < MIN_POST_TEXT_LEN:
            print(f"[SKIP BAD TEXT] slug={slug} event={event} len={len(msg)}", flush=True)
            log_event(
                sb,
                slug,
                "SKIP_BAD_TEXT",
                {"event": event, "text_len": len(msg), "min_len": MIN_POST_TEXT_LEN, "run_id": run_id},
            )
            skipped_bad_text += 1
            continue

        if event == "PRICE_CHANGED":
            old = inv_db.get(slug) or {}
            old_post = posts_db.get(slug) or {}
            post_id = (old_post.get("post_id") or "").strip()

            if not post_id:
                print(f"[PRICE_CHANGED] no post_id for slug={slug}, skip update", flush=True)
                log_event(sb, slug, "PRICE_CHANGED_SKIP_NO_POST", {"run_id": run_id})
                continue

            try:
                update_post_text(post_id, FB_TOKEN, msg)

                upsert_post(
                    sb,
                    {
                        "slug": slug,
                        "post_id": post_id,
                        "status": "ACTIVE",
                        "published_at": old_post.get("published_at") or now,
                        "last_updated_at": now,
                        "base_text": msg,
                        "stock": stock,
                    },
                )

                updated += 1
                print(
                    f"[UPDATED] PRICE_CHANGED slug={slug} stock={stock} "
                    f"old_price={old.get('price_int')} new_price={v.get('price_int')} "
                    f"post_id={post_id}",
                    flush=True,
                )
                time.sleep(max(1, SLEEP_BETWEEN))

            except Exception as e:
                print(f"[ERROR UPDATE] slug={slug} err={e}", flush=True)
                log_event(sb, slug, "PRICE_UPDATE_ERROR", {"err": str(e), "run_id": run_id})

            continue

        # =========================================================
        # FIX #2: PHOTOS_ADDED - Réutiliser msg, publier correctement
        # =========================================================
        if event == "PHOTOS_ADDED":
            old_post = posts_db.get(slug) or {}
            old_post_id = (old_post.get("post_id") or "").strip()

            # Réutiliser msg déjà généré et validé (plus de double _build_ad_text!)
            base_text = msg

            if not old_post_id:
                # Post reseté (post_id vide) — publier comme un NEW
                print(f"[PHOTOS_ADDED→NEW] no post_id for slug={slug}, publishing as NEW", flush=True)
                photos = _download_photos(sb, stock, v.get("photos") or [], limit=MAX_PHOTOS)
                if not photos:
                    skipped_no_photos += 1
                    continue
                try:
                    media_ids = publish_photos_unpublished(
                        FB_PAGE_ID, FB_TOKEN, photos[:POST_PHOTOS], limit=POST_PHOTOS,
                    )
                    new_post_id = create_post_with_attached_media(FB_PAGE_ID, FB_TOKEN, base_text, media_ids)

                    upsert_post(sb, {
                        "slug": slug, "post_id": new_post_id, "status": "ACTIVE",
                        "published_at": now, "last_updated_at": now,
                        "base_text": base_text, "no_photo": False,
                        "photo_count": len(photos[:POST_PHOTOS]), "stock": stock,
                    })
                    posted += 1
                    print(f"[NEW from reset] ✅ slug={slug} stock={stock} post_id={new_post_id} photos={len(photos)}", flush=True)
                    log_event(sb, slug, "NEW_FROM_RESET", {"run_id": run_id, "post_id": new_post_id, "photo_count": len(photos)})
                    time.sleep(max(1, SLEEP_BETWEEN))
                except Exception as e:
                    print(f"[ERROR NEW_RESET] slug={slug} err={e}", flush=True)
                continue

            photos = _download_photos(sb, stock, v.get("photos") or [], limit=MAX_PHOTOS)
            if not photos or _is_no_photo_fallback(photos):
                print(f"[PHOTOS_ADDED] still no real photos for slug={slug}, skip", flush=True)
                continue

            try:
                # 1. Supprimer l'ancien post (avec l'image NO PHOTO)
                deleted = delete_post(old_post_id, FB_TOKEN)
                if deleted:
                    print(f"[PHOTOS_ADDED] Deleted old post {old_post_id} for slug={slug}", flush=True)
                else:
                    print(f"[PHOTOS_ADDED] Warning: Could not delete old post {old_post_id}, continuing anyway", flush=True)

                # 2. Créer le nouveau post avec les vraies photos (msg déjà prêt)
                media_ids = publish_photos_unpublished(
                    FB_PAGE_ID,
                    FB_TOKEN,
                    photos[:POST_PHOTOS],
                    limit=POST_PHOTOS,
                )
                new_post_id = create_post_with_attached_media(FB_PAGE_ID, FB_TOKEN, base_text, media_ids)

                # Mettre à jour la DB avec le nouveau post_id
                upsert_post(
                    sb,
                    {
                        "slug": slug,
                        "post_id": new_post_id,  # NOUVEAU post_id!
                        "status": "ACTIVE",
                        "published_at": now,  # Nouvelle date de publication
                        "last_updated_at": now,
                        "base_text": base_text,
                        "no_photo": False,  # Maintenant il a de vraies photos
                        "photo_count": len(photos),
                        "stock": stock,
                    },
                )

                updated += 1
                print(
                    f"[PHOTOS_ADDED] ✅ slug={slug} stock={stock} "
                    f"old_post={old_post_id} → new_post={new_post_id} "
                    f"photos={len(photos)}",
                    flush=True,
                )
                log_event(sb, slug, "PHOTOS_ADDED_SUCCESS", {
                    "run_id": run_id,
                    "old_post_id": old_post_id,
                    "new_post_id": new_post_id,
                    "photo_count": len(photos),
                })
                time.sleep(max(1, SLEEP_BETWEEN))

            except Exception as e:
                print(f"[ERROR PHOTOS_ADDED] slug={slug} err={e}", flush=True)
                log_event(sb, slug, "PHOTOS_ADDED_ERROR", {"err": str(e), "run_id": run_id})

            continue

        # =========================================================
        # NEW POST - Avec FIX #1: Détecter le fallback NO_PHOTO
        # =========================================================
        photos = _download_photos(sb, stock, v.get("photos") or [], limit=MAX_PHOTOS)
        if not photos:
            print(f"[SKIP NO PHOTOS] slug={slug} stock={stock}", flush=True)
            log_event(sb, slug, "SKIP_NO_PHOTOS", {"run_id": run_id})
            skipped_no_photos += 1
            continue

        # FIX #1: Détecter si on utilise le fallback NO_PHOTO
        using_no_photo_fallback = _is_no_photo_fallback(photos)
        if using_no_photo_fallback:
            print(f"[NO_PHOTO POST] slug={slug} stock={stock} - Post créé avec image placeholder", flush=True)

        try:
            media_ids = publish_photos_unpublished(
                FB_PAGE_ID,
                FB_TOKEN,
                photos[:POST_PHOTOS],
                limit=POST_PHOTOS,
            )
            post_id = create_post_with_attached_media(FB_PAGE_ID, FB_TOKEN, msg, media_ids)

            # FIX #1: Mettre no_photo=True et photo_count=0 si fallback utilisé
            upsert_post(
                sb,
                {
                    "slug": slug,
                    "post_id": post_id,
                    "status": "ACTIVE",
                    "published_at": now,
                    "last_updated_at": now,
                    "base_text": msg,
                    "stock": stock,
                    "no_photo": using_no_photo_fallback,  # FIX: True si fallback, False si vraies photos
                    "photo_count": 0 if using_no_photo_fallback else len(photos),  # FIX: 0 si fallback
                },
            )

            posts_map[stock] = {"post_id": post_id, "published_at": now}
            posted += 1
            print(f"[POSTED] NEW slug={slug} stock={stock} post_id={post_id} no_photo={using_no_photo_fallback}", flush=True)
            time.sleep(max(1, SLEEP_BETWEEN))

        except Exception as e:
            print(f"[ERROR POST] slug={slug} event={event} err={e}", flush=True)
            log_event(sb, slug, "POST_ERROR", {"err": str(e), "run_id": run_id})
            continue

    print(
        f"OK run_id={run_id} inv_count={len(current)} "
        f"NEW={len(new_slugs)} PRICE_CHANGED={len(price_changed)} PHOTOS_ADDED={len(photos_added)} SOLD={len(sold_slugs)} "
        f"posted={posted} updated={updated} sold={sold_count} skipped_dup={skipped_dup} "
        f"skipped_bad_text={skipped_bad_text} skipped_no_photos={skipped_no_photos}",
        flush=True,
    )

    _run_meta_compare_safe()

if __name__ == "__main__":
    main()
```

---

## FILE: supabase_db.py
```python
import os
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client, Client
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json
import hashlib


# =========================
# Time
# =========================
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =========================
# Client
# =========================
def get_client(url: str | None = None, key: str | None = None) -> Client:
    url = (url or os.getenv("SUPABASE_URL") or "").strip()
    key = (key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

    base = url.rstrip("/")
    sb = create_client(base, key)

    # Force le endpoint Storage avec slash (évite le warning)
    try:
        sb.storage_url = f"{base}/storage/v1/"
    except Exception:
        pass

    return sb

# =========================
# Core tables: inventory / posts / events
# =========================
def upsert_inventory(sb: Client, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    cleaned: List[Dict[str, Any]] = []
    for r in rows:
        st = (r.get("stock") or "").strip().upper()
        if not st:
            continue  # pas de stock => on skip (sinon on casse l'unicité)
        r["stock"] = st

        # slug utile mais pas clé; on le garde propre
        if r.get("slug"):
            r["slug"] = str(r["slug"]).strip()

        cleaned.append(r)

    if not cleaned:
        return

    # ✅ maintenant que DB a UNIQUE(stock), on upsert sur stock
    sb.table("inventory").upsert(cleaned, on_conflict="stock").execute()


def get_inventory_map(sb: Client) -> Dict[str, Dict[str, Any]]:
    res = sb.table("inventory").select("*").execute()
    data = res.data or []
    return {r["slug"]: r for r in data if r.get("slug")}


from postgrest.exceptions import APIError

def upsert_post(sb: Client, row: Dict[str, Any]) -> None:
    if not row:
        return

    stock = (row.get("stock") or "").strip().upper()
    slug = (row.get("slug") or "").strip()

    if not stock:
        raise ValueError("upsert_post: stock obligatoire")

    row["stock"] = stock
    row["slug"] = slug or None

    # Upsert on slug (PRIMARY KEY) — si le slug existe, on update
    try:
        sb.table("posts").upsert(
            row,
            on_conflict="slug"
        ).execute()
    except Exception as e:
        err_msg = str(e)
        if "23505" in err_msg or "duplicate key" in err_msg.lower():
            # Conflit stock unique — update par slug (PK)
            try:
                update_row = {k: v for k, v in row.items()}
                sb.table("posts").update(update_row).eq("slug", slug).execute()
            except Exception as e2:
                print(f"[UPSERT_POST FALLBACK] slug={slug} stock={stock} err={e2}", flush=True)
                # Dernier recours: update seulement les champs critiques par slug
                try:
                    sb.table("posts").update({
                        "post_id": row.get("post_id"),
                        "status": row.get("status"),
                        "base_text": row.get("base_text"),
                        "last_updated_at": row.get("last_updated_at"),
                        "no_photo": row.get("no_photo"),
                        "photo_count": row.get("photo_count"),
                    }).eq("slug", slug).execute()
                except Exception as e3:
                    print(f"[UPSERT_POST LAST_RESORT] slug={slug} err={e3}", flush=True)
        else:
            raise


def get_posts_map(sb: Client) -> Dict[str, Dict[str, Any]]:
    res = sb.table("posts").select("*").execute()
    data = res.data or []
    return {r["slug"]: r for r in data if r.get("slug")}


def log_event(sb: Client, slug: str, typ: str, payload: Dict[str, Any]) -> None:
    sb.table("events").insert({"slug": slug, "type": typ, "payload": payload}).execute()


# =========================
# Mémoire tables (ALIGNED to your schema)
# =========================
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def upsert_scrape_run(sb: Client, run_id: str, status: str = "OK", note: str = "") -> None:
    """
    scrape_runs:
      run_id (text, NOT NULL)
      created_at (timestamptz, NOT NULL)
      status (text, NOT NULL)
      note (text, nullable)
    """
    sb.table("scrape_runs").upsert(
        {
            "run_id": run_id,
            "created_at": utc_now_iso(),
            "status": status,
            "note": (note or None),
        },
        on_conflict="run_id",
    ).execute()


def upsert_raw_page(sb: Client, run_id: str, page_no: int, storage_path: str, data: bytes) -> None:
    """
    raw_pages:
      run_id (text, NOT NULL)
      page_no (int4, NOT NULL)
      storage_path (text, NOT NULL)
      bytes (int4, NOT NULL)
      sha256 (text, NOT NULL)
    """
    sb.table("raw_pages").upsert(
        {
            "run_id": run_id,
            "page_no": int(page_no),
            "storage_path": storage_path,
            "bytes": len(data or b""),
            "sha256": sha256_hex(data or b""),
        },
        on_conflict="run_id,page_no",
    ).execute()


def upsert_sticker_pdf(
    sb: Client,
    vin: str,
    status: str,
    storage_path: str,
    data: bytes,
    reason: str = "",
    run_id: str = "",
) -> None:
    """
    sticker_pdfs:
      vin (text, NOT NULL)
      status (text, NOT NULL)
      storage_path (text, NOT NULL)
      bytes (int4, NOT NULL)
      sha256 (text, NOT NULL)
      reason (text, nullable)
      run_id (text, nullable)
      updated_at (timestamptz, NOT NULL)
    """
    sb.table("sticker_pdfs").upsert(
        {
            "vin": (vin or "").strip().upper(),
            "status": status,
            "storage_path": storage_path,
            "bytes": len(data or b""),
            "sha256": sha256_hex(data or b""),
            "reason": (reason or None),
            "run_id": (run_id or None),
            "updated_at": utc_now_iso(),
        },
        on_conflict="vin",
    ).execute()


def upsert_output(
    sb: Client,
    stock: str,
    kind: str,
    facebook_path: str,
    marketplace_path: str,
    run_id: str = "",
) -> None:
    sb.table("outputs").upsert(
        {
            "stock": (stock or "").strip().upper(),
            "kind": (kind or "").strip(),
            "facebook_path": facebook_path,
            "marketplace_path": marketplace_path,
            "run_id": run_id or None,
            "updated_at": utc_now_iso(),
        },
        on_conflict="stock,kind",
    ).execute()

# =========================
# Storage helpers (RESTORED)
# =========================
import json
from typing import Any, Optional, List


def upload_bytes_to_storage(
    sb,
    bucket: str,
    path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    upsert: bool = True,
) -> None:
    bucket = (bucket or "").strip()
    path = (path or "").lstrip("/")
    if not bucket or not path:
        raise ValueError("upload_bytes_to_storage: missing bucket/path")

    sb.storage.from_(bucket).upload(
        path,
        data,
        file_options={
            "content-type": content_type,
            "upsert": "true" if upsert else "false",  # IMPORTANT: str, pas bool
        },
    )


def upload_json_to_storage(
    sb,
    bucket: str,
    path: str,
    obj: Any,
    upsert: bool = True,
) -> None:
    b = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    upload_bytes_to_storage(
        sb,
        bucket,
        path,
        b,
        content_type="application/json; charset=utf-8",
        upsert=upsert,
    )


def read_json_from_storage(
    sb,
    bucket: str,
    path: str,
) -> Optional[Any]:
    bucket = (bucket or "").strip()
    path = (path or "").lstrip("/")
    if not bucket or not path:
        return None
    try:
        blob = sb.storage.from_(bucket).download(path)
    except Exception:
        return None
    try:
        return json.loads(blob.decode("utf-8", errors="replace"))
    except Exception:
        return None


def cleanup_storage_runs(sb, bucket: str, prefix: str, keep: int = 5) -> None:
    """
    Supprime récursivement les vieux runs dans Storage bucket/prefix/<run_id>/...
    en gardant les `keep` plus récents.
    """
    bucket = (bucket or "").strip()
    prefix = (prefix or "").strip().strip("/")
    if not bucket or not prefix or keep <= 0:
        return

    try:
        top = sb.storage.from_(bucket).list(prefix) or []
    except Exception:
        return

    run_ids = sorted([it.get("name") for it in top if it and it.get("name")], reverse=True)
    old = run_ids[keep:]
    if not old:
        return

    def list_all_files(folder: str) -> list[str]:
        """Retourne tous les fichiers sous folder (récursif), avec chemins complets."""
        out = []
        try:
            items = sb.storage.from_(bucket).list(folder) or []
        except Exception:
            return out

        for it in items:
            name = it.get("name")
            if not name:
                continue
            full = f"{folder}/{name}"
            # Supabase Storage: si metadata contient "metadata" ou "id", c'est fichier,
            # sinon c'est souvent un "folder". On tente récursif de toute façon.
            # Heuristique: si name contient un point, c’est un fichier probable.
            if "." in name:
                out.append(full)
            else:
                out.extend(list_all_files(full))
        return out

    for rid in old:
        root = f"{prefix}/{rid}"
        paths = list_all_files(root)
        if paths:
            try:
                sb.storage.from_(bucket).remove(paths)
            except Exception:
                pass


def get_latest_snapshot_run_id(
    sb,
    bucket: str,
    runs_prefix: str = "runs",
) -> Optional[str]:
    """
    Retourne le run_id le plus récent dans bucket/runs/<run_id>/...
    (utilisé par runner pour lire le dernier snapshot)
    """
    bucket = (bucket or "").strip()
    runs_prefix = (runs_prefix or "runs").strip().strip("/")
    if not bucket:
        return None

    try:
        items = sb.storage.from_(bucket).list(runs_prefix) or []
    except Exception:
        return None

    run_ids = sorted(
        [it.get("name") for it in items if it and it.get("name")],
        reverse=True,
    )
    return run_ids[0] if run_ids else None

```

---

## FILE: llm_v3.py
```python
"""
llm_v3.py

Génération de textes Facebook HUMAINS et INTELLIGENTS pour les annonces auto.
Utilise vehicle_intelligence.py pour adapter le ton, les angles et le contenu
à chaque véhicule spécifique.

Version 3.0 — Textes qui sonnent comme un vrai vendeur passionné, pas un robot.
"""

import os
import random
from typing import Dict, Any, Optional, List

from vehicle_intelligence import build_vehicle_context, humanize_options


# ─── OpenAI client ───
def _get_openai():
    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        return OpenAI(api_key=api_key)
    except ImportError:
        return None


# ─── Prompts par type de véhicule ───

SYSTEM_PROMPT = """Tu es Daniel Giroux, vendeur passionné chez Kennebec Dodge Chrysler à Saint-Georges en Beauce.
Tu écris des annonces Facebook pour des véhicules d'occasion.

RÈGLES ABSOLUES:
- Tu écris en français québécois naturel. Pas de français de France. Pas de robot.
- Tu parles comme un VRAI vendeur qui connaît ses chars. Pas de phrases génériques.
- JAMAIS de "Prêt à dominer les routes" ou "faire tourner les têtes" — c'est cliché.
- JAMAIS de "sillonner la Beauce" ou "conquérir les chemins" — c'est du robot.
- JAMAIS mentionner "la Beauce", "routes de la Beauce" ou "paysages beauceron". On vend des chars, pas du tourisme.
- ABSOLUMENT AUCUN mot vulgaire, grossier ou à caractère sexuel. Pas de "couilles", "balls", "badass", "bitch", "cul", "merde" ou tout autre sacre/juron. C'est une page PROFESSIONNELLE d'un concessionnaire. Le ton est passionné mais TOUJOURS respectueux et professionnel.
- Chaque texte doit être UNIQUE. Si tu vends un Challenger, parle du V8. Si c'est un Wrangler, parle du off-road.
- Le ton est direct, authentique, passionné. Comme si tu parlais à un client au showroom.
- Tu CONNAIS les véhicules. Tu sais ce qui rend chaque modèle spécial.
- Maximum 3-4 phrases pour l'intro. Pas de roman.
- Pas de hashtags dans l'intro.
- Pas d'emojis dans l'intro (ils viennent après dans le corps de l'annonce).
"""

def _build_prompt_for_vehicle(ctx: Dict[str, Any], event: str = "NEW", options_text: str = "") -> str:
    """Construit le prompt spécifique au véhicule."""

    # Info de base
    title = ctx.get("title", "")
    brand = ctx.get("brand", "").capitalize()
    model = ctx.get("model", "")
    trim = ctx.get("trim", "")
    year = ctx.get("year", "")
    price_fmt = ctx.get("price_formatted", "")
    km_fmt = ctx.get("km_formatted", "")
    km_desc = ctx.get("km_description", "")
    price_desc = ctx.get("price_description", "")

    # Intelligence véhicule
    vehicle_type = ctx.get("vehicle_type", "general")
    hp = ctx.get("hp", "")
    engine = ctx.get("engine", "")
    trim_vibe = ctx.get("trim_vibe", "")
    model_known_for = ctx.get("model_known_for", "")
    brand_identity = ctx.get("brand_identity", "")
    brand_angles = ctx.get("brand_angles", [])

    # Construire les infos spécifiques
    specs_info = []
    if hp:
        specs_info.append(f"Moteur: {engine} — {hp} chevaux")
    elif engine:
        specs_info.append(f"Moteur: {engine}")
    if trim_vibe:
        specs_info.append(f"Ce trim: {trim_vibe}")
    if model_known_for:
        specs_info.append(f"Ce modèle est connu pour: {model_known_for}")
    if brand_identity:
        specs_info.append(f"La marque {brand}: {brand_identity}")

    # Options humanisées
    human_options = []
    if options_text:
        human_options = humanize_options(options_text)

    prompt = f"""Écris une annonce Facebook pour ce véhicule:

VÉHICULE: {title}
PRIX: {price_fmt}
KILOMÉTRAGE: {km_fmt} ({km_desc})
POSITIONNEMENT PRIX: {price_desc}
TYPE: {vehicle_type}

CONNAISSANCES SPÉCIFIQUES:
{chr(10).join(specs_info) if specs_info else "Aucune info spécifique disponible."}

OPTIONS/ÉQUIPEMENTS CONFIRMÉS:
{chr(10).join(f"- {o}" for o in human_options) if human_options else "Aucune option confirmée."}

ANGLES DE VENTE SUGGÉRÉS: {', '.join(brand_angles[:3]) if brand_angles else 'qualité, valeur, confiance'}

INSTRUCTIONS:
1. Écris une INTRO de 3-4 phrases maximum. Naturelle, directe, passionnée.
   - Mentionne ce qui rend CE véhicule spécial (pas une intro générique)
   - Si tu connais le moteur/HP, mentionne-le naturellement
   - Adapte le ton au type: {"adrénaline et son du moteur" if vehicle_type == "muscle_car" else "robustesse et capacité" if vehicle_type in ("pickup", "pickup_hd") else "aventure et liberté" if vehicle_type == "off_road" else "confort et raffinement" if vehicle_type == "suv_premium" else "style et économie" if vehicle_type in ("citadine", "suv_compact") else "exclusivité et rêve" if vehicle_type in ("exotique", "collector") else "polyvalence et fiabilité"}

2. Puis le CORPS structuré:
   - Titre avec le nom complet et l'année
   - Prix
   - Kilométrage
   - Stock
   - 5-8 équipements/caractéristiques en points (en français, pas de jargon technique brut)
   - Si c'est un Stellantis avec sticker: mention "Window Sticker vérifié"

3. FERME avec: le nom Daniel Giroux et le numéro 418-222-3939.
   Ne mets PAS "Kennebec Dodge" dans le footer (il est ajouté automatiquement).

FORMAT DE SORTIE: Texte prêt à copier-coller sur Facebook. Utilise des emojis avec parcimonie dans le corps (pas dans l'intro).
"""

    if event == "PRICE_CHANGED":
        old_price = ctx.get("old_price", "")
        new_price = ctx.get("new_price", "")
        prompt += f"""
ÉVÉNEMENT SPÉCIAL: BAISSE DE PRIX
Ancien prix: {old_price}
Nouveau prix: {new_price}
→ Commence par mentionner la baisse de prix de façon naturelle et excitante.
→ Fais sentir que c'est une opportunité sans être agressif.
"""

    return prompt


# ─── Variations d'intro pour éviter la répétition ───
INTRO_STYLES = [
    "direct",       # Va droit au but: "J'ai un [vehicule] qui..."
    "storytelling",  # Raconte une mini-histoire: "Y'a des chars qui..."
    "question",     # Pose une question: "Tu cherches un truck qui..."
    "expertise",    # Montre ta connaissance: "Le [modèle], c'est..."
    "opportunité",  # Focus sur le deal: "Celui-là, à ce prix-là..."
]


def generate_smart_text(
    vehicle: Dict[str, Any],
    event: str = "NEW",
    options_text: str = "",
    old_price: Any = None,
    new_price: Any = None,
) -> Optional[str]:
    """
    Génère un texte Facebook intelligent et humain pour un véhicule.

    Args:
        vehicle: Dict avec title, stock, vin, price_int, km_int, url, etc.
        event: "NEW", "PRICE_CHANGED", "PHOTOS_ADDED"
        options_text: Texte brut des options du sticker (optionnel)
        old_price: Ancien prix (pour PRICE_CHANGED)
        new_price: Nouveau prix (pour PRICE_CHANGED)

    Returns:
        Texte Facebook prêt à publier, ou None si échec
    """
    client = _get_openai()
    if not client:
        return None

    # Construire le contexte enrichi
    ctx = build_vehicle_context(vehicle)
    if old_price:
        ctx["old_price"] = f"{int(old_price):,}".replace(",", " ") + " $"
    if new_price:
        ctx["new_price"] = f"{int(new_price):,}".replace(",", " ") + " $"

    # Enrichir avec les specs VIN NHTSA si disponibles
    vin_specs_text = vehicle.get("_vin_specs_text", "")
    if not vin_specs_text:
        try:
            from vin_decoder import decode_vin, format_specs_for_prompt, format_engine_line
            vin_val = (vehicle.get("vin") or "").strip().upper()
            if len(vin_val) >= 11:
                specs = decode_vin(vin_val)
                if specs:
                    vin_specs_text = format_specs_for_prompt(specs)
                    if not ctx.get("hp") and specs.get("engine_hp"):
                        ctx["hp"] = specs["engine_hp"]
                        ctx["engine"] = format_engine_line(specs).replace(f" — {specs['engine_hp']} HP", "")
        except Exception:
            pass

    # Choisir un style d'intro aléatoire
    style = random.choice(INTRO_STYLES)

    # Construire le prompt
    prompt = _build_prompt_for_vehicle(ctx, event, options_text)
    if vin_specs_text:
        prompt += f"\n\nSPECS DECODEES DU VIN (NHTSA):\n{vin_specs_text}"
    prompt += f"\n\nSTYLE D'INTRO: {style}"

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.85,
            max_tokens=1200,
        )

        text = response.choices[0].message.content.strip()

        # Post-traitement
        text = _post_process(text)
        return text

    except Exception as e:
        print(f"[LLM_V3 ERROR] {e}", flush=True)
        return None


def generate_intro_v3(vehicle: Dict[str, Any], max_chars: int = 300) -> Optional[str]:
    """
    Génère SEULEMENT une intro courte et punchy pour un véhicule.
    Utilisée pour ajouter au-dessus d'un texte existant.
    """
    client = _get_openai()
    if not client:
        return None

    ctx = build_vehicle_context(vehicle)
    style = random.choice(INTRO_STYLES)

    title = ctx.get("title", "")
    hp = ctx.get("hp", "")
    engine = ctx.get("engine", "")
    trim_vibe = ctx.get("trim_vibe", "")
    model_known_for = ctx.get("model_known_for", "")
    km_desc = ctx.get("km_description", "")
    price_fmt = ctx.get("price_formatted", "")
    vehicle_type = ctx.get("vehicle_type", "general")

    prompt = f"""Écris SEULEMENT une intro de 2-3 phrases pour cette annonce Facebook.
Véhicule: {title}
Prix: {price_fmt}
KM: {ctx.get('km_formatted', '')} ({km_desc})
{f'Moteur: {engine} — {hp} HP' if hp else ''}
{f'Ce modèle: {model_known_for}' if model_known_for else ''}
{f'Ce trim: {trim_vibe}' if trim_vibe else ''}
Style: {style}
Type: {vehicle_type}

RÈGLES: Max {max_chars} caractères. Pas d'emojis. Pas de clichés. Pas de "routes de la Beauce". 
Parle comme un vrai vendeur québécois passionné qui connaît ses chars.
Mentionne ce qui rend CE véhicule spécial."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            max_tokens=200,
        )
        text = response.choices[0].message.content.strip()
        text = text.strip('"').strip("'")
        return text[:max_chars]
    except Exception as e:
        print(f"[LLM_V3 INTRO ERROR] {e}", flush=True)
        return None


def _post_process(text: str) -> str:
    """Nettoyage post-génération."""
    # Retirer les guillemets englobants
    text = text.strip('"').strip("'")

    # Retirer les clichés qui auraient pu passer
    cliches = [
        "prêt à dominer",
        "faire tourner les têtes",
        "sillonner la beauce",
        "conquérir les chemins",
        "dominer les routes",
        "parcourir les routes de beauce",
        "arpenter les routes",
        "routes de la beauce",
        "routes de beauce",
        "chemins de la beauce",
        "paysages de la beauce",
        "paysages beauceron",
    ]
    for c in cliches:
        if c in text.lower():
            # Retirer la phrase contenant le cliché
            lines = text.split("\n")
            text = "\n".join(l for l in lines if c not in l.lower())

    # Retirer les mots vulgaires/sexuels
    vulgar = ["couilles", "balls", "badass", "bitch", "cul ", "merde", "crisse",
              "tabarnac", "calisse", "ostie", "fuck", "shit", "damn", "ass ", "sexy"]
    for v in vulgar:
        if v in text.lower():
            lines = text.split("\n")
            text = "\n".join(l for l in lines if v not in l.lower())

    return text.strip()


# ─── Test local ───
if __name__ == "__main__":
    # Test avec quelques véhicules
    test_vehicles = [
        {"title": "Dodge CHALLENGER R/T SCAT PACK BLANC 2023", "stock": "06234", "vin": "2C3CDZFJ1PH593481", "price_int": 79995, "km_int": 11500},
        {"title": "Jeep WRANGLER RUBICON 4XE 2024", "stock": "06106", "vin": "1C4HJXFN5RW123456", "price_int": 62995, "km_int": 15586},
        {"title": "Ram 2500 BIG HORN 2025", "stock": "06230", "vin": "3C6UR5DJ1RG123456", "price_int": 71995, "km_int": 25},
        {"title": "LAMBORGHIN I 2024", "stock": "06232", "vin": "", "price_int": 343995, "km_int": 8900},
        {"title": "Ford MUSTANG 2022", "stock": "46104A", "vin": "", "price_int": 35995, "km_int": 21433},
        {"title": "Fiat 500 E RED 2024", "stock": "44220A", "vin": "", "price_int": 23995, "km_int": 22},
    ]

    for v in test_vehicles:
        print(f"\n{'='*60}")
        print(f"TEST: {v['title']}")
        print(f"{'='*60}")
        ctx = build_vehicle_context(v)
        print(f"  Brand: {ctx['brand']} | Model: {ctx['model']} | Trim: {ctx['trim']}")
        print(f"  Type: {ctx['vehicle_type']} | HP: {ctx['hp']} | Engine: {ctx['engine']}")
        print(f"  Vibe: {ctx['trim_vibe']}")
        print(f"  KM: {ctx['km_description']} | Prix: {ctx['price_description']}")
        print()

        text = generate_smart_text(v)
        if text:
            print(text[:500])
        else:
            print("  [Pas de clé OpenAI — test parsing seulement]")
```

---

## FILE: vehicle_intelligence.py
```python
"""
vehicle_intelligence.py

Module de connaissance véhicule pour générer des textes Facebook
intelligents et humains. Parse le titre, identifie marque/modèle/trim,
et fournit des angles de vente spécifiques à chaque véhicule.
"""

import re
from typing import Dict, Any, Optional, List, Tuple


# ─── Base de connaissance : Marques ───
BRAND_PROFILES = {
    "ram": {
        "tone": "puissance",
        "emoji": "💪",
        "identity": "le truck qui travaille aussi fort que toi",
        "angles": ["capacité de remorquage", "robustesse", "confort de cabine", "moteur Cummins/HEMI"],
    },
    "dodge": {
        "tone": "performance",
        "emoji": "🏁",
        "identity": "la performance américaine pure",
        "angles": ["puissance brute", "son du moteur", "look agressif", "adrénaline"],
    },
    "jeep": {
        "tone": "aventure",
        "emoji": "🏔️",
        "identity": "la liberté de rouler partout",
        "angles": ["capacité hors route", "polyvalence", "look iconique", "4x4"],
    },
    "chrysler": {
        "tone": "confort",
        "emoji": "✨",
        "identity": "le confort familial raffiné",
        "angles": ["espace intérieur", "technologie", "confort", "sécurité"],
    },
    "fiat": {
        "tone": "urbain",
        "emoji": "⚡",
        "identity": "le style européen électrique",
        "angles": ["économie", "style", "format compact", "zéro émission"],
    },
    "ford": {
        "tone": "polyvalent",
        "emoji": "🔥",
        "identity": "l'icône américaine",
        "angles": ["fiabilité", "performance", "polyvalence", "tradition"],
    },
    "chevrolet": {
        "tone": "polyvalent",
        "emoji": "🔥",
        "identity": "la fiabilité américaine",
        "angles": ["rapport qualité-prix", "fiabilité", "performance", "polyvalence"],
    },
    "toyota": {
        "tone": "fiabilité",
        "emoji": "🛡️",
        "identity": "la fiabilité légendaire",
        "angles": ["durabilité", "revente", "économie de carburant", "fiabilité prouvée"],
    },
    "honda": {
        "tone": "fiabilité",
        "emoji": "🛡️",
        "identity": "l'ingénierie japonaise",
        "angles": ["fiabilité", "économie", "conduite agréable", "valeur de revente"],
    },
    "hyundai": {
        "tone": "moderne",
        "emoji": "🚀",
        "identity": "la technologie accessible",
        "angles": ["garantie", "technologie", "design moderne", "rapport qualité-prix"],
    },
    "kia": {
        "tone": "moderne",
        "emoji": "🚀",
        "identity": "le design qui surprend",
        "angles": ["design", "garantie", "technologie", "valeur"],
    },
    "mazda": {
        "tone": "plaisir",
        "emoji": "🎯",
        "identity": "le plaisir de conduire",
        "angles": ["conduite", "design", "qualité intérieure", "Skyactiv"],
    },
    "subaru": {
        "tone": "aventure",
        "emoji": "🏔️",
        "identity": "la traction intégrale de série",
        "angles": ["AWD", "sécurité", "fiabilité", "conduite hivernale"],
    },
    "volkswagen": {
        "tone": "raffiné",
        "emoji": "🇩🇪",
        "identity": "l'ingénierie allemande",
        "angles": ["qualité de construction", "conduite", "technologie", "raffinement"],
    },
    "bmw": {
        "tone": "luxe",
        "emoji": "🏎️",
        "identity": "le plaisir de conduire premium",
        "angles": ["performance", "luxe", "technologie", "prestige"],
    },
    "mercedes": {
        "tone": "luxe",
        "emoji": "⭐",
        "identity": "le luxe qui ne fait pas de compromis",
        "angles": ["confort", "prestige", "sécurité", "technologie de pointe"],
    },
    "lamborghini": {
        "tone": "exotique",
        "emoji": "🐂",
        "identity": "le rêve automobile",
        "angles": ["exclusivité", "performance extrême", "design", "expérience unique"],
    },
    "porsche": {
        "tone": "exotique",
        "emoji": "🏎️",
        "identity": "la perfection sportive",
        "angles": ["ingénierie", "performance", "prestige", "conduite"],
    },
    "tesla": {
        "tone": "futuriste",
        "emoji": "⚡",
        "identity": "le futur de l'automobile",
        "angles": ["autonomie", "technologie", "performance instantanée", "zéro émission"],
    },
    "gmc": {
        "tone": "puissance",
        "emoji": "💪",
        "identity": "le premium professionnel",
        "angles": ["capacité", "luxe utilitaire", "robustesse", "technologie"],
    },
    "nissan": {
        "tone": "polyvalent",
        "emoji": "🔥",
        "identity": "l'innovation accessible",
        "angles": ["technologie", "polyvalence", "fiabilité", "rapport qualité-prix"],
    },
    "plymouth": {
        "tone": "classique",
        "emoji": "🏁",
        "identity": "la légende américaine",
        "angles": ["collector", "rareté", "histoire", "look unique"],
    },
    "ferrari": {
        "tone": "exotique",
        "emoji": "🏎️",
        "identity": "la quintessence de la supercar italienne",
        "angles": ["exclusivité", "performance extrême", "héritage course", "design italien"],
    },
    "audi": {
        "tone": "raffiné",
        "emoji": "🇩🇪",
        "identity": "la technologie allemande de pointe",
        "angles": ["Quattro AWD", "technologie", "qualité de construction", "performance"],
    },
    "buick": {
        "tone": "confort",
        "emoji": "✨",
        "identity": "le confort américain premium",
        "angles": ["confort", "silence de roulement", "technologie", "valeur"],
    },
    "cadillac": {
        "tone": "luxe",
        "emoji": "⭐",
        "identity": "le luxe américain audacieux",
        "angles": ["luxe", "technologie", "performance", "prestige"],
    },
    "mitsubishi": {
        "tone": "aventure",
        "emoji": "🏔️",
        "identity": "le 4x4 japonais fiable",
        "angles": ["AWD", "fiabilité", "garantie", "rapport qualité-prix"],
    },
}

# ─── Base de connaissance : Modèles spécifiques ───
MODEL_SPECS = {
    # DODGE
    "challenger": {
        "type": "muscle_car",
        "known_for": "muscle car américain légendaire",
        "trims": {
            "sxt": {"hp": "303", "engine": "V6 Pentastar 3.6L", "vibe": "l'entrée dans le monde muscle"},
            "gt": {"hp": "303", "engine": "V6 Pentastar 3.6L AWD", "vibe": "le muscle avec traction intégrale"},
            "r/t": {"hp": "375", "engine": "V8 HEMI 5.7L", "vibe": "le vrai son HEMI"},
            "r/t scat pack": {"hp": "485", "engine": "V8 HEMI 6.4L 392", "vibe": "485 chevaux de pure adrénaline"},
            "scat pack": {"hp": "485", "engine": "V8 HEMI 6.4L 392", "vibe": "la bête de 485 chevaux"},
            "hellcat": {"hp": "717", "engine": "V8 HEMI Supercharged 6.2L", "vibe": "717 chevaux. Point final."},
            "demon": {"hp": "840", "engine": "V8 HEMI Supercharged 6.2L", "vibe": "le monstre de la drag strip"},
        },
    },
    "charger": {
        "type": "muscle_sedan",
        "known_for": "la seule berline muscle car 4 portes",
        "trims": {
            "sxt": {"hp": "303", "engine": "V6 Pentastar 3.6L"},
            "gt": {"hp": "303", "engine": "V6 Pentastar 3.6L AWD"},
            "r/t": {"hp": "375", "engine": "V8 HEMI 5.7L"},
            "scat pack": {"hp": "485", "engine": "V8 HEMI 6.4L 392"},
            "hellcat": {"hp": "717", "engine": "V8 HEMI Supercharged 6.2L"},
        },
    },
    "hornet": {
        "type": "suv_compact",
        "known_for": "le petit SUV Dodge avec du punch",
        "trims": {
            "gt": {"hp": "268", "engine": "Turbo 2.0L", "vibe": "compact mais costaud"},
            "r/t": {"hp": "288", "engine": "Turbo 1.3L + électrique PHEV", "vibe": "hybride rechargeable avec du caractère"},
            "r/t plus": {"hp": "288", "engine": "Turbo 1.3L + électrique PHEV", "vibe": "le PHEV tout équipé"},
        },
    },
    # JEEP
    "wrangler": {
        "type": "off_road",
        "known_for": "l'icône du hors-route depuis 1941",
        "trims": {
            "sport": {"vibe": "le Wrangler pur et dur, prêt pour la trail"},
            "sahara": {"vibe": "le Wrangler confortable pour la route ET la trail"},
            "rubicon": {"vibe": "le roi absolu du hors-route, lockers et tout"},
            "4xe": {"vibe": "le Wrangler hybride rechargeable — trail ET électrique"},
            "rubicon 4xe": {"vibe": "hors-route extrême + hybride rechargeable"},
        },
    },
    "grand cherokee": {
        "type": "suv_premium",
        "known_for": "le SUV premium américain par excellence",
        "trims": {
            "laredo": {"vibe": "l'entrée dans le monde Grand Cherokee"},
            "limited": {"vibe": "cuir, tech et confort — le sweet spot"},
            "overland": {"vibe": "le luxe avec capacité hors-route"},
            "summit": {"vibe": "le sommet du luxe — tout y est"},
            "trailhawk": {"vibe": "le Grand Cherokee prêt pour le sentier"},
            "4xe": {"vibe": "hybride rechargeable avec le luxe Jeep"},
        },
    },
    "compass": {
        "type": "suv_compact",
        "known_for": "le SUV compact Jeep accessible",
        "trims": {
            "sport": {"vibe": "compact et capable"},
            "latitude": {"vibe": "bien équipé pour le quotidien"},
            "limited": {"vibe": "le petit luxe Jeep"},
            "trailhawk": {"vibe": "le plus capable de sa catégorie"},
        },
    },
    # RAM
    "1500": {
        "type": "pickup",
        "known_for": "le pickup pleine grandeur le plus confortable",
        "trims": {
            "tradesman": {"vibe": "le truck de travail, simple et efficace"},
            "big horn": {"vibe": "le meilleur rapport équipement-prix"},
            "classic slt": {"vibe": "le Classic — équipement solide à prix compétitif"},
            "classic tradesman": {"vibe": "le Classic pour le travail au quotidien"},
            "slt": {"vibe": "bien équipé — le choix populaire"},
            "sport": {"hp": "395", "engine": "V8 HEMI 5.7L", "vibe": "le HEMI avec le look sport — roues noires et grille sport"},
            "laramie": {"vibe": "cuir et chrome — le truck premium"},
            "rebel": {"vibe": "le look off-road avec la suspension Bilstein"},
            "limited": {"vibe": "le truck limousine — tout le luxe"},
            "trx": {"hp": "702", "engine": "V8 HEMI Supercharged 6.2L", "vibe": "702 chevaux dans un pickup. Oui."},
        },
    },
    "2500": {
        "type": "pickup_hd",
        "known_for": "le heavy-duty qui remorque tout",
        "trims": {
            "tradesman": {"vibe": "fait pour travailler, point"},
            "slt": {"vibe": "heavy-duty bien équipé au bon prix"},
            "big horn": {"vibe": "heavy-duty bien équipé"},
            "laramie": {"vibe": "HD avec intérieur premium"},
            "limited": {"vibe": "le HD le plus luxueux sur le marché"},
            "power wagon": {"vibe": "le HD off-road ultime avec Warn winch"},
        },
    },
    "promaster": {
        "type": "commercial",
        "known_for": "le fourgon commercial #1 pour les entrepreneurs",
        "trims": {
            "cargo van": {"vibe": "l'espace de travail mobile"},
            "tradesman": {"vibe": "prêt pour le business dès la sortie du lot"},
            "1500": {"vibe": "le ProMaster compact — maniable en ville"},
            "2500": {"vibe": "le ProMaster mid — bon équilibre charge/maniabilité"},
            "3500": {"vibe": "le ProMaster max — charge maximale pour les pros"},
            "1500 136": {"vibe": "empattement court — parfait pour les livraisons urbaines"},
            "1500 118": {"vibe": "le plus compact — facile à stationner"},
            "2500 high": {"vibe": "toit haut — debout à l'intérieur pour travailler"},
            "3500 high": {"vibe": "toit haut + charge max — le fourgon ultime"},
            "3500 high extended": {"vibe": "toit haut + empattement long — le plus d'espace possible"},
        },
    },
    # FORD
    "mustang": {
        "type": "muscle_car",
        "known_for": "la légende américaine depuis 1964",
        "trims": {
            "ecoboost": {"hp": "310", "engine": "Turbo 2.3L EcoBoost", "vibe": "le turbo efficace"},
            "gt": {"hp": "450", "engine": "V8 Coyote 5.0L", "vibe": "le V8 légendaire"},
            "mach 1": {"hp": "480", "engine": "V8 Coyote 5.0L", "vibe": "entre le GT et le Shelby"},
            "shelby gt500": {"hp": "760", "engine": "V8 Supercharged 5.2L", "vibe": "la Mustang ultime"},
        },
    },
    # FIAT
    "500": {
        "type": "citadine",
        "known_for": "le style italien électrique",
        "trims": {
            "e": {"vibe": "100% électrique, 100% style"},
            "red": {"vibe": "édition spéciale (RED) — style et cause"},
        },
    },
    # TOYOTA
    "rav4": {
        "type": "suv_compact",
        "known_for": "le SUV compact le plus vendu au monde",
        "trims": {
            "le": {"vibe": "bien équipé de série"},
            "xle": {"vibe": "le sweet spot — confort et valeur"},
            "limited": {"vibe": "tout équipé, rien ne manque"},
            "trail": {"vibe": "prêt pour l'aventure avec AWD"},
        },
    },
    # MAZDA
    "cx-90": {
        "type": "suv_premium",
        "known_for": "le SUV 3 rangées premium de Mazda",
        "trims": {
            "gs-l": {"vibe": "le luxe Mazda accessible"},
            "gt": {"vibe": "cuir Nappa et bois véritable"},
            "phev": {"vibe": "hybride rechargeable premium"},
            "premium": {"vibe": "le haut de gamme Mazda — cuir, bois, technologie"},
            "premium plus": {"vibe": "le summum du luxe Mazda avec tout l'équipement"},
            "premium signature": {"vibe": "édition signature — le meilleur de Mazda, point final"},
        },
    },
    "cx-5": {
        "type": "suv_compact",
        "known_for": "le SUV compact le plus plaisant à conduire",
        "trims": {
            "gs": {"vibe": "bien équipé et agréable"},
            "gt": {"vibe": "cuir et toit ouvrant — le sweet spot"},
            "signature": {"vibe": "le CX-5 ultime — turbo et luxe"},
        },
    },
    "cx-50": {
        "type": "suv_compact",
        "known_for": "le SUV compact aventurier de Mazda",
        "trims": {
            "gs": {"vibe": "prêt pour l'aventure de série"},
            "gt": {"vibe": "confort et capacité off-road"},
            "meridian": {"vibe": "édition premium — turbo et cuir"},
        },
    },
    # PLYMOUTH
    "prowler": {
        "type": "collector",
        "known_for": "le hot rod de usine — une pièce de collection rare",
        "trims": {},
    },
    "satellite": {
        "type": "collector",
        "known_for": "le muscle car classique Plymouth des années 60-70",
        "trims": {},
    },
    # JEEP (modèles manquants)
    "wagoneer": {
        "type": "suv_premium",
        "known_for": "le grand SUV de luxe américain par Jeep",
        "trims": {
            "series i": {"vibe": "l'entrée dans le monde Wagoneer — déjà très équipé"},
            "series ii": {"vibe": "le luxe Wagoneer avec plus de technologie et de confort"},
            "series iii": {"vibe": "le Wagoneer tout inclus — rien ne manque"},
        },
    },
    "renegade": {
        "type": "suv_compact",
        "known_for": "le petit Jeep au look unique — compact mais capable",
        "trims": {
            "sport": {"vibe": "compact et abordable avec le badge Jeep"},
            "north": {"vibe": "bien équipé pour le climat canadien"},
            "limited": {"vibe": "le petit luxe Jeep"},
            "trailhawk": {"vibe": "le plus capable des petits SUV — Trail Rated"},
        },
    },
    # CHEVROLET
    "malibu": {
        "type": "berline",
        "known_for": "la berline intermédiaire fiable et économique",
        "trims": {
            "ls": {"vibe": "l'essentiel bien fait"},
            "lt": {"hp": "160", "engine": "Turbo 1.5L", "vibe": "le meilleur rapport équipement-prix"},
            "rs": {"vibe": "le look sportif avec le turbo"},
            "premier": {"vibe": "tout équipé — cuir et technologie"},
        },
    },
    "silverado": {
        "type": "pickup",
        "known_for": "le pickup pleine grandeur le plus vendu en Amérique",
        "trims": {
            "wt": {"vibe": "le truck de travail, simple et efficace"},
            "custom": {"vibe": "le look custom sans le prix custom"},
            "lt": {"vibe": "bien équipé pour le quotidien"},
            "rst": {"vibe": "le look sport streetside"},
            "ltz": {"vibe": "cuir et chrome — le Silverado premium"},
            "high country": {"vibe": "le Silverado le plus luxueux — tout y est"},
            "trail boss": {"vibe": "le off-road Chevy avec suspension relevée"},
            "zr2": {"hp": "420", "engine": "V8 6.2L", "vibe": "le Silverado off-road extrême — Multimatic DSSV"},
        },
    },
    "equinox": {
        "type": "suv_compact",
        "known_for": "le SUV compact familial par excellence chez Chevy",
        "trims": {
            "ls": {"vibe": "l'essentiel pour la famille"},
            "lt": {"vibe": "bien équipé et polyvalent"},
            "rs": {"vibe": "le look sportif"},
            "premier": {"vibe": "tout équipé — cuir et technologie"},
        },
    },
    # HONDA
    "civic": {
        "type": "berline",
        "known_for": "la compacte la plus fiable et la plus vendue au monde",
        "trims": {
            "dx": {"vibe": "l'essentiel Honda — fiable et économique"},
            "lx": {"vibe": "bien équipé de série"},
            "ex": {"hp": "158", "engine": "2.0L i-VTEC", "vibe": "le sweet spot — toit ouvrant et Honda Sensing"},
            "ex-l": {"vibe": "cuir et tout le confort"},
            "touring": {"vibe": "la Civic tout équipée — navigation et cuir"},
            "sport": {"vibe": "le look sportif avec le moteur turbo"},
            "si": {"hp": "200", "engine": "Turbo 1.5L", "vibe": "la Civic sportive — turbo et manuelle"},
            "type r": {"hp": "315", "engine": "Turbo 2.0L", "vibe": "la bête de piste — 315 chevaux de pure rage"},
        },
    },
    "cr-v": {
        "type": "suv_compact",
        "known_for": "le SUV compact Honda — fiabilité légendaire",
        "trims": {
            "lx": {"vibe": "AWD et Honda Sensing de série"},
            "ex": {"vibe": "le sweet spot avec toit ouvrant"},
            "ex-l": {"vibe": "cuir et sièges chauffants"},
            "touring": {"vibe": "tout équipé — le CR-V ultime"},
        },
    },
    "accord": {
        "type": "berline",
        "known_for": "la berline intermédiaire référence — confort et fiabilité",
        "trims": {
            "lx": {"vibe": "bien équipé de série"},
            "ex": {"vibe": "le meilleur rapport qualité-prix"},
            "ex-l": {"vibe": "cuir et navigation"},
            "sport": {"hp": "252", "engine": "Turbo 2.0L", "vibe": "le turbo qui surprend"},
            "touring": {"hp": "252", "engine": "Turbo 2.0L", "vibe": "tout le luxe Honda — le sommet"},
        },
    },
    # CHRYSLER
    "pacifica": {
        "type": "minivan",
        "known_for": "la meilleure minifourgonnette sur le marché — confort familial",
        "trims": {
            "lx": {"vibe": "l'essentiel familial bien fait"},
            "touring": {"vibe": "Stow 'n Go et confort pour toute la famille"},
            "touring l": {"vibe": "cuir et portières électriques"},
            "limited": {"vibe": "le luxe familial — tout y est"},
            "pinnacle": {"vibe": "le summum du luxe en minifourgonnette"},
            "hybrid": {"vibe": "hybride rechargeable — économique et familial"},
        },
    },
    "300": {
        "type": "berline",
        "known_for": "la grande berline américaine au look imposant",
        "trims": {
            "touring": {"hp": "292", "engine": "V6 Pentastar 3.6L", "vibe": "le look imposant à bon prix"},
            "s": {"hp": "300", "engine": "V6 Pentastar 3.6L", "vibe": "le look sport avec les roues noires"},
            "c": {"hp": "363", "engine": "V8 HEMI 5.7L", "vibe": "le V8 HEMI dans une berline de luxe"},
        },
    },
    # DODGE (modèles manquants)
    "durango": {
        "type": "suv_premium",
        "known_for": "le seul SUV 3 rangées avec un V8 HEMI disponible",
        "trims": {
            "sxt": {"hp": "293", "engine": "V6 Pentastar 3.6L", "vibe": "le SUV Dodge accessible"},
            "gt": {"hp": "293", "engine": "V6 Pentastar 3.6L", "vibe": "le look sport avec AWD"},
            "r/t": {"hp": "360", "engine": "V8 HEMI 5.7L", "vibe": "le V8 HEMI dans un SUV familial"},
            "citadel": {"hp": "360", "engine": "V8 HEMI 5.7L", "vibe": "le luxe Durango — cuir et chrome"},
            "srt 392": {"hp": "475", "engine": "V8 HEMI 6.4L 392", "vibe": "475 chevaux dans un SUV 3 rangées"},
            "srt hellcat": {"hp": "710", "engine": "V8 HEMI Supercharged 6.2L", "vibe": "le SUV le plus puissant jamais construit"},
        },
    },
    # RAM (trims manquants)
    "promaster city": {
        "type": "commercial",
        "known_for": "le fourgon compact idéal pour la ville",
        "trims": {
            "tradesman": {"vibe": "compact et maniable pour les livraisons"},
            "wagon": {"vibe": "version passagers — 5 places"},
        },
    },
    # TOYOTA (modèles supplémentaires)
    "corolla": {
        "type": "berline",
        "known_for": "la voiture la plus vendue de l'histoire — fiabilité absolue",
        "trims": {
            "l": {"vibe": "l'essentiel Toyota"},
            "le": {"vibe": "bien équipé et économique"},
            "se": {"vibe": "le look sport avec la boîte CVT"},
            "xse": {"vibe": "le sport haut de gamme"},
        },
    },
    "tacoma": {
        "type": "pickup",
        "known_for": "le pickup mid-size indestructible",
        "trims": {
            "sr": {"vibe": "le truck de travail Toyota"},
            "sr5": {"vibe": "le sweet spot — bien équipé"},
            "trd sport": {"vibe": "le look sport sur route"},
            "trd off-road": {"vibe": "Trail Rated — prêt pour le sentier"},
            "trd pro": {"vibe": "le Tacoma ultime — TRD suspension et tout"},
            "limited": {"vibe": "le luxe dans un pickup mid-size"},
        },
    },
    "4runner": {
        "type": "off_road",
        "known_for": "le SUV body-on-frame — robuste et indestructible",
        "trims": {
            "sr5": {"vibe": "le 4Runner classique"},
            "trd off-road": {"vibe": "différentiel arrière verrouillable — sérieux"},
            "trd pro": {"vibe": "le 4Runner ultime pour le hors-route extrême"},
            "limited": {"vibe": "luxe et capacité combinés"},
        },
    },
    "highlander": {
        "type": "suv_premium",
        "known_for": "le SUV 3 rangées familial par excellence",
        "trims": {
            "le": {"vibe": "bien équipé de série"},
            "xle": {"vibe": "le sweet spot familial"},
            "limited": {"vibe": "cuir et technologie — tout y est"},
            "platinum": {"vibe": "le sommet du luxe Toyota"},
        },
    },
    # FORD (modèles supplémentaires)
    "f-150": {
        "type": "pickup",
        "known_for": "le véhicule le plus vendu en Amérique — le roi des pickups",
        "trims": {
            "xl": {"vibe": "le truck de travail Ford"},
            "xlt": {"hp": "400", "engine": "V6 EcoBoost 3.5L", "vibe": "le meilleur vendeur — bien équipé"},
            "lariat": {"vibe": "cuir et chrome — le F-150 premium"},
            "king ranch": {"vibe": "l'héritage texan — cuir et bois"},
            "platinum": {"vibe": "le luxe absolu dans un pickup"},
            "tremor": {"vibe": "le F-150 off-road avec suspension trail"},
            "raptor": {"hp": "450", "engine": "V6 EcoBoost 3.5L HO", "vibe": "le pickup haute performance — Baja ready"},
            "raptor r": {"hp": "720", "engine": "V8 Supercharged 5.2L", "vibe": "720 chevaux dans un pickup. Fou."},
        },
    },
    "explorer": {
        "type": "suv_premium",
        "known_for": "le SUV 3 rangées Ford — aventure et famille",
        "trims": {
            "base": {"vibe": "l'Explorer bien équipé de série"},
            "xlt": {"vibe": "le sweet spot familial"},
            "limited": {"vibe": "cuir et technologie"},
            "st": {"hp": "400", "engine": "V6 EcoBoost 3.0L", "vibe": "400 chevaux dans un SUV familial"},
            "timberline": {"vibe": "l'Explorer prêt pour le sentier"},
        },
    },
    "bronco": {
        "type": "off_road",
        "known_for": "le retour de la légende Ford — hors-route pur et dur",
        "trims": {
            "base": {"vibe": "le Bronco pur — portes et toit amovibles"},
            "big bend": {"vibe": "un peu plus de confort pour la trail"},
            "outer banks": {"vibe": "le look côtier avec tout l'équipement"},
            "badlands": {"vibe": "le sérieux hors-route — stabilisateur déconnectable"},
            "wildtrak": {"vibe": "les gros pneus et le Sasquatch package"},
            "raptor": {"hp": "418", "engine": "V6 EcoBoost 3.0L", "vibe": "le Bronco extrême — suspension Baja"},
        },
    },
    "escape": {
        "type": "suv_compact",
        "known_for": "le SUV compact Ford — polyvalent et économique",
        "trims": {
            "s": {"vibe": "l'essentiel Ford"},
            "se": {"vibe": "bien équipé et AWD disponible"},
            "sel": {"vibe": "confort et technologie"},
            "titanium": {"vibe": "le haut de gamme compact Ford"},
        },
    },
    # FERRARI
    "488": {
        "type": "exotique",
        "known_for": "la supercar turbo qui a redéfini Ferrari",
        "trims": {
            "gtb": {"hp": "661", "engine": "V8 Biturbo 3.9L", "vibe": "661 chevaux de pure ingénierie italienne"},
            "spider": {"hp": "661", "engine": "V8 Biturbo 3.9L", "vibe": "le même monstre, mais à ciel ouvert"},
            "pista": {"hp": "710", "engine": "V8 Biturbo 3.9L", "vibe": "née sur la piste — la 488 ultime"},
        },
    },
    "488gtb": {
        "type": "exotique",
        "known_for": "la supercar turbo qui a redéfini Ferrari",
        "trims": {},
    },
    # HYUNDAI (modèles courants)
    "tucson": {
        "type": "suv_compact",
        "known_for": "le SUV compact au design futuriste",
        "trims": {
            "essential": {"vibe": "bien équipé de série"},
            "preferred": {"vibe": "AWD et sièges chauffants"},
            "ultimate": {"vibe": "tout inclus — le luxe Hyundai"},
        },
    },
    "santa fe": {
        "type": "suv_premium",
        "known_for": "le SUV familial redessiné avec audace",
        "trims": {
            "essential": {"vibe": "spacieux et bien équipé"},
            "preferred": {"vibe": "le sweet spot familial"},
            "ultimate": {"vibe": "cuir et panoramique — tout y est"},
            "calligraphy": {"vibe": "le sommet du luxe Hyundai"},
        },
    },
    # SUBARU
    "outback": {
        "type": "suv_compact",
        "known_for": "le wagon surélevé avec AWD — aventure et quotidien",
        "trims": {
            "base": {"vibe": "AWD de série — prêt pour l'hiver"},
            "limited": {"vibe": "cuir et EyeSight — le sweet spot"},
            "onyx": {"vibe": "le look aventurier avec les accents noirs"},
            "wilderness": {"vibe": "le vrai off-road Subaru — suspension relevée"},
        },
    },
    "forester": {
        "type": "suv_compact",
        "known_for": "le SUV compact avec la meilleure visibilité de sa catégorie",
        "trims": {
            "base": {"vibe": "AWD et EyeSight de série"},
            "touring": {"vibe": "cuir et toit panoramique"},
            "sport": {"vibe": "le look sport avec le moteur turbo"},
            "wilderness": {"vibe": "le Forester prêt pour le sentier"},
        },
    },
}

# ─── Kilométrage intelligence ───
def km_description(km: int) -> str:
    if km is None:
        return ""
    if km <= 100:
        return "pratiquement neuf — jamais roulé"
    if km <= 5000:
        return "à peine rodé"
    if km <= 15000:
        return "très bas kilométrage"
    if km <= 30000:
        return "bas kilométrage"
    if km <= 60000:
        return "kilométrage raisonnable"
    if km <= 100000:
        return "bien entretenu"
    if km <= 150000:
        return "kilométrage honnête pour l'année"
    return "véhicule d'expérience"

# ─── Prix intelligence ───
def price_description(price: int, vehicle_type: str = "") -> str:
    if price is None:
        return ""
    if price < 20000:
        return "prix d'ami"
    if price < 30000:
        return "excellent rapport qualité-prix"
    if price < 45000:
        return "bien positionné"
    if price < 65000:
        return "investissement solide"
    if price < 100000:
        return "véhicule premium"
    if price < 200000:
        return "véhicule de prestige"
    return "pièce d'exception"


def parse_vehicle_title(title: str) -> Dict[str, str]:
    """
    Parse un titre comme 'Ram 2500 BIG HORN 2025' ou 'Dodge CHALLENGER R/T SCAT PACK BLANC 2023'
    Retourne: brand, model, trim, year, color
    """
    title = (title or "").strip()
    result = {"brand": "", "model": "", "trim": "", "year": "", "color": "", "raw_title": title}

    # Extraire l'année (4 chiffres, généralement 2000+)
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', title)
    if year_match:
        result["year"] = year_match.group(1)
        title_no_year = title[:year_match.start()].strip()
    else:
        title_no_year = title

    # Couleurs connues à retirer
    colors = ["blanc", "blanche", "noir", "noire", "rouge", "bleu", "bleue", "gris", "grise",
              "argent", "vert", "verte", "orange", "jaune", "brun", "brune", "beige",
              "white", "black", "red", "blue", "grey", "gray", "silver", "green"]
    title_clean = title_no_year
    for c in colors:
        pattern = re.compile(r'\b' + re.escape(c) + r'\b', re.IGNORECASE)
        if pattern.search(title_clean):
            result["color"] = c.capitalize()
            title_clean = pattern.sub('', title_clean).strip()

    # Nettoyer les espaces multiples
    title_clean = re.sub(r'\s+', ' ', title_clean).strip()

    # Détecter la marque
    parts = title_clean.split()
    if not parts:
        return result

    brand_candidate = parts[0].lower().replace("-", "")
    # Cas spéciaux
    if brand_candidate in ("lamborghin", "lamborghini"):
        brand_candidate = "lamborghini"
    elif brand_candidate == "mercedes" or brand_candidate == "mercedes-benz":
        brand_candidate = "mercedes"

    result["brand"] = brand_candidate

    # Le reste est modèle + trim
    remaining = " ".join(parts[1:]).strip()

    # Essayer de matcher un modèle connu
    remaining_lower = remaining.lower()
    best_model = ""
    best_model_len = 0

    brand_models = {k: v for k, v in MODEL_SPECS.items()}
    for model_name in brand_models:
        if model_name.lower() in remaining_lower:
            if len(model_name) > best_model_len:
                best_model = model_name
                best_model_len = len(model_name)

    if best_model:
        result["model"] = best_model
        # Ce qui reste après le modèle = trim
        idx = remaining_lower.find(best_model.lower())
        after_model = remaining[idx + len(best_model):].strip()
        # Nettoyer
        after_model = re.sub(r'\s+', ' ', after_model).strip()
        # Retirer A/C, 4X4, AWD etc. du trim pour le garder propre
        result["trim"] = after_model
    else:
        # Pas de modèle connu — prendre le premier mot comme modèle
        rem_parts = remaining.split()
        if rem_parts:
            result["model"] = rem_parts[0]
            result["trim"] = " ".join(rem_parts[1:])

    return result


def get_vehicle_profile(parsed: Dict[str, str]) -> Dict[str, Any]:
    """
    Retourne un profil complet du véhicule basé sur le parsing.
    """
    brand = parsed.get("brand", "").lower()
    model = parsed.get("model", "").lower()
    trim = parsed.get("trim", "").lower()

    profile = {
        "brand_profile": BRAND_PROFILES.get(brand, BRAND_PROFILES.get("ford")),  # fallback générique
        "model_specs": None,
        "trim_specs": None,
        "vehicle_type": "general",
        "known_for": "",
        "hp": "",
        "engine": "",
        "vibe": "",
    }

    # Chercher le modèle
    model_data = MODEL_SPECS.get(model)
    if model_data:
        profile["model_specs"] = model_data
        profile["vehicle_type"] = model_data.get("type", "general")
        profile["known_for"] = model_data.get("known_for", "")

        # Chercher le trim
        trims = model_data.get("trims", {})
        best_trim = None
        best_trim_len = 0
        for trim_key, trim_val in trims.items():
            if trim_key.lower() in trim:
                if len(trim_key) > best_trim_len:
                    best_trim = trim_val
                    best_trim_len = len(trim_key)

        if best_trim:
            profile["trim_specs"] = best_trim
            profile["hp"] = best_trim.get("hp", "")
            profile["engine"] = best_trim.get("engine", "")
            profile["vibe"] = best_trim.get("vibe", "")

    return profile


def humanize_options(options_text: str) -> List[str]:
    """
    Convertit les options brutes du sticker en texte humain lisible.
    """
    translations = {
        "BAQUETS AVANT": "Sièges baquets avant",
        "VENTILES DESSUS CUIR": "ventilés en cuir",
        "TISSU CATEGORIE SUP": "en tissu premium",
        "SIEGES AVANT CHAUFFANTS": "Sièges avant chauffants",
        "SIEGES ARRIERE CHAUFFANTS": "Sièges arrière chauffants",
        "VOLANT CHAUFFANT": "Volant chauffant",
        "ENSEMBLE SIEGES ET VOLANT CHAUFFANTS": "Sièges et volant chauffants",
        "ECROUS DE ROUE ANTIVOL": "Écrous de roue antivol",
        "ENSEMBLE TECHNOLOGIE": "Ensemble technologie",
        "ENSEMBLE PROTECTION": "Ensemble protection",
        "ENSEMBLE ECLAIR": "Ensemble complet",
        "EDITION NUIT": "Édition Nuit (look noir)",
        "TRANS AUTO": "Transmission automatique",
        "TORQUEFLITE": "TorqueFlite",
        "GLACES A ECRAN SOLAIRE": "Vitres teintées",
        "FREINS ANTIBLOCAGE": "Freins ABS",
        "SYSTEME DE REDUCTION ACTIF DU BRUIT": "Insonorisation active",
        "COUCHE NACREE ROUGE": "Peinture rouge nacrée",
        "COUCHE NACREE": "Peinture nacrée",
        "SUSPENSION HAUTE PERFORMANCE": "Suspension sport haute performance",
        "PNEUS RTE/HORS RTE": "Pneus route/hors-route",
        "PORT USB": "Port USB",
        "PORTS USB": "Ports USB",
        "ECRAN COULEUR TFT": "Écran couleur TFT",
        "OUVRE-PORTE DE GARAGE UNIVERSEL": "Ouvre-porte de garage intégré",
        "TROUSSE DE REPARATION DE PNEUS": "Kit de réparation de pneus",
        "MOPAR": "Mopar (accessoire officiel)",
        "PASSENGER BUCKET SEAT": "Siège passager baquet",
        "CARGO AREA FLOOR MAT": "Tapis de plancher cargo",
        "KEY FOBS": "clés supplémentaires",
    }

    lines = options_text.strip().split("\n")
    humanized = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("▫️"):
            continue

        clean = line.lstrip("✅").lstrip("■").lstrip("-").strip()
        if not clean or len(clean) < 3:
            continue

        # Appliquer les traductions
        result = clean
        for raw, human in translations.items():
            if raw.upper() in result.upper():
                result = result.upper().replace(raw.upper(), human)
                break

        # Nettoyer les codes internes (2UZ, 22B, 2GH, etc.)
        result = re.sub(r'\b\d{1,2}[A-Z]{1,3}\b', '', result).strip()
        result = re.sub(r'\s+', ' ', result).strip()

        if result and len(result) > 3:
            humanized.append(result)

    return humanized[:8]  # Max 8 options


def build_vehicle_context(vehicle: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construit le contexte complet pour la génération de texte.
    Entrée: dictionnaire véhicule (title, stock, vin, price_int, km_int, etc.)
    Sortie: contexte enrichi avec intelligence véhicule
    """
    title = vehicle.get("title", "")
    parsed = parse_vehicle_title(title)
    profile = get_vehicle_profile(parsed)

    price = vehicle.get("price_int")
    km = vehicle.get("km_int")

    context = {
        # Identité
        "title": title,
        "brand": parsed["brand"],
        "model": parsed["model"],
        "trim": parsed["trim"],
        "year": parsed["year"],
        "color": parsed["color"],
        "stock": vehicle.get("stock", ""),
        "vin": vehicle.get("vin", ""),

        # Chiffres
        "price": price,
        "price_formatted": f"{price:,}".replace(",", " ") + " $" if price else "",
        "km": km,
        "km_formatted": f"{km:,}".replace(",", " ") + " km" if km else "",

        # Intelligence
        "vehicle_type": profile["vehicle_type"],
        "brand_tone": profile["brand_profile"]["tone"] if profile["brand_profile"] else "polyvalent",
        "brand_emoji": profile["brand_profile"]["emoji"] if profile["brand_profile"] else "🔥",
        "brand_identity": profile["brand_profile"]["identity"] if profile["brand_profile"] else "",
        "brand_angles": profile["brand_profile"]["angles"] if profile["brand_profile"] else [],
        "model_known_for": profile["known_for"],
        "hp": profile["hp"],
        "engine": profile["engine"],
        "trim_vibe": profile["vibe"],
        "km_description": km_description(km) if km else "",
        "price_description": price_description(price, profile["vehicle_type"]) if price else "",

        # URL
        "url": vehicle.get("url", ""),
    }

    return context
```

---

## FILE: vin_decoder.py
```python
"""
vin_decoder.py

Decode les VINs via l'API NHTSA vPIC (gratuit, sans cle API).
Retourne les specs du vehicule: moteur, HP, transmission, drive, places, securite.
"""

import requests
from typing import Dict, Any, Optional

NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"

# Cache simple en memoire pour eviter les appels repetitifs
_cache: Dict[str, Dict[str, Any]] = {}


def decode_vin(vin: str) -> Optional[Dict[str, Any]]:
    """
    Decode un VIN via NHTSA et retourne les specs utiles.
    Retourne None si le VIN est invalide ou vide.
    """
    vin = (vin or "").strip().upper()
    if len(vin) < 11:
        return None

    if vin in _cache:
        return _cache[vin]

    try:
        r = requests.get(NHTSA_URL.format(vin=vin), timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[VIN_DECODER] Erreur API NHTSA pour {vin}: {e}")
        return None

    raw = {}
    for item in data.get("Results", []):
        val = (item.get("Value") or "").strip()
        if val:
            raw[item["Variable"]] = val

    # Extraire les specs utiles
    specs = {
        "vin": vin,
        "make": raw.get("Make", ""),
        "model": raw.get("Model", ""),
        "year": raw.get("Model Year", ""),
        "trim": raw.get("Trim", ""),
        "body_class": raw.get("Body Class", ""),
        # Moteur
        "engine_cylinders": raw.get("Engine Number of Cylinders", ""),
        "engine_displacement_l": raw.get("Displacement (L)", ""),
        "engine_hp": raw.get("Engine Brake (hp) From", ""),
        "engine_model": raw.get("Engine Model", ""),
        "engine_config": raw.get("Engine Configuration", ""),
        "fuel_primary": raw.get("Fuel Type - Primary", ""),
        "fuel_secondary": raw.get("Fuel Type - Secondary", ""),
        "turbo": raw.get("Turbo", ""),
        "electrification": raw.get("Electrification Level", ""),
        # Transmission
        "transmission": raw.get("Transmission Style", ""),
        "transmission_speeds": raw.get("Transmission Speeds", ""),
        "drive_type": raw.get("Drive Type", ""),
        # Capacite
        "seats": raw.get("Number of Seats", ""),
        "seat_rows": raw.get("Number of Seat Rows", ""),
        "gvwr": raw.get("Gross Vehicle Weight Rating From", ""),
        # Fabrication
        "plant_country": raw.get("Plant Country", ""),
        "plant_city": raw.get("Plant City", ""),
        # Securite
        "abs": raw.get("Anti-lock Braking System (ABS)", ""),
        "esc": raw.get("Electronic Stability Control (ESC)", ""),
        "traction_control": raw.get("Traction Control", ""),
        "tpms": raw.get("Tire Pressure Monitoring System (TPMS) Type", ""),
        "keyless": raw.get("Keyless Ignition", ""),
        "adaptive_cruise": raw.get("Adaptive Cruise Control (ACC)", ""),
        "auto_braking": raw.get("Crash Imminent Braking (CIB)", ""),
        "forward_collision": raw.get("Forward Collision Warning (FCW)", ""),
        "pedestrian_braking": raw.get("Pedestrian Automatic Emergency Braking (PAEB)", ""),
        "blind_spot": raw.get("Blind Spot Warning (BSW)", ""),
        "lane_departure": raw.get("Lane Departure Warning (LDW)", ""),
        "lane_keeping": raw.get("Lane Keeping Assistance (LKA)", ""),
        "backup_camera": raw.get("Backup Camera", ""),
        "rear_cross_traffic": raw.get("Rear Cross Traffic Alert", ""),
        "headlamp_type": raw.get("Headlamp Light Source", ""),
        "drl": raw.get("Daytime Running Light (DRL)", ""),
    }

    _cache[vin] = specs
    return specs


def format_engine_line(specs: Dict[str, Any]) -> str:
    """Formate la ligne moteur lisible."""
    parts = []
    cyl = specs.get("engine_cylinders", "")
    disp = specs.get("engine_displacement_l", "")
    hp = specs.get("engine_hp", "")
    config = specs.get("engine_config", "")
    turbo = specs.get("turbo", "")

    if cyl and disp:
        eng = f"{cyl} cylindres"
        if config:
            eng += f" {config.lower()}"
        eng += f" {disp}L"
        parts.append(eng)
    elif disp:
        parts.append(f"{disp}L")

    if hp:
        parts.append(f"{hp} HP")

    if turbo and turbo.lower() not in ("", "not applicable"):
        parts.append("turbo")

    return " — ".join(parts) if parts else ""


def format_specs_for_prompt(specs: Dict[str, Any]) -> str:
    """Formate les specs en texte lisible pour le prompt IA."""
    if not specs:
        return ""

    lines = []

    # Moteur
    engine = format_engine_line(specs)
    if engine:
        lines.append(f"Moteur: {engine}")

    fuel = specs.get("fuel_primary", "")
    fuel2 = specs.get("fuel_secondary", "")
    elec = specs.get("electrification", "")
    if elec and "hev" in elec.lower():
        lines.append(f"Hybride: {elec}")
    elif fuel2 and fuel2.lower() == "electric":
        lines.append("Hybride (electrique secondaire)")
    elif fuel:
        lines.append(f"Carburant: {fuel}")

    # Transmission
    trans = specs.get("transmission", "")
    speeds = specs.get("transmission_speeds", "")
    if trans:
        t = trans
        if speeds:
            t += f" {speeds} vitesses"
        lines.append(f"Transmission: {t}")

    drive = specs.get("drive_type", "")
    if drive:
        lines.append(f"Motricite: {drive}")

    # Capacite
    seats = specs.get("seats", "")
    rows = specs.get("seat_rows", "")
    if seats:
        s = f"{seats} places"
        if rows and int(rows) > 2:
            s += f", {rows} rangees"
        lines.append(s)

    # Fabrication
    country = specs.get("plant_country", "")
    city = specs.get("plant_city", "")
    if country:
        fab = f"Fabrique: {country}"
        if city:
            fab += f" ({city})"
        lines.append(fab)

    # Securite
    safety = []
    safety_map = {
        "adaptive_cruise": "Cruise adaptatif",
        "auto_braking": "Freinage d'urgence automatique",
        "pedestrian_braking": "Detection pietons",
        "blind_spot": "Avertissement angle mort",
        "lane_keeping": "Aide au maintien de voie",
        "lane_departure": "Avertissement sortie de voie",
        "backup_camera": "Camera de recul",
        "rear_cross_traffic": "Alerte trafic transversal arriere",
        "keyless": "Demarrage sans cle",
    }
    for key, label in safety_map.items():
        val = specs.get(key, "")
        if val and val.lower() in ("standard", "yes"):
            safety.append(label)

    headlamp = specs.get("headlamp_type", "")
    if headlamp and "led" in headlamp.lower():
        safety.append("Phares LED")

    if safety:
        lines.append(f"Securite de serie: {', '.join(safety)}")

    return "\n".join(lines)
```

---

## FILE: ad_builder.py
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ad_builder.py
from __future__ import annotations

import re
from typing import Any, Dict, List

# -----------------------------
# Blacklist (Window Sticker)
# -----------------------------
BLACKLIST_TERMS = (
    "ECOPRELEVEMENT", "ECO PRELEVEMENT", "ECO-PRÉLÈVEMENT", "ÉCOPRÉLÈVEMENT", "ECOPRÉLÈVEMENT",
    "FEDERAL", "FÉDÉRAL",
    "TAX", "TAXE",
    "FEE", "FRAIS",
    "LEVY", "PRÉLÈVEMENT", "PRELEVEMENT",
    "DESTINATION", "EXPEDITION", "EXPÉDITION",
    "MSRP", "PRIX TOTAL", "TOTAL PRICE",
)

def is_blacklisted_line(s: str) -> bool:
    if not s:
        return True
    u = s.upper()
    return any(t in u for t in BLACKLIST_TERMS)


# -----------------------------
# Hashtags / Marques
# -----------------------------
def choose_hashtags(title: str) -> str:
    base = [
        "#VehiculeOccasion", "#AutoUsagée", "#Quebec", "#Beauce",
        "#SaintGeorges", "#KennebecDodge", "#DanielGiroux"
    ]
    low = (title or "").lower()
    if "ram" in low:
        base.insert(0, "#RAM")
    if "jeep" in low:
        base.insert(0, "#Jeep")
    if "dodge" in low:
        base.insert(0, "#Dodge")
    if "chrysler" in low:
        base.insert(0, "#Chrysler")

    out: List[str] = []
    seen = set()
    for t in base:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return " ".join(out)


def is_allowed_stellantis_brand(txt: str) -> bool:
    low = (txt or "").lower()
    allowed = (
        "ram", "dodge", "jeep", "chrysler",
        "alfa", "alfaromeo", "alfa romeo",
        "fiat", "wagoneer"
    )
    return any(a in low for a in allowed)


# -----------------------------
# Normalisation Prix / KM
# -----------------------------
def _digits_only(s: str) -> str:
    return re.sub(r"[^\d]", "", s or "")


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def normalize_price(price: str) -> str:
    """
    Accepte:
      "33995", "33 995", "33,995", "33 995 $", "CAD 33995"
    Retour:
      "33 995 $"
    """
    raw = (price or "").strip()
    if not raw:
        return ""

    digits = _digits_only(raw)
    if not digits:
        return ""

    try:
        n = int(digits)
    except Exception:
        return ""

    # garde-fou anti-n'importe-quoi
    if n < 1000 or n > 500000:
        return ""

    return f"{_fmt_int(n)} $"


def normalize_km(mileage: str) -> str:
    """
    Sort TOUJOURS "xx xxx km"
    Supporte miles -> km si le texte contient mi/miles/mile.
    """
    raw = (mileage or "").strip().lower()
    if not raw:
        return ""

    digits = _digits_only(raw)
    if not digits:
        return ""

    try:
        n = int(digits)
    except Exception:
        return ""

    if n < 0 or n > 600000:
        return ""

    is_miles = (" mi" in raw) or raw.endswith("mi") or ("miles" in raw) or ("mile" in raw)
    if is_miles:
        n = int(round(n * 1.60934))

    return f"{_fmt_int(n)} km"


# -----------------------------
# Builder final (texte prêt à publier)
# -----------------------------
def build_ad(
    title: str,
    price: str,
    mileage: str,
    stock: str,
    vin: str,
    options: List[Dict[str, Any]],
    *,
    vehicle_url: str = "",
) -> str:
    lines: List[str] = []

    t = (title or "").strip()
    s = (stock or "").strip().upper()
    v = (vin or "").strip().upper()

    p = normalize_price(price)
    m = normalize_km(mileage)

    # --- Titre ---
    if t:
        lines.append(f"🔥 {t} 🔥")
        lines.append("")

    # --- Infos clés ---
    if p:
        lines.append(f"💥 {p} 💥")
    if m:
        lines.append(f"📊 Kilométrage : {m}")
    if s:
        lines.append(f"🧾 Stock : {s}")
    lines.append("")

    # --- Accessoires (Window Sticker) ---
    if options:
        lines.append("✨ ACCESSOIRES OPTIONNELS (Window Sticker)")
        lines.append("")

        seen_titles = set()

        for g in options:
            tt = (g.get("title") or "").strip()
            details = g.get("details") or []

            # skip titres vides / blacklisted / doublons
            if not tt or is_blacklisted_line(tt):
                continue
            k = tt.casefold()
            if k in seen_titles:
                continue
            seen_titles.add(k)

            # ✅ IMPORTANT: on n'affiche JAMAIS le prix des options
            lines.append(f"✅  {tt}")

            # sous-options filtrées + blacklist + dédoublonnage
            seen_details = set()
            kept = 0
            for d in details:
                if kept >= 6:
                    break
                dd = (d or "").strip()
                if not dd or is_blacklisted_line(dd):
                    continue
                dk = dd.casefold()
                if dk in seen_details:
                    continue
                seen_details.add(dk)

                lines.append(f"        ▫️ {dd}")
                kept += 1

        lines.append("")
        lines.append("📌 Le reste des détails est dans le Window Sticker :")
        lines.append("")
        if v:
            lines.append(f"https://www.chrysler.com/hostd/windowsticker/getWindowStickerPdf.do?vin={v}")
        else:
            lines.append("(VIN introuvable — lien Window Sticker non généré)")
        lines.append("")

    # --- Lien Kennebec (optionnel) ---
    if vehicle_url:
        lines.append("🔗 Fiche complète :")
        lines.append(vehicle_url)
        lines.append("")

    # --- Échanges ---
    lines.append("🔁 J’accepte les échanges : 🚗 auto • 🏍️ moto • 🛥️ bateau • 🛻 VTT • 🏁 côte-à-côte")
    lines.append("📸 Envoie-moi les photos + infos de ton échange (année / km / paiement restant) → je te reviens vite.")

    return "\n".join(lines).strip() + "\n"
```

---

## FILE: footer_utils.py
```python
# -*- coding: utf-8 -*-
"""
footer_utils.py - Module centralisé pour la gestion du footer Daniel Giroux.

RÈGLE D'OR: Le footer ne doit être ajouté qu'UNE SEULE FOIS, à UN SEUL ENDROIT.
Ce module est la source de vérité pour:
1. Détecter si un footer existe déjà
2. Ajouter un footer si nécessaire
3. Générer le footer standard

Usage:
    from footer_utils import has_footer, add_footer_if_missing, get_dealer_footer
"""

from __future__ import annotations
from typing import List, Optional

# ============================================================
# CONFIGURATION DU FOOTER
# ============================================================

DEALER_NAME = "Daniel Giroux"
DEALER_PHONE = "418-222-3939"
DEALER_LOCATION = "Saint-Georges (Beauce)"

# Marqueurs qui indiquent qu'un footer est déjà présent
# Si 2+ de ces marqueurs sont trouvés, on considère qu'il y a un footer
FOOTER_MARKERS = [
    "418-222-3939",
    "418 222 3939",
    "daniel giroux",
    "j'accepte les échanges",
    "j'accepte les echanges",
    "écris-moi en privé",
    "ecris-moi en prive",
    "#danielgiroux",
    "[[dg_footer]]",
]

# Seuil: combien de marqueurs minimum pour considérer qu'un footer existe
FOOTER_MARKER_THRESHOLD = 1  # 1 seul marqueur suffit (le téléphone est unique)


# ============================================================
# DÉTECTION DE FOOTER
# ============================================================

def has_footer(text: str) -> bool:
    """
    Détecte si un footer Daniel Giroux est déjà présent dans le texte.
    
    Returns:
        True si un footer est détecté, False sinon.
    """
    if not text:
        return False
    
    low = text.lower()
    
    # Vérification rapide: le téléphone est unique et obligatoire
    if DEALER_PHONE in text or "418 222 3939" in text:
        return True
    
    # Vérification secondaire: compter les marqueurs
    matches = sum(1 for marker in FOOTER_MARKERS if marker in low)
    return matches >= FOOTER_MARKER_THRESHOLD


def count_footer_occurrences(text: str) -> int:
    """
    Compte combien de fois le footer semble apparaître.
    Utile pour détecter les doubles footers.
    
    Returns:
        Nombre d'occurrences du téléphone (indicateur principal).
    """
    if not text:
        return 0
    return text.count(DEALER_PHONE) + text.count("418 222 3939")


def has_double_footer(text: str) -> bool:
    """
    Détecte si un texte a un DOUBLE footer (bug à corriger).
    
    Returns:
        True si double footer détecté.
    """
    return count_footer_occurrences(text) > 1


# ============================================================
# GÉNÉRATION DU FOOTER
# ============================================================

def get_dealer_footer(
    include_echanges: bool = True,
    include_hashtags: bool = True,
    hashtags: Optional[List[str]] = None,
) -> str:
    """
    Génère le footer standard Daniel Giroux.
    
    Args:
        include_echanges: Inclure la section "J'accepte les échanges"
        include_hashtags: Inclure les hashtags
        hashtags: Liste de hashtags personnalisés (sinon défaut)
    
    Returns:
        Le footer formaté.
    """
    lines = []
    
    if include_echanges:
        lines.append("🔁 J'accepte les échanges : 🚗 auto • 🏍️ moto • 🛥️ bateau • 🛻 VTT • 🏁 côte-à-côte")
        lines.append("📸 Envoie-moi les photos + infos de ton échange (année / km / paiement restant) → je te reviens vite.")
        lines.append("")
    
    lines.append(f"📞 {DEALER_NAME} — {DEALER_PHONE}")
    
    if include_hashtags:
        if hashtags:
            lines.append(" ".join(hashtags))
        else:
            lines.append("#DanielGiroux #Beauce #Quebec #SaintGeorges")
    
    return "\n".join(lines).strip()


def get_minimal_footer() -> str:
    """
    Retourne un footer minimal (juste le téléphone).
    Utilisé quand on veut s'assurer que le contact est présent.
    """
    return f"📞 {DEALER_NAME} {DEALER_PHONE}"


# ============================================================
# AJOUT INTELLIGENT DU FOOTER
# ============================================================

def add_footer_if_missing(
    text: str,
    footer: Optional[str] = None,
    force_minimal: bool = False,
) -> str:
    """
    Ajoute le footer UNIQUEMENT s'il n'est pas déjà présent.
    
    C'est LA fonction à utiliser partout pour éviter les doubles footers.
    
    Args:
        text: Le texte à traiter
        footer: Footer personnalisé (sinon footer standard)
        force_minimal: Si True, utilise le footer minimal
    
    Returns:
        Le texte avec footer (ajouté ou non selon détection).
    """
    text = (text or "").strip()
    
    if not text:
        return text
    
    # Si footer déjà présent, ne rien faire
    if has_footer(text):
        return text
    
    # Choisir le footer à ajouter
    if footer:
        footer_to_add = footer
    elif force_minimal:
        footer_to_add = get_minimal_footer()
    else:
        footer_to_add = get_dealer_footer()
    
    return f"{text}\n\n{footer_to_add}".strip()


def ensure_contact_present(text: str) -> str:
    """
    S'assure que le numéro de téléphone est présent.
    N'ajoute que le minimum si absent.
    
    C'est une version "légère" de add_footer_if_missing.
    """
    text = (text or "").strip()
    
    if not text:
        return text
    
    # Si le téléphone est déjà là, rien à faire
    if DEALER_PHONE in text or "418 222 3939" in text:
        return text
    
    # Ajouter seulement le contact minimal
    return f"{text}\n\n{get_minimal_footer()}".strip()


# ============================================================
# NETTOYAGE
# ============================================================

def remove_footer_marker(text: str) -> str:
    """
    Retire le marqueur [[DG_FOOTER]] s'il est présent.
    Ce marqueur est utilisé pour éviter les doublons mais ne doit pas
    apparaître dans le texte final.
    """
    return (text or "").replace("[[DG_FOOTER]]", "").replace("[[dg_footer]]", "").strip()


def clean_double_footer(text: str) -> str:
    """
    Tente de nettoyer un double footer.
    
    ⚠️ À utiliser avec précaution - préférer prévenir que guérir.
    """
    if not has_double_footer(text):
        return text
    
    # Stratégie simple: trouver la dernière occurrence du téléphone
    # et garder tout ce qui est avant + cette dernière occurrence
    
    # TODO: Implémenter si nécessaire
    # Pour l'instant, on retourne le texte tel quel
    return text


# ============================================================
# HELPERS POUR HASHTAGS
# ============================================================

def smart_hashtags(
    make: str = "",
    model: str = "",
    title: str = "",
    event: str = "NEW",
) -> List[str]:
    """
    Génère des hashtags intelligents basés sur le véhicule.
    """
    tags = ["#DanielGiroux", "#Beauce", "#Quebec", "#SaintGeorges"]
    
    # Event
    if event == "PRICE_CHANGED":
        tags.insert(0, "#BaisseDePrix")
    elif event == "NEW":
        tags.insert(0, "#NouvelArrivage")
    
    # Marque
    text_blob = f"{make} {model} {title}".lower()
    
    brand_tags = {
        "ram": ["#RAM", "#Truck"],
        "jeep": ["#Jeep", "#4x4"],
        "dodge": ["#Dodge"],
        "chrysler": ["#Chrysler"],
        "toyota": ["#Toyota"],
        "honda": ["#Honda"],
        "ford": ["#Ford"],
        "chevrolet": ["#Chevrolet", "#Chevy"],
        "gmc": ["#GMC"],
    }
    
    for brand, btags in brand_tags.items():
        if brand in text_blob:
            tags = btags + tags
            break
    
    # Caractéristiques
    if "4x4" in text_blob or "awd" in text_blob or "4wd" in text_blob:
        if "#4x4" not in tags:
            tags.append("#4x4")
    
    if "hybrid" in text_blob or "hybride" in text_blob:
        tags.append("#Hybride")
    
    # Dédoublonner
    seen = set()
    unique = []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)
    
    return unique[:12]


# ============================================================
# TESTS INTÉGRÉS
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST footer_utils.py")
    print("=" * 60)
    
    # Test 1: Détection sans footer
    text_no_footer = "🔥 RAM 1500 2022 🔥\n\n💥 34 995 $ 💥"
    assert not has_footer(text_no_footer), "FAIL: Faux positif"
    print("✅ Test 1: Texte sans footer détecté correctement")
    
    # Test 2: Détection avec footer
    text_with_footer = "🔥 RAM 1500 🔥\n\n📞 Daniel Giroux — 418-222-3939"
    assert has_footer(text_with_footer), "FAIL: Faux négatif"
    print("✅ Test 2: Texte avec footer détecté correctement")
    
    # Test 3: Ajout de footer
    result = add_footer_if_missing(text_no_footer)
    assert has_footer(result), "FAIL: Footer non ajouté"
    assert count_footer_occurrences(result) == 1, "FAIL: Double footer"
    print("✅ Test 3: Footer ajouté correctement")
    
    # Test 4: Pas de double ajout
    result2 = add_footer_if_missing(result)
    assert count_footer_occurrences(result2) == 1, "FAIL: Double footer après 2e appel"
    print("✅ Test 4: Pas de double footer après 2e appel")
    
    # Test 5: Double footer détecté
    double = text_with_footer + "\n\n📞 Daniel Giroux — 418-222-3939"
    assert has_double_footer(double), "FAIL: Double footer non détecté"
    print("✅ Test 5: Double footer détecté")
    
    print("\n" + "=" * 60)
    print("🎉 TOUS LES TESTS PASSENT!")
    print("=" * 60)
```

---

## FILE: fb_api.py
```python
import json
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional

GRAPH_VER = "v24.0"


def _graph(url: str) -> str:
    return f"https://graph.facebook.com/{GRAPH_VER}/{url.lstrip('/')}"


def _json_or_text(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def publish_photos_unpublished(
    page_id: str,
    token: str,
    photo_paths: List[Path],
    limit: int = 10
) -> List[str]:
    """
    Upload photos as unpublished to get media_fbid IDs.
    Returns list of media IDs.
    """
    media_ids: List[str] = []
    for p in photo_paths[:limit]:
        url = _graph(f"{page_id}/photos")
        with open(p, "rb") as f:
            resp = requests.post(
                url,
                params={"access_token": token},
                data={"published": "false"},
                files={"source": f},
                timeout=120,
            )

        payload = _json_or_text(resp)
        if not resp.ok:
            raise RuntimeError(f"FB upload photo failed {resp.status_code}: {payload}")

        mid = payload.get("id")
        if not mid:
            raise RuntimeError(f"FB upload photo missing id: {payload}")

        media_ids.append(mid)

    return media_ids


def create_post_with_attached_media(
    page_id: str,
    token: str,
    message: str,
    media_ids: List[str]
) -> str:
    """
    Create a page feed post with attached media.
    Returns post_id (string) for backward compatibility.
    """
    url = _graph(f"{page_id}/feed")
    data: Dict[str, str] = {"message": message}

    for i, mid in enumerate(media_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})

    resp = requests.post(url, params={"access_token": token}, data=data, timeout=120)
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB create post failed {resp.status_code}: {payload}")

    post_id = payload.get("id")
    if not post_id:
        raise RuntimeError(f"FB create post missing id: {payload}")

    return post_id


def create_post_with_attached_media_full(
    page_id: str,
    token: str,
    message: str,
    media_ids: List[str]
) -> Dict[str, Any]:
    """
    Same as create_post_with_attached_media but returns full Meta payload.
    """
    url = _graph(f"{page_id}/feed")
    data: Dict[str, str] = {"message": message}

    for i, mid in enumerate(media_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": mid})

    resp = requests.post(url, params={"access_token": token}, data=data, timeout=120)
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB create post failed {resp.status_code}: {payload}")

    if not payload.get("id"):
        raise RuntimeError(f"FB create post missing id: {payload}")

    return payload


def update_post_text(post_id: str, token: str, message: str) -> Dict[str, Any]:
    """
    Update an existing post's message.
    Returns full Meta payload (so you can log it).
    """
    url = _graph(post_id)
    resp = requests.post(
        url,
        params={"access_token": token},
        data={"message": message},
        timeout=60,
    )
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB update text failed {resp.status_code}: {payload}")

    return payload


def delete_post(post_id: str, token: str) -> bool:
    """
    Supprime un post Facebook.
    
    Args:
        post_id: ID du post à supprimer
        token: Token d'accès de la page
    
    Returns:
        True si suppression réussie, False sinon.
    """
    url = _graph(post_id)
    resp = requests.delete(
        url,
        params={"access_token": token},
        timeout=60,
    )
    payload = _json_or_text(resp)

    if not resp.ok:
        print(f"[FB DELETE] Failed {resp.status_code}: {payload}")
        return False

    return payload.get("success", False)


def comment_on_post(post_id: str, token: str, message: str) -> str:
    """
    Create a comment on a post. Returns comment_id (string).
    """
    url = _graph(f"{post_id}/comments")
    resp = requests.post(url, params={"access_token": token}, data={"message": message}, timeout=60)
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB comment failed {resp.status_code}: {payload}")

    return payload.get("id", "")


def comment_photo(post_id: str, token: str, attachment_id: str, message: str = "") -> str:
    """
    Comment with a photo attachment (attachment_id = media_fbid). Returns comment_id.
    """
    url = _graph(f"{post_id}/comments")
    data: Dict[str, str] = {"attachment_id": attachment_id}
    if message:
        data["message"] = message

    resp = requests.post(url, params={"access_token": token}, data=data, timeout=60)
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB comment photo failed {resp.status_code}: {payload}")

    return payload.get("id", "")


def publish_photos_as_comment_batch(
    page_id: str, 
    token: str, 
    post_id: str, 
    photo_paths: List[Path],
    message: str = "📸 Suite des photos 👇"
) -> None:
    """
    Publie les photos extra en commentaires (pas en posts).
    
    Args:
        page_id: ID de la page Facebook
        token: Token d'accès
        post_id: ID du post existant
        photo_paths: Liste des chemins vers les photos
        message: Message d'introduction (défaut: "📸 Suite des photos 👇")
    """
    if not photo_paths:
        return

    # Commentaire d'introduction (best-effort)
    try:
        comment_on_post(post_id, token, message)
    except Exception:
        pass

    # Upload en unpublished, puis attache chaque photo au post via commentaire
    for p in photo_paths:
        url = _graph(f"{page_id}/photos")
        with open(p, "rb") as f:
            resp = requests.post(
                url,
                params={"access_token": token},
                data={"published": "false"},
                files={"source": f},
                timeout=120,
            )

        payload = _json_or_text(resp)
        if not resp.ok:
            raise RuntimeError(f"FB upload extra photo failed {resp.status_code}: {payload}")

        mid = payload.get("id")
        if not mid:
            raise RuntimeError(f"FB upload extra photo missing id: {payload}")

        # Attache la photo comme commentaire (PAS un post)
        comment_photo(post_id, token, attachment_id=mid)


def fetch_fb_post_message(post_id: str, token: str) -> str:
    """
    Fetch current post message (proof after update).
    """
    url = _graph(post_id)
    resp = requests.get(
        url,
        params={"access_token": token, "fields": "message"},
        timeout=30,
    )
    payload = _json_or_text(resp)

    if not resp.ok:
        raise RuntimeError(f"FB fetch post failed {resp.status_code}: {payload}")

    return (payload or {}).get("message") or ""


# Alias (si tu veux un nom plus court)
def fetch_post_message(post_id: str, token: str) -> str:
    return fetch_fb_post_message(post_id, token)
```

---

## FILE: text_engine_client.py
```python
import time
from typing import Any, Dict

import requests

# Import du module centralisé pour la gestion du footer
from footer_utils import (
    has_footer,
    add_footer_if_missing,
    get_dealer_footer,
    smart_hashtags,
    remove_footer_marker,
    DEALER_PHONE,
)

FOOTER_MARKER = "[[DG_FOOTER]]"


def _fmt_money(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        n = int(float(value))
        return f"{n:,}".replace(",", " ") + " $"
    except Exception:
        return str(value).strip()


def _fmt_km(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        n = int(float(value))
        return f"{n:,}".replace(",", " ") + " km"
    except Exception:
        return str(value).strip()


def _vehicle_price(vehicle: Dict[str, Any]) -> str:
    v = vehicle or {}
    raw = v.get("price")
    if raw in (None, ""):
        raw = v.get("price_int")
    return _fmt_money(raw)


def _vehicle_mileage(vehicle: Dict[str, Any]) -> str:
    v = vehicle or {}
    raw = v.get("mileage")
    if raw in (None, ""):
        raw = v.get("km")
    if raw in (None, ""):
        raw = v.get("km_int")
    return _fmt_km(raw)


def _smart_hashtags(vehicle: Dict[str, Any], event: str) -> str:
    v = vehicle or {}
    title = (v.get("title") or "").lower()
    text_blob = f"{title} {str(v).lower()}"

    tags = [
        "#DanielGiroux",
        "#Beauce",
        "#Quebec",
        "#SaintGeorges",
        "#Thetford",
    ]

    if event == "PRICE_CHANGED":
        tags.append("#BaisseDePrix")
    elif event == "NEW":
        tags.append("#NouvelArrivage")

    if "awd" in text_blob or "4x4" in text_blob:
        tags.append("#AWD")

    if "jeep" in title:
        tags.append("#Jeep")
    elif "ram" in title:
        tags.append("#Ram")
    elif "dodge" in title:
        tags.append("#Dodge")
    elif "chrysler" in title:
        tags.append("#Chrysler")

    if "challenger" in title:
        tags.append("#Challenger")
    if "hornet" in title:
        tags.append("#Hornet")
    if "wagoneer" in title:
        tags.append("#Wagoneer")
    if "big horn" in title:
        tags.append("#BigHorn")

    seen = set()
    out = []
    for tag in tags:
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            out.append(tag)

    return " ".join(out[:10]).strip()


def _dealer_footer(vehicle: Dict[str, Any], event: str) -> str:
    tags = _smart_hashtags(vehicle, event)
    return (
        "🔁 J’accepte les échanges : 🚗 auto • 🏍️ moto • 🛥️ bateau • 🛻 VTT • 🏁 côte-à-côte\n"
        "📸 Envoie-moi les photos + infos de ton échange (année / km / paiement restant) → je te reviens vite.\n"
        "📞 Daniel Giroux 418-222-3939\n"
        f"{tags}\n"
        f"{FOOTER_MARKER}"
    ).strip()


def ensure_single_footer(text: str, footer: str) -> str:
    """
    Ajoute le footer UNIQUEMENT si aucun footer n'est présent.
    Utilise footer_utils.has_footer pour une détection fiable.
    """
    base = (text or "").rstrip()
    
    # Utiliser la détection centralisée
    if has_footer(base):
        return remove_footer_marker(base)
    
    # Vérifier aussi le marqueur legacy
    if FOOTER_MARKER.lower() in base.lower():
        return remove_footer_marker(base)
    
    return f"{base}\n\n{footer}".strip()


def _fallback_text(slug: str, event: str, vehicle: Dict[str, Any]) -> str:
    v = vehicle or {}
    title = (v.get("title") or "Véhicule").strip()
    stock = (v.get("stock") or "").strip()
    vin = (v.get("vin") or "").strip()
    url = (v.get("url") or "").strip()
    price = _vehicle_price(v)
    mileage = _vehicle_mileage(v)
    old_price = _fmt_money(v.get("old_price"))
    new_price = _fmt_money(v.get("new_price"))

    lines = []

    if event == "PRICE_CHANGED" and old_price and new_price:
        lines.append(f"💥 Nouveau prix pour ce {title} !")
        lines.append("")
        lines.append(f"Avant : {old_price}")
        lines.append(f"Maintenant : {new_price}")
        lines.append("")
        lines.append("Si vous l’aviez à l’œil, c’est peut-être le bon moment pour passer à l’action.")
    else:
        lines.append(f"🔥 {title}")
        if price:
            lines.append(f"💰 {price}")
        if mileage:
            lines.append(f"📊 {mileage}")

    if stock:
        lines.append(f"🧾 Stock : {stock}")
    if vin:
        lines.append(f"🔢 VIN : {vin}")
    if url:
        lines.append("")
        lines.append(url)

    lines.append("")
    lines.append("📞 Daniel Giroux 418-222-3939")

    return "\n".join(lines).strip()


def generate_facebook_text(base_url: str, slug: str, event: str, vehicle: dict) -> str:
    url = f"{base_url.rstrip('/')}/generate"
    payload = {"slug": slug, "event": event, "vehicle": vehicle}

    last_err = None
    for attempt in range(1, 4):
        try:
            r = requests.post(url, json=payload, timeout=120)
            r.raise_for_status()
            j = r.json()

            txt = (j.get("facebook_text") or j.get("text") or "").strip()
            if txt:
                return ensure_single_footer(txt, _dealer_footer(vehicle, event))

            return ensure_single_footer(
                _fallback_text(slug, event, vehicle),
                _dealer_footer(vehicle, event),
            )

        except Exception as e:
            last_err = e
            time.sleep(2 * attempt)

    print(f"[TEXT_ENGINE FALLBACK] slug={slug} event={event} err={last_err}")
    return ensure_single_footer(
        _fallback_text(slug, event, vehicle),
        _dealer_footer(vehicle, event),
    )
```

---

## FILE: kennebec_scrape.py
```python
import re
import requests
import json
from bs4 import BeautifulSoup
from typing import Any, Dict, List, Set, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

def _clean_price_int(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"(\d[\d\s.,]{2,})\s*\$", s)
    if not m:
        return None
    n = re.sub(r"[^\d]", "", m.group(1))
    try:
        return int(n)
    except Exception:
        return None

def _clean_km_int(s: str) -> Optional[int]:
    if not s:
        return None
    m = re.search(r"(\d[\d\s.,]{2,})\s*km", s.lower())
    if not m:
        return None
    n = re.sub(r"[^\d]", "", m.group(1))
    try:
        return int(n)
    except Exception:
        return None

def slugify(title: str, stock: str) -> str:
    base = (title or "").lower()
    base = re.sub(r"[^a-z0-9]+", "-", base)
    base = re.sub(r"-+", "-", base).strip("-")
    stock = (stock or "").strip().upper()
    return f"{base}-{stock.lower()}"

def fetch_html(session: requests.Session, url: str, timeout: int = 30) -> str:
    r = session.get(url, timeout=timeout)
    r.raise_for_status()
    return r.text

def parse_inventory_listing_urls(base_url: str, inventory_path: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: Set[str] = set()

    def add(u: str) -> None:
        if not u:
            return
        full = u if u.startswith("http") else urljoin(base_url, u)
        parts = urlsplit(full)
        path = parts.path or ""
        if not path.startswith(inventory_path):
            return
        if not re.search(r"-id\d+$", path.rstrip("/"), re.IGNORECASE):
            return
        clean = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
        out.add(clean)

    for a in soup.find_all("a", href=True):
        add(a.get("href") or "")

    for m in re.findall(r'(/fr/inventaire-occasion/[^\s"\'<>]+?-id\d+)', html, flags=re.IGNORECASE):
        add(m)

    return sorted(out)

def _uniq_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for x in items or []:
        s = " ".join(str(x).split()).strip()
        if not s:
            continue
        k = s.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _extract_features_from_html(html: str) -> Dict[str, Any]:
    """
    Essaie d'extraire features/comfort/specs depuis des JSON embarqués.
    Kennebec/Dilawri met souvent un gros objet 'vehicleDetails' dans la page.
    """
    out: Dict[str, Any] = {"features": [], "comfort": [], "specs": {}}

    # 1) Cherche un bloc JSON "vehicleDetails": {...}
    m = re.search(r'vehicleDetails"\s*:\s*({.*?})\s*,\s*"isNew"', html, flags=re.DOTALL)
    if not m:
        # fallback: parfois 'vehicleDetails = {...};'
        m = re.search(r"vehicleDetails\s*=\s*({.*?})\s*;\s*", html, flags=re.DOTALL)

    if not m:
        return out

    raw = m.group(1)

    # on tente un json.loads après nettoyage léger
    try:
        # remplace les guillemets simples si c'est du JSON "presque"
        # (si ça pète, on retourne vide)
        data = json.loads(raw)
    except Exception:
        return out

    # mapping le plus courant
    specs = data.get("specs") or data.get("specifications") or {}
    if isinstance(specs, dict):
        out["specs"] = {str(k): str(v) for k, v in specs.items() if v}

    feats = data.get("features") or data.get("options") or []
    if isinstance(feats, list):
        out["features"] = _uniq_keep_order(feats)

    comfort = data.get("comfort") or data.get("comfortFeatures") or []
    if isinstance(comfort, list):
        out["comfort"] = _uniq_keep_order(comfort)

    return out


def _extract_list_near_heading(soup: BeautifulSoup, keywords: List[str]) -> List[str]:
    """
    Fallback HTML: cherche un titre contenant un keyword, puis récupère les <li> proches.
    """
    keys = [k.lower() for k in keywords]
    for node in soup.find_all(["h2", "h3", "h4", "div", "span"]):
        t = " ".join(node.get_text(" ", strip=True).split()).lower()
        if any(k in t for k in keys):
            parent = node.parent
            lis = parent.find_all("li")
            items = []
            for li in lis:
                s = " ".join(li.get_text(" ", strip=True).split()).strip()
                if s:
                    items.append(s)
            return _uniq_keep_order(items)
    return []

def _extract_headline_line(soup: BeautifulSoup) -> str:
    """
    Ligne juste sous le H1, souvent du style '*AWD*TOIT PANO*...*'
    """
    h1 = soup.find("h1")
    if not h1:
        return ""
    # regarde les 1-3 prochains blocs texte
    for sib in h1.find_all_next(["p", "div", "h2", "span"], limit=6):
        txt = sib.get_text(" ", strip=True)
        if not txt:
            continue
        # on veut la ligne avec plein d'étoiles / séparateurs
        if txt.count("*") >= 4 or ("•" in txt) or ("|" in txt):
            return txt.strip()
        # parfois c'est sans étoiles mais très “liste”
        if len(txt) > 25 and txt.count(" ") <= 6 and txt.count("-") == 0:
            return txt.strip()
    return ""


def _extract_specs_dict(soup: BeautifulSoup) -> Dict[str, str]:
    """
    Extrait le tableau "Spécifications" en dict {label: value}.
    Sur Kennebec, c'est souvent une grille 2 colonnes.
    """
    wanted = {
        "Transmission": "transmission",
        "Kilométrage": "kilometrage",
        "Chassis": "chassis",
        "Passagers": "passagers",
        "Cylindres": "cylindres",
        "Entraînement": "entrainement",
        "Entrainement": "entrainement",
        "Inventaire #": "inventaire",
        "Carburant": "carburant",
        "Couleur ext.": "couleur_ext",
        "Couleur int.": "couleur_int",
    }

    specs: Dict[str, str] = {}

    # stratégie: trouver l'endroit où il y a "Spécifications"
    anchor = None
    for n in soup.find_all(["h2", "h3", "h4", "div", "span"]):
        t = n.get_text(" ", strip=True).lower()
        if "spécification" in t or "specification" in t:
            anchor = n
            break

    if not anchor:
        return specs

    # Dans le bloc parent, prendre toutes les paires "Label:" -> "Valeur"
    container = anchor.parent
    texts = [x.get_text(" ", strip=True) for x in container.find_all(["div", "span", "p"], limit=200)]
    texts = [t for t in texts if t]

    # fallback si le parent est trop petit : élargir un peu
    if len(texts) < 10:
        container = anchor.find_parent(["section", "div"]) or container
        texts = [x.get_text(" ", strip=True) for x in container.find_all(["div", "span", "p"], limit=400)]
        texts = [t for t in texts if t]

    # parse en paires
    for i, t in enumerate(texts):
        tt = t.strip()
        if not tt.endswith(":"):
            continue
        label = tt[:-1].strip()
        key = wanted.get(label)
        if not key:
            continue
        # valeur = prochain texte non vide
        val = ""
        for j in range(i + 1, min(i + 6, len(texts))):
            cand = texts[j].strip()
            if cand and not cand.endswith(":"):
                val = cand
                break
        if val:
            specs[key] = val

    return specs
    
def parse_vehicle_detail_simple(session: requests.Session, url: str) -> Dict[str, Any]:
    """
    Enrichi : titre/price/km + photos sm360 + options (features/comfort/specs + headline)
    Stratégie:
      - parse HTML (sections, titres, listes <li>)
      - récupérer la ligne sous le H1 (headline_features)
      - récupérer le tableau Spécifications en dict
      - dédoublonner / normaliser
    """
    html = fetch_html(session, url)
    soup = BeautifulSoup(html, "html.parser")

    def norm_txt(s: str) -> str:
        s = (s or "").strip()
        s = re.sub(r"\s+", " ", s)
        return s

    def uniq_keep_order(items: List[str]) -> List[str]:
        seen = set()
        out: List[str] = []
        for x in items or []:
            x = norm_txt(x)
            if not x:
                continue
            k = x.casefold()
            if k in seen:
                continue
            seen.add(k)
            out.append(x)
        return out

    def extract_list_near_heading(keywords: List[str]) -> List[str]:
        keys = [k.lower() for k in keywords]
        for node in soup.find_all(["h2", "h3", "h4", "div", "span"]):
            t = norm_txt(node.get_text(" ", strip=True)).lower()
            if not t:
                continue
            if any(k in t for k in keys):
                parent = node.parent
                lis = parent.find_all("li")
                items = []
                for li in lis:
                    s = norm_txt(li.get_text(" ", strip=True))
                    if s:
                        items.append(s)
                items = uniq_keep_order(items)
                if items:
                    return items
        return []

    def extract_headline_line() -> str:
        """
        Ligne juste sous le H1, souvent '*AWD*TOIT PANO*...*'
        """
        h1 = soup.find("h1")
        if not h1:
            return ""
        # regarde quelques siblings/prochains blocs texte
        for sib in h1.find_all_next(["p", "div", "span"], limit=10):
            txt = norm_txt(sib.get_text(" ", strip=True))
            if not txt:
                continue
            # heuristique: beaucoup de *
            if txt.count("*") >= 4:
                return txt
            # ou des séparateurs
            if txt.count("•") >= 2 or txt.count("|") >= 2:
                return txt
        return ""

    def extract_specs_dict() -> Dict[str, str]:
        """
        Extrait le bloc 'Spécifications' en dict.
        Sur Kennebec: lignes du type 'Transmission:' puis valeur.
        """
        wanted = {
            "Transmission": "transmission",
            "Kilométrage": "kilometrage",
            "Chassis": "chassis",
            "Passagers": "passagers",
            "Cylindres": "cylindres",
            "Entraînement": "entrainement",
            "Entrainement": "entrainement",
            "Inventaire #": "inventaire",
            "Carburant": "carburant",
            "Couleur ext.": "couleur_ext",
            "Couleur int.": "couleur_int",
        }

        # trouve l’ancre "Spécifications"
        anchor = None
        for n in soup.find_all(["h2", "h3", "h4", "div", "span"]):
            t = norm_txt(n.get_text(" ", strip=True)).lower()
            if "spécification" in t or "specification" in t:
                anchor = n
                break
        if not anchor:
            return {}

        container = anchor.find_parent(["section", "div"]) or anchor.parent
        nodes = container.find_all(["div", "span", "p"], limit=400)
        texts = [norm_txt(x.get_text(" ", strip=True)) for x in nodes]
        texts = [t for t in texts if t]

        specs: Dict[str, str] = {}
        for i, t in enumerate(texts):
            if not t.endswith(":"):
                continue
            label = t[:-1].strip()
            key = wanted.get(label)
            if not key:
                continue

            val = ""
            for j in range(i + 1, min(i + 8, len(texts))):
                cand = texts[j].strip()
                if cand and not cand.endswith(":"):
                    val = cand
                    break
            if val:
                specs[key] = val

        return specs

    # --------------------
    # title
    # --------------------
    h1 = soup.find("h1")
    title = (h1.get_text(" ", strip=True) if h1 else "").strip() or "Sans titre"

    # headline line under title
    headline_features = extract_headline_line()

    # --------------------
    # stock / vin
    # --------------------
    stock = ""
    vin = ""

    m = re.search(r"stockNumber\s*[:=]\s*['\"]([A-Za-z0-9]+)['\"]", html, re.IGNORECASE)
    if m:
        stock = m.group(1).strip().upper()

    # Kennebec affiche parfois VIN # ... ; regex plus permissive
    m = re.search(r"\bvin\s*#?\s*[:=]?\s*['\"]?([A-HJ-NPR-Z0-9]{17})['\"]?", html, re.IGNORECASE)
    if m:
        vin = m.group(1).strip().upper()

    # fallback vin dans page visible (VIN # XXXXX)
    if not vin:
        m = re.search(r"\bVIN\s*#\s*([A-HJ-NPR-Z0-9]{17})\b", html, re.IGNORECASE)
        if m:
            vin = m.group(1).strip().upper()

    # --------------------
    # price / mileage
    # --------------------
    price = ""
    mileage = ""

    mp = re.search(r"displayedPrice\s*[:=]\s*['\"]([0-9]+(?:\.[0-9]+)?)['\"]", html, re.IGNORECASE)
    if mp:
        try:
            n = int(float(mp.group(1)))
            price = f"{n:,}".replace(",", " ") + " $"
        except Exception:
            pass

    mk = re.search(r"\bmileage\s*[:=]\s*['\"]([0-9]+(?:\.[0-9]+)?)['\"]", html, re.IGNORECASE)
    if mk:
        try:
            n = int(float(mk.group(1)))
            mileage = f"{n:,}".replace(",", " ") + " km"
        except Exception:
            pass

    # fallback visible price/km (au cas où)
    if not mileage:
        m = re.search(r"(\d[\d\s]{2,})\s*KM\b", html, re.IGNORECASE)
        if m:
            mileage = re.sub(r"\s+", " ", m.group(1)).strip() + " km"
    if not price:
        m = re.search(r"(\d[\d\s]{2,})\s*\$\b", html, re.IGNORECASE)
        if m:
            price = re.sub(r"\s+", " ", m.group(1)).strip() + " $"

    # --------------------
    # photos sm360
    # --------------------
    photos: List[str] = []
    for img in soup.select("img"):
        src = img.get("data-src") or img.get("src")
        if not src:
            continue
        src = src if src.startswith("http") else urljoin(url, src)
        low = src.lower()
        if "img.sm360.ca" in low and "/images/inventory/" in low and "/ir/w75h23/" not in low:
            photos.append(src)

    photos = uniq_keep_order(photos)

    # --------------------
    # features / comfort / specs
    # --------------------
    # HTML headings-based extraction (simple, stable)
    comfort = extract_list_near_heading(["Confort"])
    features = extract_list_near_heading(
        ["Équipements", "Equipements", "Caractéristiques", "Caracteristiques", "Options"]
    )

    features = uniq_keep_order(features)
    comfort = uniq_keep_order(comfort)

    # specs dict (Spécifications section)
    specs = extract_specs_dict()
    if not isinstance(specs, dict):
        specs = {}

    return {
        "url": url,
        "title": title,
        "headline_features": headline_features,
        "stock": stock,
        "vin": vin,
        "price": price,
        "mileage": mileage,
        "price_int": _clean_price_int(price) if price else None,
        "km_int": _clean_km_int(mileage) if mileage else None,
        "photos": photos,
        "features": features,
        "comfort": comfort,
        "specs": specs,
    }
```

---

## FILE: sticker_to_ad.py
```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
sticker_to_ad.py
- Extrait les OPTIONS (Window Sticker PDF) pour enrichir une annonce Facebook
- Sources:
  - Prix/KM/Titre: viennent du site Kennebec (passés via args --price/--mileage/--title)
  - Sticker: options + VIN (fallback) + titre (fallback si pas fourni)
- Parsing:
  - PDFMiner spans (layout) -> groupage PRIX à droite + détails indentés
  - Fallback texte brut (pdfminer extract_text)
  - Dernier recours OCR (poppler + tesseract)
- Ne pas afficher les prix des options (on s'en sert pour parser seulement)
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

# ---------- PDF text extraction (pdfminer) ----------
from pdfminer.high_level import extract_pages
from pdfminer.high_level import extract_text as pdfminer_extract_text
from pdfminer.layout import LTTextContainer, LTChar, LTAnno

# ---------- Optional: decrypt PDFs ----------
try:
    import pikepdf  # type: ignore
except Exception:
    pikepdf = None

# ---------- OCR fallback ----------
try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
except Exception:
    pytesseract = None
    Image = None


# ------------------------------
# Data structures
# ------------------------------

@dataclass
class Span:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    bold_ratio: float  # 0..1


# ------------------------------
# Helpers
# ------------------------------

def normalize(s: str) -> str:
    s = (s or "").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_price_token(s: str) -> bool:
    s = normalize(s)
    # accepte $ collé, après, etc.
    return bool(re.search(r"(\$\s*)?\b\d[\d\s.,]*\b\s*\$?", s))


def extract_price(s: str) -> Optional[str]:
    s = normalize(s)
    # capture 595, 2,395, 2 395, 2,395.00 etc.
    m = re.search(r"(?i)(?:\$\s*)?(\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{2})?)\s*\$?", s)
    if not m:
        return None
    raw = normalize(m.group(1)).replace(" ", "")
    return f"{raw} $" if raw else None


def looks_like_junk(s: str) -> bool:
    if not s:
        return True

    low = s.lower()
    low = (low
       .replace("’", "'")
       .replace("−", "-")
       .replace("–", "-")
       .replace("\u00a0", " ")
)

    banned = (
        "année modèle",
        "annee modele",
        "prix de base",
        "prix total",
        "p.d.s.f",
        "pdsf",
        "préparation",
        "preparation",
        "frais d'expédition",
        "frais d expedition",
        "destination",
        "destination charge",
        "freight",
        "shipping",
        "energuide",
        "consommation",
        "annual fuel cost",
        "coût annuel",
        "cout annuel",
        "garantie",
        "assistance routière",
        "assistance routiere",
        "transférable",
        "transferable",
        "motopropulseur",
        "fca canada",
        "ce véhicule est fabriqué",
        "ce vehicule est fabrique",
        "vehicles.nrcan",
        "vehicules.nrcan",
        "indice",
        "smog",
        "carbon",
        "tailpipe",
        "government of canada",
        "visitez le site web",
        "contactez",
        "pour de plus amples renseignements",
        "manufacturer's suggested retail price",
        "suggested retail price",
        "msrp",
        "tariff adjustment",
        "total price",
        "base price",
        "destination charge",
        "freight charge",
        "destination charge",
        "tariff adjustment",
        "federal a/c excise tax",
        "frais d’expédition",
        "taxe d’accise",
        "taxe d'accise",
        "federal a c excise tax",  # OCR parfois enlève le slash)
    )
    if any(b in low for b in banned):
        return True

    if "http" in low or "www." in low:
        return True

    # trop long = souvent paragraphe
    if len(s) > 90:
        return True

    return False


def detect_hybrid_from_text(txt: str) -> bool:
    t = (txt or "").lower()
    return any(k in t for k in (
        "phev",
        "plug-in",
        "plug in",
        "plug-in hybrid",
        "hybrid",
        "hybride",
        "vehicule hybride",
        "véhicule hybride",
        "vehicule hybride rechargeable",
        "véhicule hybride rechargeable",
        "vhr",
        "plug–in hybrid vehicle",
        "plug-in hybrid vehicle",
    ))


def is_hard_stop_detail(t: str) -> bool:
    """
    Stop net quand on arrive dans le bas du sticker (dealer/shipped/sold).
    FR + EN.
    """
    low = (t or "").lower().strip()

    stop_phrases = (
        # FR
        "le concessionnaire",
        "peut vendre moins cher",
        "expedier a", "expédier à",
        "expedie a", "expédié à",
        "vendu a", "vendu à",
        "par le concessionnaire",
        # EN
        "the dealer",
        "may sell for less",
        "shipped to",
        "sold to",
        "by dealer",
    )

    if low == "s.l.":
        return True

    return any(k in low for k in stop_phrases)


def extract_vin_from_text(txt: str) -> str:
    """
    Cherche un VIN même s'il est écrit avec des séparateurs (ex: 1C6—RR7LG5NS—241151).
    Retourne 17 caractères alphanum (sans I/O/Q).
    """
    if not txt:
        return ""

    t = (txt or "").upper()

    m = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", t)
    if m:
        return m.group(1)

    m2 = re.search(
        r"\b([A-HJ-NPR-Z0-9]{3,6})\s*[-–—]\s*([A-HJ-NPR-Z0-9]{4,8})\s*[-–—]\s*([A-HJ-NPR-Z0-9]{3,8})\b",
        t,
    )
    if m2:
        cand = (m2.group(1) + m2.group(2) + m2.group(3))
        cand = re.sub(r"[^A-Z0-9]", "", cand)
        if len(cand) == 17 and not re.search(r"[IOQ]", cand):
            return cand

    blob = re.sub(r"[^A-Z0-9\-–—\s]", " ", t)
    blob = re.sub(r"\s+", " ", blob).strip()
    compact = re.sub(r"[\s\-–—]", "", blob)

    for i in range(0, max(0, len(compact) - 16)):
        win = compact[i: i + 17]
        if re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", win) and not re.search(r"[IOQ]", win):
            return win

    return ""


def clean_option_line(s: str) -> str:
    s = normalize(s)
    s = re.sub(r"\bwww\.[^\s]+", "", s, flags=re.I).strip()
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def choose_hashtags(title: str) -> str:
    t = (title or "").lower()

    # Toujours présents
    BASE_TAGS = [
        "#Beauce", "#SaintGeorges", "#Quebec",
        "#AutoUsagée", "#VehiculeOccasion",
        "#DanielGiroux"
    ]

    # Marque -> intention
    BRAND_TAGS = {
        "ram": ["#RAM", "#Truck", "#Pickup"],
        "jeep": ["#Jeep", "#4x4", "#SUV"],
        "dodge": ["#Dodge", "#Performance"],
        "chrysler": ["#Chrysler", "#Familiale"],
        "alfa": ["#AlfaRomeo", "#Performance"],
    }

    # Modèle -> précision marketing
    MODEL_TAGS = {
        # Dodge
        "hornet": ["#Hornet", "#SUV", "#Performance"],
        "challenger": ["#Challenger", "#MuscleCar"],
        "charger": ["#Charger", "#MuscleCar"],
        "durango": ["#Durango", "#SUV"],

        # RAM
        "promaster": ["#ProMaster", "#Cargo", "#Van"],
        "1500": ["#RAM1500", "#Pickup"],
        "2500": ["#RAM2500", "#HeavyDuty"],

        # Jeep
        "wagoneer": ["#Wagoneer", "#SUV", "#4x4"],
        "wrangler": ["#Wrangler", "#OffRoad", "#4x4"],
        "grand cherokee": ["#GrandCherokee", "#LuxurySUV", "#4x4"],
        "gladiator": ["#Gladiator", "#Pickup4x4"],
    }

    # Variantes / mots-clés
    VARIANT_TAGS = {
        "r/t": ["#RT"],
        " rt ": ["#RT"],  # aide quand "RT" est séparé
        "plus": ["#Plus"],
        "hybrid": ["#Hybride"],
        "plug-in": ["#HybrideRechargeable"],
        "phev": ["#HybrideRechargeable"],
        "awd": ["#AWD"],
        "4x4": ["#4x4"],
        "4wd": ["#4x4"],
        "v8": ["#V8"],
    }

    tags = []

    # 1) Marque (première qui match)
    for brand, btags in BRAND_TAGS.items():
        if brand in t:
            tags.extend(btags)
            break

    # 2) Modèle (peut en matcher plusieurs)
    for model, mtags in MODEL_TAGS.items():
        if model in t:
            tags.extend(mtags)

    # 3) Variantes
    for key, vtags in VARIANT_TAGS.items():
        if key in t:
            tags.extend(vtags)

    # 4) Base
    tags.extend(BASE_TAGS)

    # 5) Dédoublonnage + limite
    out, seen = [], set()
    for x in tags:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            out.append(x)

    return " ".join(out[:18])


# ------------------------------
# PDF decrypt (optional)
# ------------------------------

def maybe_decrypt_pdf(in_pdf: Path) -> Path:
    if not pikepdf:
        return in_pdf
    try:
        with pikepdf.open(str(in_pdf), allow_overwriting_input=False) as pdf:
            out = Path(tempfile.gettempdir()) / (in_pdf.stem + "_unlocked.pdf")
            pdf.save(str(out))
            return out
    except Exception:
        return in_pdf


# ------------------------------
# PDF miner spans extraction
# ------------------------------

def extract_spans_pdfminer(pdf_path: Path, max_pages: int = 2) -> List[Span]:
    spans: List[Span] = []
    pages = 0

    def iter_objs(obj):
        if isinstance(obj, (LTChar, LTAnno)):
            yield obj
            return
        try:
            for x in obj:
                yield x
        except TypeError:
            yield obj

    for page_layout in extract_pages(str(pdf_path)):
        pages += 1

        for element in page_layout:
            if not isinstance(element, LTTextContainer):
                continue

            for text_line in element:
                chars: List[LTChar] = []
                txt_parts: List[str] = []
                x0 = y0 = float("inf")
                x1 = y1 = float("-inf")

                for obj in iter_objs(text_line):
                    if isinstance(obj, LTChar):
                        chars.append(obj)
                        txt_parts.append(obj.get_text())
                        x0 = min(x0, obj.x0)
                        y0 = min(y0, obj.y0)
                        x1 = max(x1, obj.x1)
                        y1 = max(y1, obj.y1)
                    elif isinstance(obj, LTAnno):
                        txt_parts.append(obj.get_text())

                text = normalize("".join(txt_parts))
                if not text:
                    continue

                bold = 0
                for c in chars:
                    fname = (getattr(c, "fontname", "") or "").lower()
                    if any(k in fname for k in ("bold", "black", "demi", "heavy", "semibold")):
                        bold += 1
                bold_ratio = (bold / len(chars)) if chars else 0.0

                spans.append(
                    Span(
                        text=text,
                        x0=x0 if x0 != float("inf") else 0.0,
                        y0=y0 if y0 != float("inf") else 0.0,
                        x1=x1 if x1 != float("-inf") else 0.0,
                        y1=y1 if y1 != float("-inf") else 0.0,
                        bold_ratio=bold_ratio,
                    )
                )

        if pages >= max_pages:
            break

    return spans


# ------------------------------
# Big title extraction (best effort)
# ------------------------------

def extract_big_title(spans: List[Span]) -> Optional[str]:
    """
    Titre = plus gros texte (hauteur bbox) en haut du sticker.
    Regroupe d'abord les spans par ligne (Y proche), puis prend la ligne
    la plus "grosse" (y1-y0) dans le haut de page, en filtrant MSRP/prix/etc.
    """
    if not spans:
        return None

    Y_LINE_TOL = 3.0
    sps = sorted(spans, key=lambda sp: (-sp.y0, sp.x0))

    lines: List[Dict[str, Any]] = []
    for sp in sps:
        txt = normalize(sp.text)
        if not txt:
            continue

        placed = False
        for ln in lines:
            if abs(ln["y0"] - sp.y0) <= Y_LINE_TOL:
                ln["parts"].append(sp)
                ln["y0"] = max(ln["y0"], sp.y0)
                ln["y1"] = max(ln["y1"], sp.y1)
                ln["x0"] = min(ln["x0"], sp.x0)
                ln["x1"] = max(ln["x1"], sp.x1)
                placed = True
                break

        if not placed:
            lines.append({"parts": [sp], "x0": sp.x0, "x1": sp.x1, "y0": sp.y0, "y1": sp.y1})

    def line_text(ln) -> str:
        parts = sorted(ln["parts"], key=lambda sp: sp.x0)
        return normalize(" ".join(p.text for p in parts))

    def line_bold_ratio(ln) -> float:
        parts = ln["parts"]
        if not parts:
            return 0.0
        return sum(p.bold_ratio for p in parts) / len(parts)

    max_y = max(sp.y1 for sp in spans)
    top_cut = max_y * 0.70

    BAD = (
        "année modèle", "annee modele",
        "manufacturer's suggested retail price", "suggested retail price", "msrp",
        "p.d.s.f", "pdsf",
        "prix de base", "prix total",
        "destination", "destination charge",
        "frais d'expédition", "frais d expedition",
    )

    cands: List[Tuple[float, str]] = []
    for ln in lines:
        if ln["y1"] < top_cut:
            continue

        txt = line_text(ln)
        if not txt:
            continue
        low = txt.lower()
        if any(b in low for b in BAD):
            continue
        if not (8 <= len(txt) <= 90):
            continue

        br = line_bold_ratio(ln)
        h = ln["y1"] - ln["y0"]
        score = (h * 100.0) + (br * 10.0) + min(len(txt), 70) * 0.1
        cands.append((score, txt))

    if not cands:
        return None

    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


# ------------------------------
# OCR fallback (optional)
# ------------------------------

def ocr_extract_text(pdf_path: Path) -> str:
    if not pytesseract or not Image:
        return ""

    import subprocess

    tmpdir = Path(tempfile.mkdtemp(prefix="sticker_ocr_"))
    outprefix = tmpdir / "page"
    cmd = ["pdftoppm", "-f", "1", "-l", "2", "-png", str(pdf_path), str(outprefix)]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return ""

    # concat simple des pages dispo
    texts = []
    for img in (tmpdir / "page-1.png", tmpdir / "page-2.png"):
        if not img.exists():
            continue
        try:
            im = Image.open(img)
            texts.append(pytesseract.image_to_string(im, lang="fra+eng") or "")
        except Exception:
            pass
    return "\n".join(texts).strip()


def extract_option_groups_from_ocr(text: str) -> List[Dict[str, Any]]:
    """
    OCR fallback: construit des groupes.
    Titres = lignes qui contiennent un prix (utilisé comme ancre).
    Détails = lignes suivantes sans prix (souvent indentées).
    """
    lines_raw = (text or "").splitlines()

    def indent_level(s: str) -> int:
        return len(s) - len(s.lstrip(" "))

    lines = [(normalize(x), indent_level(x)) for x in lines_raw]
    lines = [(t, ind) for (t, ind) in lines if t]

    price_re = re.compile(r"(?i)(?:\$\s*)?(\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{2})?)\s*\$?")

    # ✅ titres qu'on ne veut JAMAIS voir comme options
    banned_titles = (
        "destination charge",
        "freight",
        "freight charge",
        "shipping",
        "tariff adjustment",
        "msrp",
        "manufacturer's suggested retail price",
        "suggested retail price",
        "p.d.s.f", "pdsf",
        "prix total",
        "total price",
        "prix de base",
        "base price",
        "federal a/c excise tax",
        "federal a c excise tax",  # OCR enlève souvent le slash
    )

    groups: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for (ln, ind) in lines:
        if is_hard_stop_detail(ln):
            break

        m = price_re.search(ln)
        if m:
            p = extract_price(ln)

            title = price_re.sub("", ln).strip(" -–:•\t")
            title = clean_option_line(title)

            # ❌ skip titres vides / junk / prix-only / banned
            if not title:
                continue
            if looks_like_junk(title):
                continue
            # prix-only (ex: "$2,395")
            if extract_price(title) and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", title)) < 2:
                continue
            lowt = title.lower()
            if any(b in lowt for b in banned_titles):
                continue

            if current:
                groups.append(current)
            current = {"title": title, "price": p, "details": []}
            continue

        # détails
        if current:
            d = clean_option_line(ln)
            if not d:
                continue
            if looks_like_junk(d):
                continue
            # skip prix-only en détail
            if extract_price(d) and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", d)) < 2:
                continue
            # si pas indenté et trop long, on skip (souvent du texte de bas de page)
            if ind < 2 and len(d) > 80:
                continue
            if d.lower() != current["title"].lower():
                current["details"].append(d)

    if current:
        groups.append(current)

    # dédoublonne titres
    final, seen = [], set()
    for g in groups:
        k = (g.get("title") or "").lower().strip()
        if k and k not in seen:
            seen.add(k)
            final.append(g)

    return final[:12]


# ------------------------------
# Brand filter
# ------------------------------

def is_allowed_stellantis_brand(txt: str) -> bool:
    low = (txt or "").lower()
    allowed = ("ram", "dodge", "jeep", "chrysler", "alfa", "alfaromeo", "alfa romeo")
    return any(a in low for a in allowed)


# ------------------------------
# Ad builder (NEVER show option prices)
# ------------------------------

def build_ad(
    title: str,
    price: str,
    mileage: str,
    stock: str,
    vin: str,
    options: List[Dict[str, Any]],
    is_hybrid: bool = False,
    dealer: str = "Kennebec Dodge Chrysler — Saint-Georges (Beauce)",
    year: str = "",
    transmission: str = "",
    drivetrain: str = "",
) -> str:

    lines: List[str] = []

    title = (title or "").strip()

    # --- Titre ---
    lines.append(f"🔥 {title} 🔥")
    lines.append("")

    # --- Infos clés (site Kennebec) ---
    if price:
        lines.append(f"💥 {price} 💥")
    if mileage:
        lines.append(f"📊 Kilométrage : {mileage}")

    # 📍 Concession
    if dealer:
        lines.append(f"📍 {dealer}")

    lines.append("")

    # ✅ HYBRIDE / PHEV (détecté depuis le sticker)
    if is_hybrid:
        lines.append("⚡ Véhicule hybride rechargeable (PHEV)")
        lines.append("")

    # 🚗 DÉTAILS (Kennebec)
    details: List[str] = []
    if stock:
        details.append(f"✅ Inventaire : {stock}")
    if year:
        details.append(f"✅ Année : {year}")
    if vin:
        details.append(f"✅ VIN : {vin}")
    if transmission:
        details.append(f"✅ Transmission : {transmission}")
    if drivetrain:
        details.append(f"✅ Entraînement : {drivetrain}")

    if details:
        lines.append("🚗 DÉTAILS")
        lines.extend(details)
        lines.append("")

    # --- Accessoires ---
    if options:
        lines.append("✨ ACCESSOIRES OPTIONNELS (Window Sticker)")
        lines.append("")

        for g in options:
            t = (g.get("title") or "").strip()
            details2 = g.get("details") or []
            if not t:
                continue

            # ✅ on n'affiche JAMAIS le prix sticker
            lines.append(f"✅  {t}")

            for d in details2[:12]:
                dd = (d or "").strip()
                if not dd:
                    continue
                if looks_like_junk(dd):
                    continue
                # skip prix-only
                if extract_price(dd) and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", dd)) < 2:
                    continue
                lines.append(f"        ▫️ {dd}")

        lines.append("")
        lines.append("📌 Le reste des détails est dans le Window Sticker :")
        lines.append("")
        if vin:
            lines.append(f"https://www.chrysler.com/hostd/windowsticker/getWindowStickerPdf.do?vin={vin}")
        else:
            lines.append("(VIN introuvable — ajoute --vin pour générer le lien)")
        lines.append("")

    # NOTE: Footer retiré pour éviter les doublons.
    # Le footer sera ajouté par runner via footer_utils.add_footer_if_missing()

    return "\n".join(lines).strip() + "\n"


# ------------------------------
# Options extraction (groups from spans) — FR+EN anchors, price-driven grouping
# ------------------------------

def extract_option_groups_from_spans(spans: List[Span]) -> List[Dict[str, Any]]:
    if not spans:
        return []

    def is_junk_detail(t: str) -> bool:
        low = (t or "").lower().strip()
        if looks_like_junk(t):
            return True
        if re.fullmatch(r"[\d\s\-–—]+", t or ""):
            return True
        if any(k in low for k in ("expedier", "vendu", "concessionnaire", "dealer", "shipped", "sold")):
            return True
        return False

    # Anchor FR + EN
    ANCHORS = ("ACCESSOIRES OPTIONNELS", "OPTIONAL EQUIPMENT")
    anchors = [sp for sp in spans if any(a in (sp.text or "").upper() for a in ANCHORS)]
    if not anchors:
        return []

    anchor = max(anchors, key=lambda sp: sp.y0)
    anchor_y = anchor.y0

    RIGHT_TEXT_MIN_X = 250
    RIGHT_TEXT_MAX_X = 445
    PRICE_MIN_X = 445

    DETAIL_INDENT_X = 315

    right_text: List[Span] = []
    prices: List[Tuple[float, str]] = []

    for sp in spans:
        if sp.y0 > anchor_y:
            continue

        t = clean_option_line(sp.text)
        if not t:
            continue

        if RIGHT_TEXT_MIN_X <= sp.x0 <= RIGHT_TEXT_MAX_X:
            if not looks_like_junk(t):
                right_text.append(sp)

        if sp.x0 >= PRICE_MIN_X and is_price_token(sp.text):
            p = extract_price(sp.text)
            if p:
                prices.append((sp.y0, p))

    right_text.sort(key=lambda s: s.y0, reverse=True)

    def nearest_price(y: float, tol: float = 6.0) -> Optional[str]:
        best = None
        best_dy = 9999.0
        for py, p in prices:
            dy = abs(py - y)
            if dy < best_dy:
                best_dy = dy
                best = p
        return best if best is not None and best_dy <= tol else None

    groups: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for sp in right_text:
        text = clean_option_line(sp.text)
        if not text:
            continue

        # ✅ (2) skip lignes "prix seulement" (ex: "$2,395" ou "2,395 $")
        if extract_price(text) and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", text)) < 2:
            continue

        # ✅ (2) skip lignes junk (TOTAL PRICE, MSRP, etc.)
        if looks_like_junk(text):
            continue

        up = text.upper()
        if any(a in up for a in ANCHORS):
            continue

        if is_hard_stop_detail(text):
            break

        p = nearest_price(sp.y0)
        is_detail_by_indent = sp.x0 >= DETAIL_INDENT_X

        # PRIX aligné -> TITRE (même si pas bold)
        if p is not None:
            # ✅ (3) refuser un "titre" qui est juste un prix
            if extract_price(text) and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", text)) < 2:
                continue
            # ✅ (3) refuser titres junk
            if looks_like_junk(text):
                continue

            if current:
                groups.append(current)
            current = {"title": text, "price": p, "details": []}
            continue

        # sinon détail
        if current:
            if is_junk_detail(text):
                continue
            if (not is_detail_by_indent) and len(text) > 70:
                continue
            if text.lower() != (current.get("title") or "").lower():
                current["details"].append(text)

    if current:
        groups.append(current)

    cleaned: List[Dict[str, Any]] = []

    BAN_TITLES = (
     "destination charge",
     "tariff adjustment",
     "federal a/c excise tax",
     "federal a c excise tax",
     "federal a c excise tax",
 )

    for g in groups:
        opt_title = (g.get("title") or "").strip()
        if not opt_title:
            continue

        lowt = opt_title.lower()
        up = opt_title.upper()

        if "TAXE ACCISE" in up:
            continue
        if any(x in lowt for x in BAN_TITLES):
            continue
        if looks_like_junk(opt_title):
            continue

        cleaned.append(g)

    return cleaned[:12]


# ------------------------------
# Options extraction (text fallback) — FR+EN anchor
# ------------------------------

def extract_paid_options_from_text(txt: str) -> List[str]:
    """
    Fallback texte brut:
    - repère ACCESSOIRES OPTIONNELS / OPTIONAL EQUIPMENT
    - collecte labels (sans $) et prix (ligne prix)
    - associe (zip)
    """
    raw_lines = (txt or "").splitlines()
    lines = [re.sub(r"\s+", " ", l).strip() for l in raw_lines]

    money_re = re.compile(r"(?i)(?:\$\s*)?(\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{2})?)\s*\$?")
    price_only_re = re.compile(r"(?i)^\s*(?:\$\s*)?(\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{2})?)\s*\$?\s*$")

    def is_price_only(line: str) -> Optional[str]:
        m = price_only_re.match(line or "")
        if not m:
            return None
        raw = normalize(m.group(1)).replace(" ", "")
        return f"{raw} $" if raw else None

    def is_stop(line: str) -> bool:
        return is_hard_stop_detail(line)

    start_idx = None
    for i, l in enumerate(lines):
        u = (l or "").upper()
        if ("ACCESSOIRES OPTIONNELS" in u) or ("OPTIONAL EQUIPMENT" in u):
            start_idx = i
            break
    if start_idx is None:
        return []

    labels: List[str] = []
    prices: List[str] = []

    for j in range(start_idx + 1, len(lines)):
        l = (lines[j] or "").strip()
        if not l:
            continue
        if is_stop(l):
            break

        p = is_price_only(l)
        if p:
            prices.append(p)
            continue

        if money_re.search(l):
            continue

        cand = clean_option_line(l)
        if not cand or looks_like_junk(cand):
            continue
        labels.append(cand)

    keep_prefixes = (
        "ENSEMBLE", "ATTELAGE", "COMMANDE", "TAPIS", "ESSIEU", "PNEU", "PNEUS",
        "CROCHETS", "PLAQUE", "AJOUT", "TAXE", "SUPPORT", "SIEGE", "SIÈGE", "PRISE",
        "BANQUETTE", "BANQ", "DIFFERENTIEL", "DIFF", "GROUP", "PACKAGE", "MOPAR",
        "CLASS", "CARGO", "SAFETY", "PREMIUM", "CUSTOMER",
    )

    filtered_labels = []
    for lb in labels:
        up = lb.upper()
        if up.startswith(keep_prefixes):
            filtered_labels.append(lb)

    use_labels = filtered_labels if filtered_labels else labels

    n = min(len(use_labels), len(prices))
    out = [f"{use_labels[i]} ({prices[i]})" for i in range(n)]

    final, seen = [], set()
    for x in out:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            final.append(x)

    return final[:12]


# ------------------------------
# Main
# ------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="Chemin vers le window sticker PDF")
    ap.add_argument("--out", default="/tmp/output_stickers", help="Dossier de sortie OU chemin .txt")
    ap.add_argument("--title", default="", help="Titre affiché de l'annonce (idéalement du site Kennebec)")
    ap.add_argument("--price", default="", help="Prix (vient du site Kennebec)")
    ap.add_argument("--mileage", default="", help="Kilométrage (vient du site Kennebec)")
    ap.add_argument("--stock", default="", help="Numéro d'inventaire (ex: 06213)")
    ap.add_argument("--vin", default="", help="VIN (optionnel, sinon auto-extrait)")
    ap.add_argument("--url", default="", help="(Optionnel) URL fiche - ignorée volontairement")

    # ✅ NOUVEAUX CHAMPS (viennent de KenBot)
    ap.add_argument("--dealer", default="Kennebec Dodge Chrysler — Saint-Georges (Beauce)", help="Concession (Kennebec)")
    ap.add_argument("--year", default="", help="Année (vient de Kennebec)")
    ap.add_argument("--transmission", default="", help="Transmission (vient de Kennebec)")
    ap.add_argument("--drivetrain", default="", help="Entraînement (vient de Kennebec)")

    args = ap.parse_args()

    if not args.price.strip() or not args.mileage.strip():
        print("⛔ Prix/KM manquants: ils doivent venir du site Kennebec (passes --price et --mileage).", file=sys.stderr)
        # return 2


    pdf_path = Path(args.pdf).expanduser()
    if not pdf_path.exists():
        print(f"PDF introuvable: {pdf_path}", file=sys.stderr)
        return 2

    unlocked = maybe_decrypt_pdf(pdf_path)

    # spans (coords) -> 2 pages
    spans = extract_spans_pdfminer(unlocked, max_pages=2)

    # texte brut fallback -> 2 pages
    page_txt = pdfminer_extract_text(str(unlocked), maxpages=2) or ""
    is_hybrid = detect_hybrid_from_text(page_txt)

    # filtre marque (Stellantis)
    if page_txt.strip() and not is_allowed_stellantis_brand(page_txt):
        print("⛔ Sticker ignoré: marque hors RAM/Dodge/Jeep/Chrysler/Alfa Romeo.")
        return 0

    # VIN (auto si pas fourni)
    auto_vin = extract_vin_from_text(page_txt)
    vin = args.vin.strip() or auto_vin

    # Stock (sert aussi à fallback titre si besoin)
    auto_stock = pdf_path.parent.name or pdf_path.stem
    stock = re.sub(r"\s+", "", (args.stock.strip() or auto_stock).strip()) or pdf_path.stem

    # Titre: priorité au site, sinon "gros titre" pdf, sinon stock
    auto_title = extract_big_title(spans) or ""
    title = args.title.strip() or auto_title or stock or pdf_path.stem

    # options groups via spans
    groups = extract_option_groups_from_spans(spans)

    # fallback texte (si groups vide)
    if not groups and page_txt.strip():
        flat = extract_paid_options_from_text(page_txt)
        groups = [{"title": x, "price": None, "details": []} for x in flat]

    # fallback OCR (dernier recours)
    if not groups:
        ocr_txt = ocr_extract_text(unlocked)
        if ocr_txt:
            groups = extract_option_groups_from_ocr(ocr_txt)

    # Annonce
    ad = build_ad(
    title=title,
    price=args.price.strip(),
    mileage=args.mileage.strip(),
    stock=stock,
    vin=vin,
    options=groups,
    is_hybrid=is_hybrid,
    dealer=args.dealer.strip(),
    year=args.year.strip(),
    transmission=args.transmission.strip(),
    drivetrain=args.drivetrain.strip(),
)

    out_target = Path(args.out).expanduser()
    if out_target.suffix.lower() == ".txt":
        out_path = out_target
        out_dir = out_path.parent
    else:
        out_dir = out_target
        out_path = out_dir / f"{stock}_facebook.txt"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ad, encoding="utf-8")
    print(f"Écrit: {out_path}")

    if not groups:
        print("⚠️ Aucun accessoire optionnel détecté (parseur à ajuster pour ce format).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
