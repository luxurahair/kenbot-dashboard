#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import csv
import time

from dotenv import load_dotenv
load_dotenv(".env", override=False)

from supabase_db import get_client, utc_now_iso, upsert_scrape_run
from fb_api import update_post_text

# On réutilise EXACTEMENT le pipeline de runner_cron_prod
import runner_cron_prod as r

FB_TOKEN = (os.getenv("KENBOT_FB_ACCESS_TOKEN") or os.getenv("FB_PAGE_ACCESS_TOKEN") or "").strip()
SLEEP = int(os.getenv("KENBOT_FB_FIX_SLEEP", "8") or "8")

# Si tu veux absolument ne jamais toucher les NO_PHOTO / cas faibles
SKIP_IF_NO_PHOTO = os.getenv("KENBOT_FB_FIX_SKIP_NO_PHOTO", "1").strip() == "1"


def _safe_run_id() -> str:
    # run_id valide + unique, compatible FK sticker_pdfs_run_id_fkey -> scrape_runs.run_id
    ts = utc_now_iso().replace(":", "").replace("-", "").replace(".", "")
    return f"FB_DIFF_FIX_{ts}"


def main():
    if not FB_TOKEN:
        raise SystemExit("❌ Missing FB token (KENBOT_FB_ACCESS_TOKEN / FB_PAGE_ACCESS_TOKEN)")

    sb = get_client()

    # ✅ créer un run_id valide en DB (FK)
    run_id = _safe_run_id()
    upsert_scrape_run(sb, run_id, status="OK", note="fb live diff rebuild like NEW (sticker priority)")

    rows = list(csv.DictReader(open("report_fb_live_compare.csv", encoding="utf-8")))
    diff = [r0 for r0 in rows if (r0.get("result") or "").strip().upper() == "DIFF"]

    print("DIFF to rebuild:", len(diff))
    if not diff:
        return

    fixed = 0
    skipped = 0

    for item in diff:
        post_id = (item.get("post_id") or "").strip()
        stock = (item.get("stock") or "").strip().upper()

        if not post_id or not stock:
            continue

        # posts row
        p_rows = (
            sb.table("posts")
            .select("post_id,stock,slug,status,base_text,last_updated_at")
            .eq("post_id", post_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not p_rows:
            print("skip: posts not found", stock, post_id)
            skipped += 1
            continue
        p = p_rows[0]

        # inventory row (source vérité site)
        i_rows = (
            sb.table("inventory")
            .select("stock,slug,title,url,vin,price_int,km_int,status,updated_at")
            .eq("stock", stock)
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not i_rows:
            print("skip: inventory not found", stock)
            skipped += 1
            continue
        inv = i_rows[0]

        # Skip NO_PHOTO / cas faibles (comme demandé)
        if SKIP_IF_NO_PHOTO:
            # si info trop faible -> on ne touche pas
            if not inv.get("url") or not inv.get("title"):
                print("skip: weak inventory info (possible no_photo)", stock)
                skipped += 1
                continue

        payload = {
            "slug": (inv.get("slug") or p.get("slug") or "").strip() or stock,
            "stock": stock,
            "title": (inv.get("title") or "").strip(),
            "url": (inv.get("url") or "").strip(),
            "vin": (inv.get("vin") or "").strip(),
            "price_int": inv.get("price_int"),
            "km_int": inv.get("km_int"),
        }

        # ✅ Rebuild EXACTEMENT comme NEW (StickerToAd si possible, sinon fallback)
        try:
            new_text = r._build_ad_text(sb, run_id=run_id, slug=payload["slug"], v=payload, event="NEW")
        except Exception as e:
            print("fail: rebuild", stock, e)
            skipped += 1
            continue

        if not new_text or not new_text.strip():
            print("skip: empty rebuilt text", stock)
            skipped += 1
            continue

        # Push FB + DB
        try:
            update_post_text(post_id, FB_TOKEN, new_text)

            sb.table("posts").update({
                "base_text": new_text,
                "last_updated_at": utc_now_iso(),
                "status": "ACTIVE",
            }).eq("post_id", post_id).execute()

            sb.table("events").insert({
                "slug": "FB_FIX",
                "type": "FB_DIFF_REBUILT_LIKE_NEW",
                "payload": {"stock": stock, "post_id": post_id, "run_id": run_id}
            }).execute()

            print("✅ fixed:", stock, post_id)
            fixed += 1
            time.sleep(max(2, SLEEP))

        except Exception as e:
            print("❌ fail: update fb", stock, post_id, e)
            skipped += 1

    print("\nDONE fixed=", fixed, "skipped=", skipped)


if __name__ == "__main__":
    main()

