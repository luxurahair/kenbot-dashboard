import os
import time
from dotenv import load_dotenv

from supabase_db import get_client, utc_now_iso, upsert_scrape_run
from fb_api import update_post_text
from runner_cron_prod import _build_ad_text

# évite le crash find_dotenv() (python 3.14 + heredoc)
load_dotenv(dotenv_path=".env", override=False)

DRY_RUN = os.getenv("KENBOT_DRY_RUN", "1").strip() == "1"
LIMIT = int(os.getenv("KENBOT_BULK_LIMIT", "200").strip() or "200")
SLEEP = int(os.getenv("KENBOT_BULK_SLEEP", "12").strip() or "12")

FB_TOKEN = os.getenv("KENBOT_FB_ACCESS_TOKEN") or os.getenv("FB_PAGE_ACCESS_TOKEN")
STICKERS_BUCKET = os.getenv("SB_BUCKET_STICKERS", "kennebec-stickers")


def main():
    sb = get_client()
    now = utc_now_iso()

    # IMPORTANT: FK sticker_pdfs.run_id -> scrape_runs.run_id
    # On crée un run_id bulk et aussi "BULK" pour compat (au cas où un sous-module loggue "BULK")
    bulk_run_id = "BULK_" + "".join(ch for ch in now if ch.isdigit())[:14]

    upsert_scrape_run(sb, bulk_run_id, status="RUNNING", note="bulk_update_fb_text_from_stickers")
    upsert_scrape_run(sb, "BULK", status="RUNNING", note="compat bulk")

    if not FB_TOKEN:
        raise SystemExit("Missing FB token (KENBOT_FB_ACCESS_TOKEN)")

    # 1) Posts actifs (pas SOLD)
    posts = (
        sb.table("posts")
        .select("slug,stock,post_id,status,base_text")
        .neq("post_id", None)
        .execute()
        .data
        or []
    )
    posts = [p for p in posts if (p.get("status") or "").upper() != "SOLD"]
    posts = posts[:LIMIT]

    print(f"Loaded posts={len(posts)} DRY_RUN={DRY_RUN}")

    updated = 0
    skipped_same = 0
    skipped_missing_inv = 0
    skipped_no_pdf = 0
    skipped_no_vin = 0

    for p in posts:
        stock = (p.get("stock") or "").strip().upper()
        post_id = p.get("post_id")
        if not stock or not post_id:
            continue

        # 2) Charger le véhicule depuis la table inventory (par stock)
        inv_rows = (
            sb.table("inventory")
            .select("stock,slug,title,url,vin,price_int,km_int")
            .eq("stock", stock)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not inv_rows:
            skipped_missing_inv += 1
            continue

        v = inv_rows[0]
        vin = (v.get("vin") or "").strip().upper()
        if len(vin) != 17:
            skipped_no_vin += 1
            continue

        # 3) Doit avoir pdf_ok/<VIN>.pdf
        pdf_path = f"pdf_ok/{vin}.pdf"
        try:
            pdf = sb.storage.from_(STICKERS_BUCKET).download(pdf_path)
            if not (pdf and pdf[:4] == b"%PDF"):
                skipped_no_pdf += 1
                continue
        except Exception:
            skipped_no_pdf += 1
            continue

        slug = (v.get("slug") or p.get("slug") or "").strip()

        vehicle_payload = {
            "slug": slug,
            "stock": stock,
            "title": v.get("title") or "",
            "url": v.get("url") or "",
            "vin": vin,
            "price_int": v.get("price_int"),
            "km_int": v.get("km_int"),
        }

        # 4) Générer le nouveau texte (StickerToAd si possible, fallback sinon)
        new_text = _build_ad_text(sb, bulk_run_id, slug or stock, vehicle_payload, event="PRICE_CHANGED")
        old_text = (p.get("base_text") or "").strip()

        new_text = (new_text or "")
        old_text = (old_text or "")

        if old_text.strip() == new_text.strip():
            skipped_same += 1
            continue

        # garde-fou : si c'est vide / trop court, on skip (évite post vide)
        if len(new_text.strip()) < 50:
            skipped_same += 1
            continue

        if DRY_RUN:
            print(f"[DRY] would update post={post_id} stock={stock} vin={vin}")
            updated += 1
            continue

        try:
            update_post_text(post_id, FB_TOKEN, new_text)

            sb.table("posts").update({
                "base_text": new_text,
                "last_updated_at": utc_now_iso(),
                "status": "ACTIVE",
            }).eq("post_id", post_id).execute()

            updated += 1
            print(f"✅ updated post={post_id} stock={stock} vin={vin}", flush=True)
            time.sleep(max(2, SLEEP))
        except Exception as e:
            print(f"❌ failed update post={post_id} stock={stock} err={e}", flush=True)

    # Close runs
    upsert_scrape_run(sb, bulk_run_id, status="OK", note="bulk_update_fb_text_from_stickers done")
    upsert_scrape_run(sb, "BULK", status="OK", note="compat bulk done")

    print(
        "DONE "
        f"updated={updated} "
        f"skipped_same={skipped_same} "
        f"skipped_missing_inv={skipped_missing_inv} "
        f"skipped_no_vin={skipped_no_vin} "
        f"skipped_no_pdf={skipped_no_pdf}"
    )


if __name__ == "__main__":
    main()
