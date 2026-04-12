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
    publish_photos_as_comment_batch,
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
    vin = (vin or "").strip().upper()
    if len(vin) != 17:
        return {"status": "skip", "reason": "invalid_vin"}

    ok_path = f"pdf_ok/{vin}.pdf"
    bad_path = f"pdf_bad/{vin}.pdf"

    try:
        blob = sb.storage.from_(STICKERS_BUCKET).download(ok_path)
        if _is_pdf_ok(blob):
            return {"status": "ok", "path": ok_path, "source": "cache_ok"}
    except Exception:
        pass

    pdf_url = f"https://www.chrysler.com/hostd/windowsticker/getWindowStickerPdf.do?vin={vin}"

    # tentative simple requests
    try:
        r = SESSION.get(pdf_url, timeout=30)
        fetched = r.content or b""
        if _is_pdf_ok(fetched):
            upload_bytes_to_storage(sb, STICKERS_BUCKET, ok_path, fetched, "application/pdf", True)
            upsert_sticker_pdf(sb, vin=vin, status="ok", storage_path=ok_path, data=fetched, reason="", run_id=run_id)
            return {"status": "ok", "path": ok_path, "source": "requests"}
    except Exception as e:
        print(f"[PDF] requests failed vin={vin} err={e}", flush=True)

    # fallback playwright si dispo
    if sync_playwright is not None:
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
                        upload_bytes_to_storage(sb, STICKERS_BUCKET, ok_path, fetched, "application/pdf", True)
                        upsert_sticker_pdf(sb, vin=vin, status="ok", storage_path=ok_path, data=fetched, reason="", run_id=run_id)
                        return {"status": "ok", "path": ok_path, "source": f"playwright_attempt_{attempt}"}
            except Exception as e:
                print(f"[PDF] Playwright attempt {attempt} failed vin={vin}: {e}", flush=True)
                time.sleep(random.uniform(2, 5))

    # cache bad pour éviter marteler Chrysler à chaque run
    try:
        upload_bytes_to_storage(sb, STICKERS_BUCKET, bad_path, b"invalid", "application/octet-stream", True)
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
    if USE_STICKER_AD and _is_stellantis_vin(vin):
        try:
            res = ensure_sticker_cached(sb, vin, run_id)
            if (res.get("status") or "").lower() == "ok":
                pdf_bytes = sb.storage.from_(STICKERS_BUCKET).download(res["path"])
                options = _extract_options_from_sticker_bytes(pdf_bytes)
                if options:
                    # Texte structuré pour llm_v3
                    opt_lines = []
                    for grp in options:
                        opt_lines.append(grp.get("title", ""))
                        for d in grp.get("details", []):
                            opt_lines.append(f"  - {d}")
                    sticker_options_text = "\n".join(opt_lines)

                    # Texte brut complet via build_ad_from_options (pour humanisation)
                    sticker_raw_text = build_ad_from_options(
                        title=title,
                        price=price,
                        mileage=mileage,
                        stock=stock,
                        vin=vin,
                        options=options,
                        vehicle_url=url,
                    )
        except Exception as e:
            print(f"[STICKER FETCH] slug={slug} vin={vin} err={e}", flush=True)

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
    # FIX #3: PHOTOS_ADDED - Détection améliorée multi-méthodes
    # =========================================================
    photos_added: List[str] = []
    if REFRESH_NO_PHOTO_DAILY:
        for slug in (set(current) & set(posts_db)):
            post_data = posts_db.get(slug) or {}
            v = current.get(slug) or {}

            # Photos actuellement disponibles sur le site Kennebec
            current_photos = v.get("photos") or []

            # Méthode 1: Vérifier le champ no_photo (set par FIX #1)
            has_no_photo_flag = post_data.get("no_photo", None)

            # Méthode 2: Vérifier photo_count == 0
            photo_count_db = post_data.get("photo_count", None)

            # Méthode 3: Vérifier si le base_text contient des indices de "no photo"
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

            # Méthode 4 (NEW): Vérifier photo_count == 1 avec no_photo == True
            # Ceci attrape les posts créés avec le fallback NO_PHOTO corrigé par FIX #1
            is_no_photo_post = False

            if has_no_photo_flag is True:
                is_no_photo_post = True
            elif photo_count_db == 0:
                is_no_photo_post = True
            elif text_has_no_photo_hint:
                is_no_photo_post = True
            elif photo_count_db is None and has_no_photo_flag is None:
                # Anciennes entrées sans ces champs - on vérifie le texte
                # ET on vérifie aussi si le post n'a qu'une seule photo (potentiel fallback)
                if text_has_no_photo_hint:
                    is_no_photo_post = True

            # Si le post est identifié comme "no photo" ET qu'il y a maintenant des photos disponibles
            if is_no_photo_post and len(current_photos) > 0:
                photos_added.append(slug)
                print(
                    f"[PHOTOS_ADDED DETECT] slug={slug} "
                    f"no_photo_flag={has_no_photo_flag} photo_count={photo_count_db} "
                    f"text_hint={text_has_no_photo_hint} current_photos={len(current_photos)}",
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
        # FIX #2: PHOTOS_ADDED - Corriger l'ordre des arguments
        # =========================================================
        if event == "PHOTOS_ADDED":
            old_post = posts_db.get(slug) or {}
            old_post_id = (old_post.get("post_id") or "").strip()

            if not old_post_id:
                print(f"[PHOTOS_ADDED] no post_id for slug={slug}, skip", flush=True)
                log_event(sb, slug, "PHOTOS_ADDED_SKIP_NO_POST", {"run_id": run_id})
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

                # 2. TOUJOURS régénérer le texte pour PHOTOS_ADDED
                #    (l'ancien texte est probablement "Photos suivront" ou sans AI)
                base_text = _build_ad_text(sb, run_id, slug, v, "NEW")

                # 3. Créer le nouveau post avec les vraies photos
                media_ids = publish_photos_unpublished(
                    FB_PAGE_ID,
                    FB_TOKEN,
                    photos[:POST_PHOTOS],
                    limit=POST_PHOTOS,
                )
                new_post_id = create_post_with_attached_media(FB_PAGE_ID, FB_TOKEN, base_text, media_ids)

                # 4. Ajouter les photos supplémentaires en commentaires si nécessaire
                extra = photos[POST_PHOTOS:]
                if extra:
                    try:
                        publish_photos_as_comment_batch(FB_PAGE_ID, FB_TOKEN, new_post_id, extra)
                    except Exception as e:
                        print(f"[PHOTOS_ADDED] Extra photos comment fail: {e}", flush=True)

                # 5. Mettre à jour la DB avec le nouveau post_id
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

            extra = photos[POST_PHOTOS:]
            if extra:
                try:
                    publish_photos_as_comment_batch(FB_PAGE_ID, FB_TOKEN, post_id, extra)
                except Exception as e:
                    print(f"[EXTRA PHOTOS COMMENT FAIL] slug={slug} post_id={post_id} err={e}", flush=True)

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
