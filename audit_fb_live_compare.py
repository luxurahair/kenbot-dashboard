import os, csv
from dotenv import load_dotenv
load_dotenv(".env", override=False)

from supabase_db import get_client

FB_TOKEN = (os.getenv("KENBOT_FB_ACCESS_TOKEN") or os.getenv("FB_PAGE_ACCESS_TOKEN") or "").strip()
LIMIT = int(os.getenv("KENBOT_FB_AUDIT_LIMIT", "25") or "25")

# ----- FB fetch (Graph API) -----
def fetch_fb_post_message(post_id: str, token: str) -> str:
    """
    Minimal Graph API call: GET /{post_id}?fields=message
    Returns message string (or "")
    """
    import requests
    url = f"https://graph.facebook.com/v19.0/{post_id}"
    r = requests.get(url, params={"fields": "message", "access_token": token}, timeout=25)
    r.raise_for_status()
    j = r.json() or {}
    return (j.get("message") or "").strip()

def norm_text(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    # normalise espaces multiples
    s = "\n".join(line.rstrip() for line in s.splitlines())
    return s

def main():
    if not FB_TOKEN:
        raise SystemExit("❌ Missing FB token (KENBOT_FB_ACCESS_TOKEN or FB_PAGE_ACCESS_TOKEN)")

    sb = get_client()

    # posts récents “touchables”
    posts = (sb.table("posts")
               .select("post_id,stock,slug,status,base_text,last_updated_at,published_at")
               .neq("post_id", None)
               .order("last_updated_at", desc=True)
               .limit(LIMIT)
               .execute().data) or []

    print(f"pulled posts: {len(posts)}  (limit={LIMIT})")

    out_rows = []
    ok = diff = fail = 0

    for p in posts:
        post_id = p.get("post_id")
        stock = (p.get("stock") or "").strip().upper()
        slug = (p.get("slug") or "").strip()
        db_text = norm_text(p.get("base_text") or "")
        db_status = (p.get("status") or "").upper()

        fb_text = ""
        result = ""
        err = ""

        try:
            fb_text = norm_text(fetch_fb_post_message(post_id, FB_TOKEN))
            if fb_text == db_text:
                result = "OK"
                ok += 1
            else:
                result = "DIFF"
                diff += 1
        except Exception as e:
            result = "FB_GET_FAIL"
            err = str(e)
            fail += 1

        out_rows.append({
            "result": result,
            "stock": stock,
            "slug": slug,
            "post_id": post_id,
            "db_status": db_status,
            "last_updated_at": p.get("last_updated_at") or "",
            "db_len": len(db_text),
            "fb_len": len(fb_text),
            "err": err[:180],
        })

    out_path = "report_fb_live_compare.csv"
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()) if out_rows else ["result"])
        w.writeheader()
        w.writerows(out_rows)

    print("\nSTATS:")
    print("  OK:", ok)
    print("  DIFF:", diff)
    print("  FB_GET_FAIL:", fail)
    print("\n✅ wrote:", out_path)

if __name__ == "__main__":
    main()

