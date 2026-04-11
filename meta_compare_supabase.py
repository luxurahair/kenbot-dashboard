#!/usr/bin/env python3
import os, csv, re
from typing import Any, Dict, Optional, List
from urllib.parse import urlsplit, urlunsplit

from dotenv import load_dotenv
load_dotenv()

import requests
from bs4 import BeautifulSoup

from supabase_db import get_client, upload_bytes_to_storage, utc_now_iso

TIMEOUT = 25
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 (KenBot meta-vs-site supabase)"})

OUTPUTS_BUCKET = os.getenv("SB_BUCKET_OUTPUTS", "kennebec-outputs").strip()
META_FEED_PATH = os.getenv("KENBOT_META_FEED_PATH", "feeds/meta_vehicle.csv").strip()
REPORT_PATH = os.getenv("KENBOT_META_REPORT_PATH", "reports/meta_vs_site.csv").strip()

BASE_URL = (os.getenv("KENBOT_BASE_URL") or "https://www.kennebecdodge.ca").strip().rstrip("/")


def norm_url(u: str) -> str:
    u = (u or "").strip()
    if not u:
        return ""
    try:
        p = urlsplit(u)
        scheme = (p.scheme or "https").lower()
        netloc = p.netloc.lower()
        path = re.sub(r"/+$", "", p.path or "")
        return urlunsplit((scheme, netloc, path, "", ""))
    except Exception:
        return u.strip()


def _to_int(s: str) -> Optional[int]:
    s = (s or "").strip()
    if not s:
        return None
    digits = "".join(ch for ch in s if ch.isdigit())
    return int(digits) if digits else None


def load_meta_feed_from_storage(sb) -> List[Dict[str, Any]]:
    blob = sb.storage.from_(OUTPUTS_BUCKET).download(META_FEED_PATH)
    txt = blob.decode("utf-8", errors="replace")
    r = csv.DictReader(txt.splitlines())
    rows: List[Dict[str, Any]] = []
    for row in r:
        rows.append({(k or "").strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()})
    return rows


def fetch_site_price(url: str) -> Optional[int]:
    url = norm_url(url)
    if not url:
        return None
    try:
        r = SESSION.get(url, timeout=TIMEOUT)
        if not r.ok:
            return None
        html = r.text or ""
    except Exception:
        return None

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    m = re.search(r"(\d[\d\s]{2,})\s*\$", text)
    if m:
        return _to_int(m.group(1))

    m2 = re.search(r"\b(\d{2,3}\s?\d{3})\b", text)
    if m2:
        return _to_int(m2.group(1))

    return None


def main():
    sb = get_client()

    meta_rows = load_meta_feed_from_storage(sb)
    if not meta_rows:
        raise RuntimeError(f"Meta feed empty: {OUTPUTS_BUCKET}/{META_FEED_PATH}")

    out_rows: List[Dict[str, Any]] = []
    checked = 0

    for row in meta_rows:
        stock = (row.get("id") or row.get("stock") or "").strip().upper()
        link = norm_url(row.get("link") or row.get("url") or "")
        meta_price = _to_int(row.get("price") or "")

        if not stock or not link:
            continue

        checked += 1
        site_price = fetch_site_price(link)

        status = "OK"
        if site_price is None:
            status = "MISSING_ON_SITE"
        elif meta_price is None:
            status = "META_PRICE_MISSING"
        elif meta_price != site_price:
            status = "PRICE_MISMATCH"

        out_rows.append({
            "ts": utc_now_iso(),
            "stock": stock,
            "link": link,
            "meta_price_int": meta_price,
            "site_price_int": site_price,
            "status": status,
        })

    fieldnames = ["ts", "stock", "link", "meta_price_int", "site_price_int", "status"]
    lines = [",".join(fieldnames)]

    def esc(x):
        s = "" if x is None else str(x)
        s = s.replace('"', '""')
        return f'"{s}"' if ("," in s or "\n" in s) else s

    for r in out_rows:
        lines.append(",".join(esc(r.get(k)) for k in fieldnames))

    report_csv = "\n".join(lines) + "\n"

    upload_bytes_to_storage(
        sb,
        OUTPUTS_BUCKET,
        REPORT_PATH,
        report_csv.encode("utf-8"),
        content_type="text/csv; charset=utf-8",
        upsert=True,
    )

    print(f"✅ Report uploaded -> {OUTPUTS_BUCKET}/{REPORT_PATH} (rows={len(out_rows)}, checked={checked})")

def meta_compare():
    return main()
    
if __name__ == "__main__":
    main()
