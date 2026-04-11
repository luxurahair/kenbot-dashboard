import os
from dotenv import load_dotenv
from supabase_db import get_client

load_dotenv(".env", override=False)

def norm(s: str) -> str:
    return (s or "").strip().upper()

STATUS_RANK = {"ACTIVE": 3, "MISSING": 2, "SOLD": 1}

def pick_keep_row(rows):
    def k(r):
        st = norm(r.get("status"))
        return (
            STATUS_RANK.get(st, 0),
            str(r.get("updated_at") or ""),
            str(r.get("last_seen") or ""),
        )
    return sorted(rows, key=k, reverse=True)[0]

def main():
    sb = get_client()

    inv = (
        sb.table("inventory")
        .select("stock,slug,vin,status,updated_at,last_seen,url,title")
        .limit(10000)
        .execute()
        .data
        or []
    )

    by_stock = {}
    for r in inv:
        st = norm(r.get("stock"))
        if not st:
            continue
        by_stock.setdefault(st, []).append(r)

    dup_stocks = [st for st, rows in by_stock.items() if len(rows) > 1]
    print(f"inventory rows loaded: {len(inv)}")
    print(f"stocks with duplicates: {len(dup_stocks)}")

    total_deleted = 0
    total_kept = 0

    for st in sorted(dup_stocks):
        rows = by_stock[st]
        keep = pick_keep_row(rows)
        keep_slug = keep.get("slug")
        del_slugs = [r.get("slug") for r in rows if r.get("slug") and r.get("slug") != keep_slug]

        print(f"\nSTOCK {st} -> KEEP slug={keep_slug} status={keep.get('status')}")
        for r in rows:
            print(f"  row slug={r.get('slug')} status={r.get('status')} updated_at={r.get('updated_at')} last_seen={r.get('last_seen')}")

        if del_slugs:
            # DELETE direct par slug
            sb.table("inventory").delete().in_("slug", del_slugs).execute()
            total_deleted += len(del_slugs)
            total_kept += 1

    print("\n✅ DONE")
    print(f"kept (one per duplicated stock): {total_kept}")
    print(f"deleted rows: {total_deleted}")

if __name__ == "__main__":
    main()
