from dotenv import load_dotenv
load_dotenv(".env", override=False)

from supabase_db import get_client

def norm(s: str) -> str:
    return (s or "").strip().upper()

STATUS_RANK = {"ACTIVE": 3, "MISSING": 2, "SOLD": 1}

def pick_keep(rows):
    """
    Keep rule:
      1) garde celle avec post_id (liée à Facebook)
      2) status: ACTIVE > MISSING > SOLD
      3) last_updated_at le plus récent (si présent)
      4) sinon slug (stable)
    """
    def k(r):
        has_post = 1 if r.get("post_id") else 0
        st_rank = STATUS_RANK.get(norm(r.get("status")), 0)
        lu = str(r.get("last_updated_at") or "")
        return (has_post, st_rank, lu, str(r.get("slug") or ""))
    return sorted(rows, key=k, reverse=True)[0]

def main():
    sb = get_client()

    rows = (sb.table("posts")
              .select("slug,stock,post_id,status,last_updated_at")
              .limit(10000)
              .execute().data) or []

    by_stock = {}
    for r in rows:
        st = norm(r.get("stock"))
        if not st:
            continue
        by_stock.setdefault(st, []).append(r)

    dup_stocks = [st for st, lst in by_stock.items() if len(lst) > 1]
    print("posts rows loaded:", len(rows))
    print("stocks with duplicates:", len(dup_stocks))

    deleted = 0
    for st in sorted(dup_stocks):
        lst = by_stock[st]
        keep = pick_keep(lst)
        keep_slug = keep.get("slug")
        del_slugs = [r.get("slug") for r in lst if r.get("slug") and r.get("slug") != keep_slug]

        print(f"\nSTOCK {st} -> KEEP {keep_slug} post_id={keep.get('post_id')} status={keep.get('status')}")
        for r in lst:
            print(f"  row {r.get('slug')} post_id={r.get('post_id')} status={r.get('status')} last_updated_at={r.get('last_updated_at')}")

        if del_slugs:
            sb.table("posts").delete().in_("slug", del_slugs).execute()
            deleted += len(del_slugs)

    print("\n✅ DONE deleted:", deleted)

if __name__ == "__main__":
    main()
