import os
from dotenv import load_dotenv
load_dotenv()

from supabase_db import get_client, get_posts_map, get_inventory_map, upsert_post, upsert_inventory, utc_now_iso, log_event
from fb_api import update_post_text

FB_TOKEN = (os.getenv("KENBOT_FB_ACCESS_TOKEN") or os.getenv("FB_PAGE_ACCESS_TOKEN") or "").strip()
if not FB_TOKEN:
    raise SystemExit("Missing FB token env (KENBOT_FB_ACCESS_TOKEN / FB_PAGE_ACCESS_TOKEN)")

# Mets ici ce que ton audit a sorti (slugs_sold=...)
GHOST_SLUGS = [
    "ram-promaster-2500-high-2023-06203",
    "dodge-grand-caravan-sxt-premium-plus-2019-45196a",
    "honda-civic-sedan-ex-t-2016-46012b",
    "ram-1500-laramie-sport-2022-46037a",
]

DRY = os.getenv("KENBOT_DRY_RUN", "0").strip() == "1"

def main():
    sb = get_client()
    posts = get_posts_map(sb)
    inv = get_inventory_map(sb)
    now = utc_now_iso()

    for slug in GHOST_SLUGS:
        post = posts.get(slug) or {}
        post_id = post.get("post_id")
        base_text = (post.get("base_text") or "").strip()

        print(f"\n=== UNSOLD {slug} ===")
        if not post_id:
            print("⚠️ no post_id in posts table for this slug (Supabase). Skipping FB edit.")
        elif not base_text:
            print("⚠️ base_text empty for this slug -> cannot restore clean text safely. Skipping FB edit.")
        else:
            if DRY:
                print(f"DRY_RUN: would restore FB post text for {post_id}")
            else:
                update_post_text(post_id, FB_TOKEN, base_text)
                print(f"✅ FB restored text for post_id={post_id}")

        # Supabase posts -> ACTIVE
        upsert_post(sb, {
            "slug": slug,
            "post_id": post_id,
            "status": "ACTIVE",
            "sold_at": None,
            "last_updated_at": now,
            "base_text": base_text or post.get("base_text"),
            "stock": post.get("stock"),
        })

        # Supabase inventory -> ACTIVE
        old = inv.get(slug) or {}
        upsert_inventory(sb, [{
            "slug": slug,
            "stock": old.get("stock"),
            "url": old.get("url"),
            "title": old.get("title"),
            "vin": old.get("vin"),
            "price_int": old.get("price_int"),
            "km_int": old.get("km_int"),
            "status": "ACTIVE",
            "last_seen": old.get("last_seen") or now,
            "updated_at": now,
        }])

        log_event(sb, slug, "UNSOLD_REPAIR", {"post_id": post_id, "run_id": "manual_fix", "ts": now})
        print("✅ Supabase repaired (posts+inventory set ACTIVE)")

if __name__ == "__main__":
    main()
