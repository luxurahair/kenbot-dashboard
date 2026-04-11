import os
import requests
from dotenv import load_dotenv

from supabase_db import get_client, get_inventory_map
from kennebec_scrape import fetch_html, parse_inventory_listing_urls, parse_vehicle_detail_simple

load_dotenv()

BASE_URL = (os.getenv("KENBOT_BASE_URL") or "https://www.kennebecdodge.ca").rstrip("/")
INVENTORY_PATH = os.getenv("KENBOT_INVENTORY_PATH") or "/fr/inventaire-occasion/"
PAGES = int(os.getenv("KENBOT_PAGES") or "3")

def main():
    sb = get_client()
    inv_db = get_inventory_map(sb)

    # SOLD en DB
    sold_by_stock = {}
    for slug, r in inv_db.items():
        if (r.get("status") or "").upper() != "SOLD":
            continue
        st = (r.get("stock") or "").strip().upper()
        if st:
            sold_by_stock.setdefault(st, []).append(slug)

    # Stocks actuels en ligne (scrape)
    s = requests.Session()
    current_stocks = set()

    for page_no in range(1, PAGES + 1):
        page_url = f"{BASE_URL}{INVENTORY_PATH}"
        if page_no > 1:
            page_url = f"{page_url}?page={page_no}"

        html = fetch_html(s, page_url)
        urls = parse_inventory_listing_urls(BASE_URL, INVENTORY_PATH, html)

        for url in urls:
            d = parse_vehicle_detail_simple(s, url)
            st = (d.get("stock") or "").strip().upper()
            if st:
                current_stocks.add(st)

    ghosts = sorted(set(sold_by_stock.keys()) & current_stocks)

    print(f"BASE_URL={BASE_URL}")
    print(f"INVENTORY_PATH={INVENTORY_PATH} pages={PAGES}")
    print(f"SOLD in DB: {len(sold_by_stock)} | current online stocks: {len(current_stocks)}")
    print(f"👻 GHOST SOLD STOCKS: {len(ghosts)}")

    for st in ghosts[:80]:
        print(f"- {st}  slugs_sold={sold_by_stock[st]}")

if __name__ == "__main__":
    main()
