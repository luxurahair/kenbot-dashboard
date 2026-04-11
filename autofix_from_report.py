import os
import csv
import time
from typing import Dict, Any, List, Tuple, Optional

from supabase_db import (
    get_client,
    get_inventory_map,
    get_posts_map,
    upsert_post,
    log_event,
)

from fb_api import update_post_text
from text_engine_client import generate_facebook_text

# --- ENV ---
OUTPUTS_BUCKET = os.getenv("SB_BUCKET_OUTPUTS", "kennebec-outputs").strip()
REPORT_PATH = os.getenv("KENBOT_META_REPORT_PATH", "reports/meta_vs_site.csv").strip()

MAX_FIX = int(os.getenv("KENBOT_MAX_FIX", "6") or "6")
SLEEP = int(os.getenv("KENBOT_SLEEP_BETWEEN_POSTS", os.getenv("KENBOT_SLEEP_BETWEEN_POSTS", "60")) or "60")
FB_TOKEN = os.getenv("KENBOT_FB_ACCESS_TOKEN", "") or ""
TEXT_ENGINE_URL = os.getenv("KENBOT_TEXT_ENGINE_URL", "") or ""
DRY = os.getenv("KENBOT_DRY_RUN", "0").strip() == "1"
AUTOFIX = os.getenv("KENBOT_AUTOFIX", "0").strip() == "1"

def _pick(row: Dict[str, Any], keys: List[str]) -> str:
    for k in keys:
        if k in row and row[k] is not None:
            s = str(row[k]).strip()
            if s:
                return s
    return ""

def _to_int(s: str) -> Optional[int]:
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else None

def _download_report(sb) -> bytes:
    return sb.storage.from_(OUTPUTS_BUCKET).download(REPORT_PATH)

def _parse_csv(b: bytes) -> List[Dict[str, Any]]:
    txt = b.decode("utf-8", errors="replace")
    return list(csv.DictReader(txt.splitlines()))

def _is_missing_on_site(row: Dict[str, Any]) -> bool:
    status = _pick(row, ["status", "result", "state"]).upper()
    if status in {"MISSING_ON_SITE", "SOLD_ON_SITE", "NOT_ON_SITE", "MISSING"}:
        return True
    # fallback par champs bool/vides
    site_url = _pick(row, ["site_url", "kennebec_url", "url_site", "site_link"])
    if status and "MISSING" in status:
        return True
    return False

def _is_price_mismatch(row: Dict[str, Any]) -> bool:
    status = _pick(row, ["status", "result", "state"]).upper()
    if status in {"PRICE_MISMATCH", "PRICE_CHANGED", "MISMATCH"}:
        return True

    meta_p = _to_int(_pick(row, ["meta_price_int", "meta_price", "price_meta"]))
    site_p = _to_int(_pick(row, ["site_price_int", "kennebec_price_int", "site_price", "price_site"]))
    if meta_p is None or site_p is None:
        return False
    return meta_p != site_p

def _dealer_footer() -> str:
    # doit matcher ton runner (et contient le marqueur pour éviter les doublons)
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

def ensure_single_footer(text: str, footer: str) -> str:
    base = (text or "").rstrip()
    low = base.lower()
    if "[[dg_footer]]" in low:
        return base
    # si DGText a déjà un CTA, on n’ajoute pas
    for m in ["j’accepte", "j'accepte", "échange", "echange", "418-222-3939", "daniel giroux"]:
        if m in low:
            return base
    return f"{base}\n\n{footer}".strip()

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
    base = (base_text or "").strip()
    if not base:
        base = "(Détails indisponibles — contactez-moi.)"
    # éviter double banner
    if base.startswith("🚨 VENDU 🚨"):
        return base
    return _sold_prefix() + base

def main():
    if not AUTOFIX:
        print("AUTOFIX disabled (set KENBOT_AUTOFIX=1).")
        return

    sb = get_client()
    inv = get_inventory_map(sb)          # slug -> vehicle dict
    posts = get_posts_map(sb)            # slug -> post dict

    try:
        blob = _download_report(sb)
    except Exception as e:
        print(f"Cannot download report {OUTPUTS_BUCKET}/{REPORT_PATH}: {e}")
        return

    rows = _parse_csv(blob)

    # Build actions list
    actions: List[Tuple[str, str, Dict[str, Any]]] = []  # (action, stock, row)

    for row in rows:
        stock = _pick(row, ["stock", "id", "vehicle_id"]).upper()
        if not stock:
            continue
        if _is_missing_on_site(row):
            actions.append(("SOLD", stock, row))
        elif _is_price_mismatch(row):
            actions.append(("PRICE", stock, row))

    if not actions:
        print("No actions found in report.")
        return

    # Map stock -> (slug, post_id, base_text)
    stock_to_post = {}
    for slug, info in (posts or {}).items():
        st = (info or {}).get("stock") or ""
        st = st.strip().upper()
        if not st:
            continue
        stock_to_post[st] = (slug, (info or {}).get("post_id"), (info or {}).get("base_text") or "")

    done = 0
    for action, stock, row in actions:
        if done >= MAX_FIX:
            break

        if stock not in stock_to_post:
            continue

        slug, post_id, base_text = stock_to_post[stock]
        if not post_id:
            continue

        if action == "SOLD":
            new_text = _make_sold_message(base_text)
            if DRY:
                print(f"DRY SOLD {stock} post_id={post_id}")
            else:
                try:
                    update_post_text(post_id, FB_TOKEN, new_text)
                    upsert_post(sb, {"slug": slug, "post_id": post_id, "status": "SOLD"})
                    log_event(sb, slug, "AUTO_SOLD_OK", {"stock": stock, "post_id": post_id})
                except Exception as e:
                    log_event(sb, slug, "AUTO_SOLD_FAIL", {"stock": stock, "post_id": post_id, "err": str(e)})
            done += 1
            if SLEEP > 0:
                time.sleep(SLEEP)

        elif action == "PRICE":
            v = inv.get(slug) or {}
            title = (v.get("title") or "").strip()
            vin = (v.get("vin") or "").strip().upper()
            url = (v.get("url") or "").strip()
            price_int = v.get("price_int")
            km_int = v.get("km_int")

            vehicle_payload = {
                "title": title,
                "price": (f"{int(price_int):,}".replace(",", " ") + " $") if isinstance(price_int, int) else "",
                "mileage": (f"{int(km_int):,}".replace(",", " ") + " km") if isinstance(km_int, int) else "",
                "stock": stock,
                "vin": vin,
                "url": url,
            }

            if DRY:
                print(f"DRY PRICE {stock} post_id={post_id}")
            else:
                try:
                    txt = generate_facebook_text(TEXT_ENGINE_URL, slug=slug, event="PRICE_CHANGED", vehicle=vehicle_payload)
                    txt = ensure_single_footer(txt, _dealer_footer())
                    update_post_text(post_id, FB_TOKEN, txt)
                    upsert_post(sb, {"slug": slug, "post_id": post_id, "status": "ACTIVE", "base_text": txt})
                    log_event(sb, slug, "AUTO_PRICE_OK", {"stock": stock, "post_id": post_id})
                except Exception as e:
                    log_event(sb, slug, "AUTO_PRICE_FAIL", {"stock": stock, "post_id": post_id, "err": str(e)})
            done += 1
            if SLEEP > 0:
                time.sleep(SLEEP)

    print(f"AUTOFIX done: actions_applied={done}/{min(len(actions), MAX_FIX)}")

if __name__ == "__main__":
    main()
