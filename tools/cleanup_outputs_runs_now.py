import os
from dotenv import load_dotenv
load_dotenv(".env", override=False)

from supabase_db import get_client

OUTPUTS_BUCKET = os.getenv("SB_BUCKET_OUTPUTS", "kennebec-outputs").strip()
PREFIX = os.getenv("KENBOT_OUTPUTS_RUNS_PREFIX", "runs").strip().strip("/")
KEEP = int(os.getenv("KENBOT_OUTPUT_RUNS_KEEP", "3").strip() or "3")

# 1 = dry run (print only), 0 = delete for real
DRY_RUN = os.getenv("KENBOT_CLEANUP_DRY_RUN", "1").strip() == "1"

def list_all_files(sb, bucket: str, folder: str):
    """
    Liste récursive de TOUS les fichiers sous folder (paths complets).
    """
    out = []
    try:
        items = sb.storage.from_(bucket).list(folder) or []
    except Exception:
        return out

    for it in items:
        name = it.get("name")
        if not name:
            continue
        full = f"{folder}/{name}"

        # Heuristique: si ça ressemble à un fichier => on garde
        if "." in name:
            out.append(full)
        else:
            out.extend(list_all_files(sb, bucket, full))
    return out

def main():
    sb = get_client()

    # Liste des run_id dans runs/
    top = sb.storage.from_(OUTPUTS_BUCKET).list(PREFIX) or []
    run_ids = sorted([it.get("name") for it in top if it and it.get("name")], reverse=True)

    print(f"bucket={OUTPUTS_BUCKET} prefix={PREFIX} keep={KEEP} dry_run={DRY_RUN}")
    print(f"found_runs={len(run_ids)}")

    keep_runs = run_ids[:KEEP]
    del_runs = run_ids[KEEP:]

    print("\nKEEP:")
    for r in keep_runs:
        print("  ", r)

    print("\nDELETE:")
    total_files = 0
    plan = []  # list of (run_id, files)

    for rid in del_runs:
        root = f"{PREFIX}/{rid}"
        files = list_all_files(sb, OUTPUTS_BUCKET, root)
        total_files += len(files)
        plan.append((rid, files))
        print(f"  {rid} -> files={len(files)}")

    print(f"\nTOTAL files to remove: {total_files}")

    if DRY_RUN:
        print("\n✅ DRY RUN terminé. Pour supprimer pour vrai:")
        print("KENBOT_CLEANUP_DRY_RUN=0 python cleanup_outputs_runs_now.py")
        return

    # Live delete
    deleted_files = 0
    for rid, files in plan:
        if not files:
            continue
        # delete par batch (évite payload trop gros)
        batch_size = 200
        for i in range(0, len(files), batch_size):
            batch = files[i:i+batch_size]
            sb.storage.from_(OUTPUTS_BUCKET).remove(batch)
            deleted_files += len(batch)

    print(f"\n✅ LIVE DELETE terminé. deleted_files={deleted_files}")
    print("Va dans Supabase Storage et clique Reload (la UI cache parfois les folders vides).")

if __name__ == "__main__":
    main()

