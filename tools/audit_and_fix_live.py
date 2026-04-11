import os
import io
import csv
import time
from typing import Dict, Any, List

from dotenv import load_dotenv

from supabase_db import get_client, utc_now_iso, upsert_scrape_run
from fb_api import update_post_text
from runner_cron_prod import _build_ad_text

# Optional: scraper detail pour photos
from kennebec_scrape import parse_vehicle_detail_simple

load_dotenv(dotenv_path=".env", override=False)

RAW_BUCKET = os.getenv("SB_BUCKET_RAW", "kennebec-raw")
OUTPUTS_BUCKET = os.getenv("SB_BUCKET_OUTPUTS", "kennebec-outputs")
STICKERS_BUCKET = os.getenv("SB_BUCKET_STICKERS", "kennebec-stickers")

FB_TOKEN = os.getenv("KENBOT_FB_ACCESS_TOKEN") or os.getenv("FB_PAGE_ACCESS_TOKEN")

DRY_RUN = os.getenv("KENBOT_DRY_RUN", "1").strip() == "1"
SLEEP = int(os.getenv("KENBOT_FIX_SLEEP", "12").strip() or "12")
LIMIT = int(os.getenv("KENBOT_FIX_LIMIT", "999").strip() or "999")  # sécurité

ALLOW_NO_PHOTO = os.getenv("KENBOT_ALLOW_NO_PHOTO", "1").strip() == "1"
NO_PHOTO_URL = (os.getenv("KENBOT_NO_PHOTO_URL") or "").strip()

if not NO_PHOTO_URL:
    nb = (os.getenv("KENBOT_NO_PHOTO_BUCKET") or "").strip()
    np = (os.getenv("KENBOT_NO_PHOTO_PATH") or "").strip().lstrip("/")
    sb_url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    if nb and np and sb_url:
        NO_PHOTO_URL = f"{sb_url}/storage/v1/object/public/{nb}/{np}"

def strip_sold_banner(txt: str) -> str:
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

def build_audit_csv(rows: List[Dict[str, Any]]) -> bytes:
    fieldnames = [
        "stock","slug","post_id","fb_status","site_present","action",
        "vin","url","note"
    ]
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fieldnames})
    return buf.getvalue().encode("utf-8")

def read_meta_feed(sb) -> List[Dict[str, str]]:
    # lit kennebec-outputs/feeds/meta_vehicle.csv si présent
    try:
        b = sb.storage.from_(OUTPUTS_BUCKET).download("feeds/meta_vehicle.csv")
    except Exception:
        return []
    txt = (b or b"").decode("utf-8", "ignore")
    if not txt.strip():
        return []
    rdr = csv.DictReader(io.StringIO(txt))
    return list(rdr)

def write_meta_feed(sb, rows: List[Dict[str, Any]], run_id: str) -> None:
    # rows = inventory dicts enrichis (avec photos éventuelles)
    fieldnames = ["id","title","description","availability","condition","price","link","image_link","brand","year"]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=fieldnames)
    w.writeheader()

    for v in rows:
        stock = (v.get("stock") or "").strip().upper()
        title = (v.get("title") or "").strip()
        url = (v.get("url") or "").strip()
        price_int = v.get("price_int")
        vin = (v.get("vin") or "").strip()

        if not stock or not title or not url or not isinstance(price_int, int):
            continue

        photos = v.get("photos") or []
        image_link = (photos[0] or "").strip() if photos else ""

        if (not image_link) and ALLOW_NO_PHOTO and NO_PHOTO_URL:
            image_link = NO_PHOTO_URL

        if not image_link:
            continue

        year = ""
        # année dans title
        import re
        m = re.search(r"\b(19\d{2}|20\d{2})\b", title)
        if m:
            year = m.group(1)

        brand = (v.get("make") or "").strip()
        if not brand:
            brand = title.split(" ", 1)[0].strip()

        w.writerow({
            "id": stock,
            "title": title,
            "description": f"{title} | Stock {stock}",
            "availability": "in stock",
            "condition": "used",
            "price": f"{price_int} CAD",
            "link": url,
            "image_link": image_link,
            "brand": brand,
            "year": year,
        })

    feed_bytes = out.getvalue().encode("utf-8")
    # canon + snapshot run
    sb.storage.from_(OUTPUTS_BUCKET).upload(
        "feeds/meta_vehicle.csv",
        feed_bytes,
        {"content-type":"text/csv; charset=utf-8", "x-upsert":"true"},
    )
    sb.storage.from_(OUTPUTS_BUCKET).upload(
        f"runs/{run_id}/feeds/meta_vehicle.csv",
        feed_bytes,
        {"content-type":"text/csv; charset=utf-8", "x-upsert":"true"},
    )

def main():
    sb = get_client()
    now = utc_now_iso()

    if not FB_TOKEN:
        raise SystemExit("Missing FB token (KENBOT_FB_ACCESS_TOKEN)")

    run_id = "AUDITFIX_" + "".join(ch for ch in now if ch.isdigit())[:14]
    upsert_scrape_run(sb, run_id, status="RUNNING", note="audit_and_fix_live")

    # compat FK si un sous-module loggue BULK
    upsert_scrape_run(sb, "BULK", status="RUNNING", note="compat bulk")
    upsert_scrape_run(sb, run_id, status="RUNNING", note="audit_and_fix_live running")

    # 1) SITE truth = inventory ACTIVE
    inv_rows = (
        sb.table("inventory")
        .select("stock,slug,title,url,vin,price_int,km_int,status")
        .eq("status", "ACTIVE")
        .limit(2000)
        .execute()
        .data
        or []
    )
    site_by_stock = {(r.get("stock") or "").strip().upper(): r for r in inv_rows if (r.get("stock") or "").strip()}
    site_stocks = set(site_by_stock.keys())

    # 2) FB posts
    posts = (
        sb.table("posts")
        .select("slug,stock,post_id,status,base_text")
        .neq("post_id", None)
        .limit(2000)
        .execute()
        .data
        or []
    )

    audit_rows: List[Dict[str, Any]] = []
    restored = 0
    text_fixed = 0

    # 3) Audit + fixes (restore + text)
    for p in posts[:LIMIT]:
        stock = (p.get("stock") or "").strip().upper()
        slug = (p.get("slug") or "").strip()
        post_id = p.get("post_id")
        fb_status = (p.get("status") or "").upper()

        site_present = "YES" if stock in site_stocks else "NO"

        inv = site_by_stock.get(stock) or {}
        vin = (inv.get("vin") or "").strip().upper()
        url = (inv.get("url") or "").strip()
        title = (inv.get("title") or "").strip()
        price_int = inv.get("price_int")
        km_int = inv.get("km_int")

        action = "OK"
        note = ""

        # Restore faux SOLD: fb SOLD mais encore sur site
        if fb_status == "SOLD" and site_present == "YES":
            action = "RESTORE_FALSE_SOLD"
            base_text = (p.get("base_text") or "").strip()
            restored_text = strip_sold_banner(base_text) if base_text else "(texte manquant)"

            if DRY_RUN:
                note = "DRY: would restore"
            else:
                try:
                    update_post_text(post_id, FB_TOKEN, restored_text)
                    sb.table("posts").update({
                        "status": "ACTIVE",
                        "sold_at": None,
                        "last_updated_at": utc_now_iso(),
                        "base_text": restored_text,
                    }).eq("post_id", post_id).execute()
                    restored += 1
                    note = "restored"
                    time.sleep(max(2, SLEEP))
                except Exception as e:
                    note = f"restore_fail: {e}"

        # Fix text via StickerToAd si pdf_ok existe (ACTIVE seulement)
        if site_present == "YES" and fb_status != "SOLD" and vin and len(vin) == 17:
            # check pdf_ok
            try:
                pdf = sb.storage.from_(STICKERS_BUCKET).download(f"pdf_ok/{vin}.pdf")
                has_pdf_ok = bool(pdf) and pdf[:4] == b"%PDF"
            except Exception:
                has_pdf_ok = False

            if has_pdf_ok:
                action = "FIX_TEXT_STICKER"
                vehicle_payload = {
                    "slug": slug or (inv.get("slug") or ""),
                    "stock": stock,
                    "title": title,
                    "url": url,
                    "vin": vin,
                    "price_int": price_int,
                    "km_int": km_int,
                }

                new_text = _build_ad_text(sb, run_id, slug or stock, vehicle_payload, event="PRICE_CHANGED")
                old_text = (p.get("base_text") or "").strip()

                if old_text.strip() == new_text.strip():
                    note = (note + " | same").strip(" |")
                else:
                    if DRY_RUN:
                        note = (note + " | DRY: would update text").strip(" |")
                    else:
                        try:
                            update_post_text(post_id, FB_TOKEN, new_text)
                            sb.table("posts").update({
                                "base_text": new_text,
                                "last_updated_at": utc_now_iso(),
                                "status": "ACTIVE",
                            }).eq("post_id", post_id).execute()
                            text_fixed += 1
                            note = (note + " | text_updated").strip(" |")
                            time.sleep(max(2, SLEEP))
                        except Exception as e:
                            note = (note + f" | text_fail:{e}").strip(" |")
            else:
                if action == "OK":
                    action = "NO_PDF_OK"

        audit_rows.append({
            "stock": stock,
            "slug": slug,
            "post_id": post_id,
            "fb_status": fb_status,
            "site_present": site_present,
            "action": action,
            "vin": vin,
            "url": url,
            "note": note,
        })

    # 4) Upload audit CSV
    audit_bytes = build_audit_csv(audit_rows)
    sb.storage.from_(OUTPUTS_BUCKET).upload(
        "reports/audit_meta_vs_kennebec_live.csv",
        audit_bytes,
        {"content-type":"text/csv; charset=utf-8", "x-upsert":"true"},
    )
    sb.storage.from_(OUTPUTS_BUCKET).upload(
        f"runs/{run_id}/reports/audit_meta_vs_kennebec_live.csv",
        audit_bytes,
        {"content-type":"text/csv; charset=utf-8", "x-upsert":"true"},
    )

    # 5) NO_PHOTO refresh NOW: re-scrape details for stocks that still have NO_PHOTO in feed, then regenerate feed
    # (FULL D: on le fait maintenant)
    refreshed_photos = 0
    meta_feed = read_meta_feed(sb)

    if meta_feed and NO_PHOTO_URL:
        need = [r for r in meta_feed if (r.get("image_link") or "").strip() == NO_PHOTO_URL]
        # on limite un peu pour éviter de scraper 2000 pages
        need = need[:50]

        # Build list of inventory rows enriched with photos for those needing refresh
        enriched: Dict[str, Dict[str, Any]] = {k: dict(v) for k, v in site_by_stock.items()}

        for r in need:
            stock = (r.get("id") or "").strip().upper()
            inv = enriched.get(stock)
            if not inv:
                continue
            url = (inv.get("url") or "").strip()
            if not url:
                continue

            if DRY_RUN:
                continue

            try:
                fresh = parse_vehicle_detail_simple(None, url)  # function should tolerate session None? if not, fallback below
            except Exception:
                # fallback: use requests session from runner_cron_prod style (simple)
                import requests
                sess = requests.Session()
                fresh = parse_vehicle_detail_simple(sess, url)

            photos = fresh.get("photos") or []
            if photos and (photos[0] or "").strip() and (photos[0] or "").strip() != NO_PHOTO_URL:
                inv["photos"] = photos
                refreshed_photos += 1

        if (not DRY_RUN) and refreshed_photos > 0:
            write_meta_feed(sb, list(enriched.values()), run_id)

    upsert_scrape_run(sb, run_id, status="OK", note=f"audit_and_fix_live done restored={restored} text_fixed={text_fixed} no_photo_fixed={refreshed_photos}")
    upsert_scrape_run(sb, "BULK", status="OK", note="compat bulk done")

    print(f"✅ AUDIT+FIX done run_id={run_id} DRY_RUN={DRY_RUN} restored={restored} text_fixed={text_fixed} no_photo_fixed={refreshed_photos}")
    print("Report -> kennebec-outputs/reports/audit_meta_vs_kennebec_live.csv")


if __name__ == "__main__":
    main()

