import os
from dotenv import load_dotenv
load_dotenv(".env", override=False)

from supabase_db import get_client

BUCKET = os.getenv("SB_BUCKET_OUTPUTS", "kennebec-outputs").strip()
PREFIX = "runs"
KEEP = int(os.getenv("KENBOT_OUTPUT_RUNS_KEEP", "3") or "3")
DRY = os.getenv("KENBOT_CLEANUP_DRY_RUN", "1") == "1"

def list_children(sb, folder: str):
    try:
        items = sb.storage.from_(BUCKET).list(folder) or []
    except Exception:
        return []
    names = [it.get("name") for it in items if it and it.get("name")]
    return sorted(names)

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
        # fichier probable
        if "." in name:
            out.append(full)
        else:
            out.extend(list_all_files(sb, full))
    return out

def main():
    sb = get_client()
    print(f"bucket={BUCKET} prefix={PREFIX} keep={KEEP} dry={DRY}")

    # IMPORTANT: list peut être paginé; on force une stratégie simple:
    # on liste les "premiers niveaux" et on boucle jusqu'à ce que ça ne bouge plus
    # (ça marche dans la pratique parce que Supabase Storage retourne tout pour un prefix raisonnable)
    run_ids = list_children(sb, PREFIX)

    print("found_runs:", len(run_ids))
    run_ids_sorted = sorted(run_ids, reverse=True)
    keep_runs = run_ids_sorted[:KEEP]
    del_runs = run_ids_sorted[KEEP:]

    print("\nKEEP:")
    for r in keep_runs:
        print(" ", r)

    print("\nDELETE count:", len(del_runs))

    total_files = 0
    plan = []
    for rid in del_runs:
        root = f"{PREFIX}/{rid}"
        files = list_all_files(sb, root)
        total_files += len(files)
        plan.append((rid, files))
        print(f"  {rid} -> files={len(files)}")

    print("\nTOTAL files to remove:", total_files)

    if DRY:
        print("\n✅ DRY RUN terminé. Pour supprimer pour vrai :")
        print("KENBOT_CLEANUP_DRY_RUN=0 python cleanup_runs_recursive_now.py")
        return

    deleted = 0
    for rid, files in plan:
        if not files:
            continue
        for i in range(0, len(files), 200):
            batch = files[i:i+200]
            sb.storage.from_(BUCKET).remove(batch)
            deleted += len(batch)

    print("\n✅ LIVE DELETE terminé. deleted_files=", deleted)
    print("Supabase Storage → Reload (l’UI cache parfois les folders vides).")

if __name__ == "__main__":
    main()

