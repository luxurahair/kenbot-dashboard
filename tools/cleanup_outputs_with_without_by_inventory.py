import os, re
from dotenv import load_dotenv
load_dotenv(".env", override=False)

from supabase_db import get_client

BUCKET = os.getenv("SB_BUCKET_OUTPUTS", "kennebec-outputs").strip()
DRY = os.getenv("KENBOT_CLEANUP_DRY_RUN", "1") == "1"

# match "46012B_facebook.txt" or "46012B_marketplace.txt"
STOCK_FILE_RE = re.compile(r"^([0-9A-Z]+)_(facebook|marketplace)\.txt$", re.I)

def list_names(sb, prefix: str):
    try:
        items = sb.storage.from_(BUCKET).list(prefix) or []
    except Exception:
        return []
    return [it.get("name") for it in items if it and it.get("name")]

def main():
    sb = get_client()

    # stocks actifs
    inv = (sb.table("inventory")
             .select("stock")
             .eq("status", "ACTIVE")
             .limit(5000)
             .execute().data) or []
    active = set((r.get("stock") or "").strip().upper() for r in inv if (r.get("stock") or "").strip())
    print("active stocks:", len(active))

    total_del = 0
    for prefix in ["with", "without"]:
        names = list_names(sb, prefix)
        to_del = []
        for name in names:
            if not name:
                continue
            # ignore folders like 'assets'
            if "." not in name:
                continue
            m = STOCK_FILE_RE.match(name)
            if not m:
                # fichier non standard -> on le laisse (ou tu peux le supprimer aussi)
                continue
            st = m.group(1).upper()
            if st not in active:
                to_del.append(f"{prefix}/{name}")

        print(f"\n{prefix}: files={len([n for n in names if n and '.' in n])} delete={len(to_del)}")
        if to_del:
            if DRY:
                print(f"[DRY] would delete sample: {to_del[:10]}")
            else:
                for i in range(0, len(to_del), 200):
                    sb.storage.from_(BUCKET).remove(to_del[i:i+200])
                print("[LIVE] deleted:", len(to_del))
                total_del += len(to_del)

    if DRY:
        print("\n✅ DRY RUN terminé. Pour supprimer pour vrai:")
        print("KENBOT_CLEANUP_DRY_RUN=0 python cleanup_outputs_with_without_by_inventory.py")
    else:
        print("\n✅ LIVE DELETE terminé. total_deleted=", total_del)

if __name__ == "__main__":
    main()

