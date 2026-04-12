import os
from dotenv import load_dotenv
load_dotenv()

from supabase import create_client, Client
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import json
import hashlib


# =========================
# Time
# =========================
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =========================
# Client
# =========================
def get_client(url: str | None = None, key: str | None = None) -> Client:
    url = (url or os.getenv("SUPABASE_URL") or "").strip()
    key = (key or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()

    if not url or not key:
        raise RuntimeError("Missing SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY")

    base = url.rstrip("/")
    sb = create_client(base, key)

    # Force le endpoint Storage avec slash (évite le warning)
    try:
        sb.storage_url = f"{base}/storage/v1/"
    except Exception:
        pass

    return sb

# =========================
# Core tables: inventory / posts / events
# =========================
def upsert_inventory(sb: Client, rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    cleaned: List[Dict[str, Any]] = []
    for r in rows:
        st = (r.get("stock") or "").strip().upper()
        if not st:
            continue  # pas de stock => on skip (sinon on casse l'unicité)
        r["stock"] = st

        # slug utile mais pas clé; on le garde propre
        if r.get("slug"):
            r["slug"] = str(r["slug"]).strip()

        cleaned.append(r)

    if not cleaned:
        return

    # ✅ maintenant que DB a UNIQUE(stock), on upsert sur stock
    sb.table("inventory").upsert(cleaned, on_conflict="stock").execute()


def get_inventory_map(sb: Client) -> Dict[str, Dict[str, Any]]:
    res = sb.table("inventory").select("*").execute()
    data = res.data or []
    return {r["slug"]: r for r in data if r.get("slug")}


from postgrest.exceptions import APIError

def upsert_post(sb: Client, row: Dict[str, Any]) -> None:
    if not row:
        return

    stock = (row.get("stock") or "").strip().upper()
    slug = (row.get("slug") or "").strip()

    if not stock:
        raise ValueError("upsert_post: stock obligatoire")

    row["stock"] = stock
    row["slug"] = slug or None

    # Try upsert on stock first; if slug conflict, update by stock instead
    try:
        sb.table("posts").upsert(
            row,
            on_conflict="stock"
        ).execute()
    except Exception as e:
        err_msg = str(e)
        if "23505" in err_msg or "duplicate key" in err_msg.lower():
            # Slug conflict — update existing row by stock
            update_row = {k: v for k, v in row.items() if k != "slug"}
            sb.table("posts").update(update_row).eq("stock", stock).execute()
        else:
            raise


def get_posts_map(sb: Client) -> Dict[str, Dict[str, Any]]:
    res = sb.table("posts").select("*").execute()
    data = res.data or []
    return {r["slug"]: r for r in data if r.get("slug")}


def log_event(sb: Client, slug: str, typ: str, payload: Dict[str, Any]) -> None:
    sb.table("events").insert({"slug": slug, "type": typ, "payload": payload}).execute()


# =========================
# Mémoire tables (ALIGNED to your schema)
# =========================
def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data or b"").hexdigest()


def upsert_scrape_run(sb: Client, run_id: str, status: str = "OK", note: str = "") -> None:
    """
    scrape_runs:
      run_id (text, NOT NULL)
      created_at (timestamptz, NOT NULL)
      status (text, NOT NULL)
      note (text, nullable)
    """
    sb.table("scrape_runs").upsert(
        {
            "run_id": run_id,
            "created_at": utc_now_iso(),
            "status": status,
            "note": (note or None),
        },
        on_conflict="run_id",
    ).execute()


def upsert_raw_page(sb: Client, run_id: str, page_no: int, storage_path: str, data: bytes) -> None:
    """
    raw_pages:
      run_id (text, NOT NULL)
      page_no (int4, NOT NULL)
      storage_path (text, NOT NULL)
      bytes (int4, NOT NULL)
      sha256 (text, NOT NULL)
    """
    sb.table("raw_pages").upsert(
        {
            "run_id": run_id,
            "page_no": int(page_no),
            "storage_path": storage_path,
            "bytes": len(data or b""),
            "sha256": sha256_hex(data or b""),
        },
        on_conflict="run_id,page_no",
    ).execute()


def upsert_sticker_pdf(
    sb: Client,
    vin: str,
    status: str,
    storage_path: str,
    data: bytes,
    reason: str = "",
    run_id: str = "",
) -> None:
    """
    sticker_pdfs:
      vin (text, NOT NULL)
      status (text, NOT NULL)
      storage_path (text, NOT NULL)
      bytes (int4, NOT NULL)
      sha256 (text, NOT NULL)
      reason (text, nullable)
      run_id (text, nullable)
      updated_at (timestamptz, NOT NULL)
    """
    sb.table("sticker_pdfs").upsert(
        {
            "vin": (vin or "").strip().upper(),
            "status": status,
            "storage_path": storage_path,
            "bytes": len(data or b""),
            "sha256": sha256_hex(data or b""),
            "reason": (reason or None),
            "run_id": (run_id or None),
            "updated_at": utc_now_iso(),
        },
        on_conflict="vin",
    ).execute()


def upsert_output(
    sb: Client,
    stock: str,
    kind: str,
    facebook_path: str,
    marketplace_path: str,
    run_id: str = "",
) -> None:
    sb.table("outputs").upsert(
        {
            "stock": (stock or "").strip().upper(),
            "kind": (kind or "").strip(),
            "facebook_path": facebook_path,
            "marketplace_path": marketplace_path,
            "run_id": run_id or None,
            "updated_at": utc_now_iso(),
        },
        on_conflict="stock,kind",
    ).execute()

# =========================
# Storage helpers (RESTORED)
# =========================
import json
from typing import Any, Optional, List


def upload_bytes_to_storage(
    sb,
    bucket: str,
    path: str,
    data: bytes,
    content_type: str = "application/octet-stream",
    upsert: bool = True,
) -> None:
    bucket = (bucket or "").strip()
    path = (path or "").lstrip("/")
    if not bucket or not path:
        raise ValueError("upload_bytes_to_storage: missing bucket/path")

    sb.storage.from_(bucket).upload(
        path,
        data,
        file_options={
            "content-type": content_type,
            "upsert": "true" if upsert else "false",  # IMPORTANT: str, pas bool
        },
    )


def upload_json_to_storage(
    sb,
    bucket: str,
    path: str,
    obj: Any,
    upsert: bool = True,
) -> None:
    b = json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")
    upload_bytes_to_storage(
        sb,
        bucket,
        path,
        b,
        content_type="application/json; charset=utf-8",
        upsert=upsert,
    )


def read_json_from_storage(
    sb,
    bucket: str,
    path: str,
) -> Optional[Any]:
    bucket = (bucket or "").strip()
    path = (path or "").lstrip("/")
    if not bucket or not path:
        return None
    try:
        blob = sb.storage.from_(bucket).download(path)
    except Exception:
        return None
    try:
        return json.loads(blob.decode("utf-8", errors="replace"))
    except Exception:
        return None


def cleanup_storage_runs(sb, bucket: str, prefix: str, keep: int = 5) -> None:
    """
    Supprime récursivement les vieux runs dans Storage bucket/prefix/<run_id>/...
    en gardant les `keep` plus récents.
    """
    bucket = (bucket or "").strip()
    prefix = (prefix or "").strip().strip("/")
    if not bucket or not prefix or keep <= 0:
        return

    try:
        top = sb.storage.from_(bucket).list(prefix) or []
    except Exception:
        return

    run_ids = sorted([it.get("name") for it in top if it and it.get("name")], reverse=True)
    old = run_ids[keep:]
    if not old:
        return

    def list_all_files(folder: str) -> list[str]:
        """Retourne tous les fichiers sous folder (récursif), avec chemins complets."""
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
            # Supabase Storage: si metadata contient "metadata" ou "id", c'est fichier,
            # sinon c'est souvent un "folder". On tente récursif de toute façon.
            # Heuristique: si name contient un point, c’est un fichier probable.
            if "." in name:
                out.append(full)
            else:
                out.extend(list_all_files(full))
        return out

    for rid in old:
        root = f"{prefix}/{rid}"
        paths = list_all_files(root)
        if paths:
            try:
                sb.storage.from_(bucket).remove(paths)
            except Exception:
                pass


def get_latest_snapshot_run_id(
    sb,
    bucket: str,
    runs_prefix: str = "runs",
) -> Optional[str]:
    """
    Retourne le run_id le plus récent dans bucket/runs/<run_id>/...
    (utilisé par runner pour lire le dernier snapshot)
    """
    bucket = (bucket or "").strip()
    runs_prefix = (runs_prefix or "runs").strip().strip("/")
    if not bucket:
        return None

    try:
        items = sb.storage.from_(bucket).list(runs_prefix) or []
    except Exception:
        return None

    run_ids = sorted(
        [it.get("name") for it in items if it and it.get("name")],
        reverse=True,
    )
    return run_ids[0] if run_ids else None

