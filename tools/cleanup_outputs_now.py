import os, re
from dotenv import load_dotenv
load_dotenv(".env", override=False)
from supabase_db import get_client

BUCKET = os.getenv("SB_BUCKET_OUTPUTS", "kennebec-outputs").strip()
KEEP_RUNS = int(os.getenv("KENBOT_OUTPUT_RUNS_KEEP", "3") or "3")
DRY = os.getenv("KENBOT_CLEANUP_DRY_RUN", "1") == "1"

RUN_ID_RE = re.compile(r"^\d{8}_\d{6}$")  # 20260202_190935 etc.

def list_all(sb, folder: str):
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
            out.extend(list_all(sb, full))
    return out

def delete_paths(sb, paths, label):
    if not paths:
        return 0
    if DRY:
        print(f"[DRY] {label}: would delete files={len(paths)}")
        return 0
    # batch remove
    deleted = 0
    for i in range(0, len(paths), 200):
        sb.storage.from_(BUCKET).remove(paths[i:i+200])
        deleted += len(paths[i:i+200])
    print(f"[LIVE] {label}: deleted files={deleted}")
    return deleted

def main():
    sb = get_client()
    print(f"bucket={BUCKET} keep_runs={KEEP_RUNS} dry={DRY}")

    # 1) runs/<run_id>/...  -> keep N latest
    top_runs = sb.storage.from_(BUCKET).list("runs") or []
    run_ids = sorted([it.get("name") for it in top_runs if it.get("name")], reverse=True)
    keep = run_ids[:KEEP_RUNS]
    kill = run_ids[KEEP_RUNS:]
    print("\nRUNS keep:", keep)
    print("RUNS delete count:", len(kill))
    run_files = []
    for rid in kill:
        run_files.extend(list_all(sb, f"runs/{rid}"))
    delete_paths(sb, run_files, "runs/<old>")

    # 2) feeds/ : keep only feeds/meta_vehicle.csv + feeds/ folder itself
    # delete any subfolder that looks like a run_id (feeds/2026.../...)
    feeds_items = sb.storage.from_(BUCKET).list("feeds") or []
    feed_files = []
    for it in feeds_items:
        name = it.get("name")
        if not name:
            continue
        if name == "meta_vehicle.csv":
            continue
        if RUN_ID_RE.match(name):
            feed_files.extend(list_all(sb, f"feeds/{name}"))
        else:
            # any other junk file under feeds (optional)
            if "." in name:
                feed_files.append(f"feeds/{name}")
            else:
                # unknown folder => delete too
                feed_files.extend(list_all(sb, f"feeds/{name}"))
    delete_paths(sb, feed_files, "feeds/<snapshots>")

    # 3) reports/ : keep only reports/meta_vs_site.csv
    rep_items = sb.storage.from_(BUCKET).list("reports") or []
    rep_files = []
    for it in rep_items:
        name = it.get("name")
        if not name:
            continue
        if name == "meta_vs_site.csv":
            continue
        if RUN_ID_RE.match(name):
            rep_files.extend(list_all(sb, f"reports/{name}"))
        else:
            if "." in name:
                rep_files.append(f"reports/{name}")
            else:
                rep_files.extend(list_all(sb, f"reports/{name}"))
    delete_paths(sb, rep_files, "reports/<snapshots>")

    print("\nDONE. Après LIVE: Supabase Storage -> Reload (la UI cache parfois).")

if __name__ == "__main__":
    main()

