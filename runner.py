# Fichier legacy / non utilisé en production
# Le runner actif est runner_cron_prod.py
import os
import re
import json
import time
import random
import hashlib
import csv
import io
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv

from kennebec_scrape import (
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
)

from supabase_db import (
    get_client,
    get_inventory_map,
    get_posts_map,
    upsert_inventory,
    upsert_post,
    log_event,
    utc_now_iso,
    read_json_from_storage,
    get_latest_snapshot_run_id,
    upload_json_to_storage,
    upload_bytes_to_storage,
    cleanup_storage_runs,
    upsert_scrape_run,
    upsert_raw_page,
    upsert_sticker_pdf,
    upsert_output,
)

# Ajout : comparaison meta vs site intégrée
from meta_compare_supabase import main as meta_compare

# -------------------------
# Env load (local dev only)
# -------------------------
for name in (".env.local", ".kenbot_env", ".env"):
    p = Path(name)
    if p.exists():
        load_dotenv(p, override=False)
        break

# -------------------------
# Config
# -------------------------
BASE_URL = os.getenv("KENBOT_BASE_URL", "https://www.kennebecdodge.ca").rstrip("/")
INVENTORY_PATH = os.getenv("KENBOT_INVENTORY_PATH", "/fr/inventaire-occasion/")
TEXT_ENGINE_URL = (os.getenv("KENBOT_TEXT_ENGINE_URL") or "").strip()
FB_PAGE_ID = (os.getenv("KENBOT_FB_PAGE_ID") or os.getenv("FB_PAGE_ID") or "").strip()
FB_TOKEN = (os.getenv("KENBOT_FB_ACCESS_TOKEN") or os.getenv("FB_PAGE_ACCESS_TOKEN") or "").strip()
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").strip()
SUPABASE_KEY = (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

RAW_BUCKET = os.getenv("SB_BUCKET_RAW", "kennebec-raw").strip()
STICKERS_BUCKET = os.getenv("SB_BUCKET_STICKERS", "kennebec-stickers").strip()
SNAP_BUCKET = os.getenv("SB_BUCKET_SNAPSHOTS", "kennebec-facebook-snapshots").strip()
OUTPUTS_BUCKET = os.getenv("SB_BUCKET_OUTPUTS", "kennebec-outputs").strip()

DRY_RUN = os.getenv("KENBOT_DRY_RUN", "0").strip() == "1"
REBUILD_POSTS = os.getenv("KENBOT_REBUILD_POSTS", "0").strip() == "1"
FORCE_STOCK = (os.getenv("KENBOT_FORCE_STOCK") or "").strip().upper()
MAX_TARGETS = int(os.getenv("KENBOT_MAX_TARGETS", "4").strip() or "4")
SLEEP_BETWEEN = int(os.getenv("KENBOT_SLEEP_BETWEEN_POSTS", "30").strip() or "30")
CACHE_STICKERS = os.getenv("KENBOT_CACHE_STICKERS", "1").strip() == "1"
STICKER_MAX = int(os.getenv("KENBOT_STICKER_MAX", "999").strip() or "999")
RAW_KEEP = int(os.getenv("KENBOT_RAW_KEEP", "2").strip() or "2")
SNAP_KEEP = int(os.getenv("KENBOT_SNAP_KEEP", "10").strip() or "10")
MAX_PHOTOS = int(os.getenv("KENBOT_MAX_PHOTOS", "15").strip() or "15")
POST_PHOTOS = int(os.getenv("KENBOT_POST_PHOTOS", "10").strip() or "10")
TMP_PHOTOS = Path(os.getenv("KENBOT_TMP_PHOTOS_DIR", "/tmp/kenbot_photos"))
TMP_PHOTOS.mkdir(parents=True, exist_ok=True)

# Seuil pour ignorer petits changements de prix (taxes, arrondi)
PRICE_CHANGE_THRESHOLD = int(os.getenv("KENBOT_PRICE_CHANGE_THRESHOLD", "200"))

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("🛑 Supabase creds manquants: SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY")

if not FB_PAGE_ID or not FB_TOKEN:
    raise SystemExit("🛑 FB creds manquants: KENBOT_FB_PAGE_ID + KENBOT_FB_ACCESS_TOKEN")

if not TEXT_ENGINE_URL:
    raise SystemExit("🛑 KENBOT_TEXT_ENGINE_URL manquant (kenbot-text-engine)")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Safari/605.1.15",
    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
})

# -------------------------
# Helpers
# -------------------------
def _sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b or b"").hexdigest()

def _run_id_from_now(now_iso: str) -> str:
    digits = "".join(ch for ch in (now_iso or "") if ch.isdigit())
    if len(digits) >= 14:
        return f"{digits[0:8]}_{digits[8:14]}"
    return f"run_{int(time.time())}"

def _is_pdf_ok(b: bytes) -> bool:
    if not b:
        return False
    bb = b.lstrip()
    if not bb.startswith(b"%PDF"):
        return False
    if len(bb) < 2048:
        return False
    if b"%%EOF" not in bb[-2048:]:
        return False
    return True

def _is_stellantis_vin(vin: str) -> bool:
    vin = (vin or "").strip().upper()
    if len(vin) != 17:
        return False
    return vin.startswith(("1C", "2C", "3C", "ZAC", "ZFA"))

def _clean_title(t: str) -> str:
    t = (t or "").strip()
    low = t.lower()
    if low in {"jeep", "dodge", "ram", "chrysler", "fiat"}:
        return ""
    if len(t) < 6:
        return ""
    return t

def _clean_int(x) -> Optional[int]:
    if x is None:
        return None
    try:
        s = str(x).replace(" ", "").replace("\u00a0", "").replace(",", "").replace("$", "")
        return int(s)
    except Exception:
        return None

def _dealer_footer() -> str:
    return (
        "\n"
        "🔁 J’accepte les échanges : 🚗 auto • 🏍️ moto • 🛥️ bateau • 🛻 VTT • 🏁 côte-à-côte\n"
        "📸 Envoie-moi les photos + infos (année / km / paiement restant) → je te reviens vite.\n"
        "📍 Saint-Georges (Beauce) | Prise de possession rapide possible\n"
        "📄 Vente commerciale — 2 taxes applicables\n"
        "✅ Inspection complète — véhicule propre & prêt à partir.\n"
        "📩 Écris-moi en privé — réponse rapide\n"
        "📞 Daniel Giroux — 418-222-3939\n"
        "[[DG_FOOTER]]"
    )

FOOTER_MARKERS = [
    "j’accepte", "j'accepte",
    "échange", "echange",
    "financement", "finance",
    "daniel giroux",
    "418-222-3939", "418 222 3939",
    "écris-moi", "ecris-moi",
    "en privé", "en prive",
    "#danielgiroux",
]

def ensure_single_footer(text: str, footer: str) -> str:
    base = (text or "").rstrip()
    low = base.lower()
    if "[[dg_footer]]" in low:
        return base
    if any(m in low for m in FOOTER_MARKERS):
        return base
    return f"{base}\n\n{footer}".strip()

def _has_hashtags(txt: str) -> bool:
    t = (txt or "")
    return "#" in t

def smart_hashtags(make: str = "", model: str = "", title: str = "", body: str = "") -> str:
    mk = (make or "").strip().lower()
    md = (model or "").strip().lower()
    t = f"{title} {body}".lower()
    tags = [
        "#KennebecDodge", "#StGeorges", "#Beauce",
        "#AutoUsagée", "#Occasion", "#VéhiculeDoccasion",
        "#FinancementAuto", "#TradeIn", "#LivraisonRapide",
    ]
    if any(x in t for x in ["4x4", "awd", "4wd", "quatre roues motrices"]):
        tags += ["#4x4", "#AWD", "#HiverQC"]
    if any(x in t for x in ["camion", "truck", "pickup", "boite", "remorquage", "towing"]):
        tags += ["#Camion", "#Pickup", "#TruckLife"]
    if any(x in t for x in ["vus", "suv", "cuv"]):
        tags += ["#SUV", "#VUS"]
    if any(x in t for x in ["hybride", "hybrid"]):
        tags += ["#Hybride", "#ÉconomieEssence"]
    if any(x in t for x in ["électrique", "electric", "ev"]):
        tags += ["#Électrique", "#EV"]
    brand_map = {
        "ram": ["#RAM", "#RamTruck"],
        "jeep": ["#Jeep", "#JeepLife"],
        "dodge": ["#Dodge"],
        "chrysler": ["#Chrysler"],
        "toyota": ["#Toyota"],
        "honda": ["#Honda"],
        "ford": ["#Ford"],
        "chevrolet": ["#Chevrolet"],
        "gmc": ["#GMC"],
        "mazda": ["#Mazda"],
        "subaru": ["#Subaru"],
        "hyundai": ["#Hyundai"],
        "kia": ["#Kia"],
        "nissan": ["#Nissan"],
        "bmw": ["#BMW"],
        "mercedes": ["#Mercedes"],
        "audi": ["#Audi"],
        "volkswagen": ["#Volkswagen"],
    }
    for key, extra in brand_map.items():
        if key in mk:
            tags += extra
            break
    full = f"{md} {t}"
    for k, extra in model_map.items():
        if k in full:
            tags += extra
    out, seen = [], set()
    for tag in tags:
        if tag not in seen:
            out.append(tag)
            seen.add(tag)
    return " ".join(out[:18])

def _strip_sold_banner(txt: str) -> str:
    t = (txt or "").lstrip()
    if not t.startswith("🚨 VENDU 🚨"):
        return t
    lines = t.splitlines()
    out = []
    cutting = True
    for line in lines:
        if cutting:
            if "────────────────────" in line:
                cutting = False
            continue
        out.append(line)
    return ("\n".join(out)).lstrip()

def _sold_prefix() -> str:
    return (
        "🚨 VENDU 🚨\n\n"
        "Ce véhicule n’est plus disponible.\n\n"
        "👉 Vous recherchez un véhicule semblable ?\n"
        "Contactez-moi directement, je peux vous aider.\n\n"
        "Daniel Giroux\n"
        "📞 418-222-3939\n"
        "────────────────────\n\n"
    )

def _make_sold_message(base_text: str) -> str:
    base = _strip_sold_banner(base_text).strip()
    if not base:
        base = "(Détails indisponibles — contactez-moi.)"
    return _sold_prefix() + base

def _fetch_fb_post_message(post_id: str) -> str:
    url = f"https://graph.facebook.com/v24.0/{post_id}"
    r = SESSION.get(url, params={"fields": "message", "access_token": FB_TOKEN}, timeout=30)
    j = r.json()
    if not r.ok:
        raise RuntimeError(f"FB get post message error: {j}")
    return (j.get("message") or "").strip()

def _download_photo(url: str, out_path: Path) -> None:
    r = SESSION.get(url, timeout=60)
    r.raise_for_status()
    out_path.write_bytes(r.content)

def _download_photos(stock: str, urls: List[str], limit: int) -> List[Path]:
    out: List[Path] = []
    stock = (stock or "UNKNOWN").strip().upper()
    folder = TMP_PHOTOS / stock
    folder.mkdir(parents=True, exist_ok=True)
    for i, u in enumerate(urls[:limit], start=1):
        ext = ".jpg"
        low = (u or "").lower()
        if ".png" in low:
            ext = ".png"
        elif ".webp" in low:
            ext = ".webp"
        p = folder / f"{stock}_{i:02d}{ext}"
        if not p.exists():
            try:
                _download_photo(u, p)
            except Exception:
                continue
        out.append(p)
    return out

def rebuild_posts_map(limit: int = 300) -> Dict[str, Dict[str, Any]]:
    posts_map: Dict[str, Dict[str, Any]] = {}
    fetched = 0
    after = None
    while fetched < limit:
        params = {"fields": "id,message,created_time,permalink_url", "limit": 25, "access_token": FB_TOKEN}
        if after:
            params["after"] = after
        url = f"https://graph.facebook.com/v24.0/{FB_PAGE_ID}/posts"
        r = SESSION.get(url, params=params, timeout=60)
        j = r.json()
        if not r.ok:
            raise RuntimeError(f"FB posts fetch failed: {j}")
        data = j.get("data") or []
        if not data:
            break
        for item in data:
            fetched += 1
            msg = (item.get("message") or "").strip()
            post_id = item.get("id")
            created = item.get("created_time") or ""
            if not post_id or not msg:
                continue
            m = re.search(r"\b(\d{5}[A-Za-z]?)\b", msg)
            stock = (m.group(1).upper() if m else "")
            if not stock:
                continue
            posts_map[stock] = {"post_id": post_id, "published_at": created}
            if fetched >= limit:
                break
        paging = (j.get("paging") or {}).get("cursors") or {}
        after = paging.get("after")
        if not after:
            break
    return posts_map

# -------------------------
# Main
# -------------------------
def main() -> None:
    sb = get_client(SUPABASE_URL, SUPABASE_KEY)
    now = utc_now_iso()
    run_id = _run_id_from_now(now)
    inv_db = get_inventory_map(sb)
    posts_db = get_posts_map(sb)
    # -------------------------
    # 1️⃣ FETCH LISTING PAGES
    # -------------------------
    pages = [
        f"{BASE_URL}{INVENTORY_PATH}",
        f"{BASE_URL}{INVENTORY_PATH}?page=2",
        f"{BASE_URL}{INVENTORY_PATH}?page=3",
    ]
    all_urls: List[str] = []
    for page_url in pages:
        try:
            html = SESSION.get(page_url, timeout=30).text
            all_urls += parse_inventory_listing_urls(BASE_URL, INVENTORY_PATH, html)
        except Exception:
            continue
    all_urls = list(dict.fromkeys(all_urls))
    # -------------------------
    # 2️⃣ PARSE INVENTORY
    # -------------------------
    current: Dict[str, Dict[str, Any]] = {}
    for url in all_urls:
        try:
            d = parse_vehicle_detail_simple(SESSION, url)
        except Exception:
            continue
        stock = (d.get("stock") or "").strip().upper()
        title = _clean_title(d.get("title") or "")
        if not stock or not title:
            continue
        d["stock"] = stock
        d["title"] = title
        d["vin"] = (d.get("vin") or "").strip().upper()
        d["price_int"] = _clean_int(d.get("price_int"))
        d["km_int"] = _clean_int(d.get("km_int"))
        d["url"] = d.get("url") or url
        slug = slugify(title, stock)
        d["slug"] = slug
        current[slug] = d
    inv_count = len(current)
    upsert_scrape_run(
        sb,
        run_id,
        status="OK",
        note=f"inv_count={inv_count}"
    )
    # -------------------------
    # 3️⃣ UPSERT ACTIVE INVENTORY
    # -------------------------
    rows = []
    for slug, v in current.items():
        rows.append({
            "slug": slug,
            "stock": v.get("stock"),
            "url": v.get("url"),
            "title": v.get("title"),
            "vin": v.get("vin"),
            "price_int": v.get("price_int"),
            "km_int": v.get("km_int"),
            "status": "ACTIVE",
            "last_seen": now,
            "updated_at": now,
        })
    upsert_inventory(sb, rows)
    # -------------------------
    # 4️⃣ DETECT NEW + PRICE_CHANGED
    # -------------------------
    current_slugs = set(current.keys())
    inv_db_active = {
        slug: r for slug, r in inv_db.items()
        if (r.get("status") or "").upper() == "ACTIVE"
    }
    db_slugs = set(inv_db_active.keys())
    new_slugs = sorted(current_slugs - db_slugs)
    common_slugs = sorted(current_slugs & db_slugs)
    price_changed: List[str] = []
    for slug in common_slugs:
        old = inv_db.get(slug) or {}
        new = current.get(slug) or {}
        old_p = old.get("price_int")
        new_p = new.get("price_int")
        if old_p is not None and new_p is not None:
            diff = abs(old_p - new_p)
            if diff > PRICE_CHANGE_THRESHOLD:
                price_changed.append(slug)
                print(f"[PRICE CHANGE] {slug} : {old_p} → {new_p} (diff {diff}$)")
            elif diff > 0:
                print(f"[DEBUG] Petit changement ignoré {slug} : {old_p} → {new_p} (diff {diff}$)")
    targets: List[Tuple[str, str]] = (
        [(s, "PRICE_CHANGED") for s in price_changed]
        + [(s, "NEW") for s in new_slugs]
    )
    # -------------------------
    # 5️⃣ BUILD pdf_ok_vins
    # -------------------------
    pdf_ok_vins: set[str] = set()
    try:
        for o in (sb.storage.from_(STICKERS_BUCKET).list("pdf_ok") or []):
            name = o.get("name") or ""
            if name.lower().endswith(".pdf"):
                pdf_ok_vins.add(name[:-4].upper())
    except Exception:
        pass
    # -------------------------
    # 6️⃣ PROCESS TARGETS
    # -------------------------
    # Rebuild posts map pour anti-duplicate
    posts_map = rebuild_posts_map(limit=500)
    for slug, event in targets[:MAX_TARGETS]:
        v = current.get(slug) or {}
        stock = (v.get("stock") or "").strip().upper()
        vin = (v.get("vin") or "").strip().upper()
        title = v.get("title") or ""
        if not stock or not title:
            continue
        price_int = _clean_int(v.get("price_int"))
        km_int = _clean_int(v.get("km_int"))
        vehicle_payload = {
            "title": title,
            "price": (f"{price_int:,}".replace(",", " ") + " $") if price_int else "",
            "mileage": (f"{km_int:,}".replace(",", " ") + " km") if km_int else "",
            "stock": stock,
            "vin": vin,
            "url": v.get("url") or "",
        }
        # Anti-duplicate : skip si déjà posté aujourd'hui
        if stock in posts_map:
            last_post = posts_map[stock]
            last_time = last_post.get("published_at")
            print(f"[ANTI-DUPLICATE] Skip : post déjà fait pour stock={stock} à {last_time}")
            continue
        # -------------------------
        # GENERATE FACEBOOK TEXT
        # -------------------------
        fb_text = generate_facebook_text(
            TEXT_ENGINE_URL,
            slug=slug,
            event=event,
            vehicle=vehicle_payload,
        )
        fb_text = (fb_text or "").replace("[[DG_FOOTER]]", "").strip()
        # GARDE-FOU : skip si texte invalide
        if not fb_text or len(fb_text) < 300:
            print(f"[SKIP] Texte invalide pour {slug} (len={len(fb_text)}) → {fb_text[:100]}...")
            log_event(sb, slug, "SKIP_EMPTY_TEXT", {"text_len": len(fb_text), "run_id": run_id})
            continue
        fb_text = ensure_single_footer(fb_text, _dealer_footer())
        if not _has_hashtags(fb_text):
            fb_text = (
                fb_text.rstrip()
                + "\n\n"
                + smart_hashtags(
                    v.get("make", ""),
                    v.get("model", ""),
                    title=title,
                    body=fb_text,
                )
            ).strip()
        # SAVE OUTPUT
        out_folder = "with" if (vin and vin in pdf_ok_vins) else "without"
        fb_out_path = f"{out_folder}/{stock}_facebook.txt"
        upload_bytes_to_storage(
            sb,
            OUTPUTS_BUCKET,
            fb_out_path,
            (fb_text + "\n").encode("utf-8"),
            content_type="text/plain; charset=utf-8",
            upsert=True,
        )
        if DRY_RUN:
            print(f"DRY_RUN {event}: {stock}")
            continue
        post_info = posts_db.get(slug) or {}
        post_id = post_info.get("post_id")
        photo_paths = _download_photos(
            stock,
            v.get("photos") or [],
            limit=MAX_PHOTOS,
        )
        if not photo_paths:
            continue
        try:
            if not post_id:
                media_ids = publish_photos_unpublished(
                    FB_PAGE_ID,
                    FB_TOKEN,
                    photo_paths[:POST_PHOTOS],
                    limit=POST_PHOTOS,
                )
                post_id = create_post_with_attached_media(
                    FB_PAGE_ID,
                    FB_TOKEN,
                    fb_text,
                    media_ids,
                )
                upsert_post(sb, {
                    "slug": slug,
                    "post_id": post_id,
                    "status": "ACTIVE",
                    "published_at": now,
                    "last_updated_at": now,
                    "base_text": fb_text,
                    "stock": stock,
                })
            else:
                update_post_text(post_id, FB_TOKEN, fb_text)
        except Exception as e:
            print(f"[ERROR POST] {slug} {event}: {e}")
            continue
        if SLEEP_BETWEEN > 0:
            time.sleep(SLEEP_BETWEEN)
    print(
        f"OK run_id={run_id} inv_count={inv_count} "
        f"NEW={len(new_slugs)} PRICE_CHANGED={len(price_changed)}"
    )

    # Appel meta_compare pour aligner prix
    try:
        meta_compare()
        print("[META] Comparaison meta vs site exécutée")
    except Exception as e:
        print(f"[META ERROR] {e}")

if __name__ == "__main__":
    main()
