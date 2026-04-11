import os
from dotenv import load_dotenv
load_dotenv(".env", override=False)

from supabase_db import get_client

BUCKET = os.getenv("SB_BUCKET_SNAPSHOTS", "kennebec-facebook-snapshots").strip()
PREFIX = "runs"
KEEP = int(os.getenv("KENBOT_SNAP_KEEP", "3") or "3")
DRY = os.getenv("KENBOT_CLEANUP_DRY_RUN", "1") == "1"

def list_children(sb, folder: str):
    try:
        items = sb.storage.from_(BUCKET).list(folder) or []
    except Exception:
        return []
    return sorted([it.get("name") for it in items if it and it.get("name")], reverse=True)

def list_all_files(sb, folder: str):
    out = []
    try:
        items = sb.storage.from_(BUCKET).list(folder) or []
    except Exception:
        return out
    for it in items:
        name = it.get("name")
        if not name:
            continue
        full = f"{folder}/{name}".strip("/")
        if "." in name:
            out.append(full)
        else:
            out.extend(list_all_files(sb, full))
    return out

def main():
    sb = get_client()
    run_ids = list_children(sb, PREFIX)
    print(f"bucket={BUCKET} prefix={PREFIX} keep={KEEP} dry={DRY}")
    print("found_runs:", len(run_ids))

    keep_runs = run_ids[:KEEP]
    del_runs = run_ids[KEEP:]

    print("\nKEEP:")
    for r in keep_runs:
        print(" ", r)

    print("\nDELETE count:", len(del_runs))

    total = 0
    plan = []
    for rid in del_runs:
        files = list_all_files(sb, f"{PREFIX}/{rid}")
        total += len(files)
        plan.append((rid, files))
        print(f"  {rid} -> files={len(files)}")

    print("\nTOTAL files to remove:", total)

    if DRY:
        print("\n✅ DRY RUN terminé. Pour supprimer pour vrai:")
        print("KENBOT_CLEANUP_DRY_RUN=0 python cleanup_snapshots_runs_now.py")
        return

    deleted = 0
    for rid, files in plan:
        for i in range(0, len(files), 200):
            batch = files[i:i+200]
            sb.storage.from_(BUCKET).remove(batch)
            deleted += len(batch)

    print("\n✅ LIVE DELETE terminé. deleted_files=", deleted)
    print("Supabase Storage → Reload")

if __name__ == "__main__":
    main()

