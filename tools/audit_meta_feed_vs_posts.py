import os, io, csv
from dotenv import load_dotenv
from supabase_db import get_client

load_dotenv(dotenv_path=".env", override=False)

OUTPUTS_BUCKET = os.getenv("SB_BUCKET_OUTPUTS", "kennebec-outputs")

def load_meta_feed(sb):
    path = "feeds/meta_vehicle.csv"
    b = sb.storage.from_(OUTPUTS_BUCKET).download(path)
    txt = (b or b"").decode("utf-8", "ignore")
    rows = list(csv.DictReader(io.StringIO(txt)))
    return rows

def norm_stock(s):
    return (s or "").strip().upper()

def has_sold_banner(text: str) -> bool:
    return (text or "").lstrip().startswith("🚨 VENDU 🚨") or (text or "").lstrip().startswith("🚨VENDU🚨")

def has_rescue(text: str) -> bool:
    t = (text or "").lower()
    return ("mode secours" in t) or ("text-engine indisponible" in t)

def has_footer(text: str) -> bool:
    return "[[DG_FOOTER]]" in (text or "")

def main():
    sb = get_client()

    # 1) Meta feed
    meta_rows = load_meta_feed(sb)
    meta_by_stock = {}
    for r in meta_rows:
        st = norm_stock(r.get("id"))
        if st:
            meta_by_stock[st] = r

    # 2) DB tables
    posts = sb.table("posts").select("post_id,stock,slug,status,base_text,last_updated_at,published_at,sold_at").neq("post_id", None).execute().data or []
    inv = sb.table("inventory").select("stock,slug,status,vin,url,title,price_int,km_int,updated_at,last_seen").execute().data or []

    posts_by_stock = {norm_stock(p.get("stock")): p for p in posts if norm_stock(p.get("stock"))}
    inv_by_stock = {norm_stock(i.get("stock")): i for i in inv if norm_stock(i.get("stock"))}

    # 3) Audit
    report = []
    for stock, m in meta_by_stock.items():
        p = posts_by_stock.get(stock)
        i = inv_by_stock.get(stock)

        base_text = (p or {}).get("base_text") or ""
        fb_status = (p or {}).get("status") or ""
        inv_status = (i or {}).get("status") or ""

        flags = []
        if not p:
            flags.append("NO_POST_ROW")
        if not i:
            flags.append("NO_INVENTORY_ROW")
        if has_rescue(base_text):
            flags.append("TEXT_ENGINE_RESCUE")
        if has_sold_banner(base_text) and (fb_status or "").upper() != "SOLD":
            flags.append("SOLD_BANNER_BUT_DB_ACTIVE")
        if (fb_status or "").upper() == "SOLD" and (inv_status or "").upper() == "ACTIVE":
            flags.append("DB_SOLD_BUT_SITE_ACTIVE")
        if not has_footer(base_text):
            flags.append("MISSING_FOOTER")

        # “suspect not updated” simple: post vieux vs inventory update récent
        # (c’est indicatif, pas parfait)
        if p and i:
            # si inventory a été updated récemment mais posts pas
            if (p.get("last_updated_at") or "") < (i.get("updated_at") or ""):
                flags.append("POST_OLDER_THAN_INVENTORY")

        report.append({
            "stock": stock,
            "meta_title": (m.get("title") or "")[:80],
            "meta_image_link": m.get("image_link") or "",
            "post_id": (p or {}).get("post_id") or "",
            "post_status": fb_status,
            "inv_status": inv_status,
            "vin": (i or {}).get("vin") or "",
            "inv_url": (i or {}).get("url") or "",
            "flags": "|".join(flags),
        })

    # 4) Stats
    total_meta = len(meta_rows)
    total_unique = len(meta_by_stock)
    print(f"META rows={total_meta} unique_stocks={total_unique}")
    print(f"posts rows={len(posts)} inventory rows={len(inv)}")

    flag_counts = {}
    for r in report:
        for f in (r["flags"].split("|") if r["flags"] else []):
            flag_counts[f] = flag_counts.get(f, 0) + 1

    print("\nFLAG COUNTS:")
    for k in sorted(flag_counts.keys()):
        print(f"  {k}: {flag_counts[k]}")

    # 5) Save report locally
    out_path = "reports_meta_audit_texts.csv"
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(report[0].keys()))
        w.writeheader()
        w.writerows(report)

    print(f"\n✅ Report written -> {out_path}")

if __name__ == "__main__":
    main()

