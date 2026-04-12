#!/usr/bin/env python3
"""
test_sold_unsold_logic.py — Test de la logique SOLD / UNSOLD / PRICE_CHANGED par stock

Simule le cron avec des données fictives et vérifie que:
1. Un véhicule sur Kennebec n'est JAMAIS marqué VENDU (même si slug change)
2. Un véhicule marqué VENDU par erreur est restauré (UNSOLD)
3. Le changement de prix se détecte par stock, pas par slug
4. PHOTOS_ADDED se détecte par stock
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

PASS = 0
FAIL = 0

def test(name, passed, detail=""):
    global PASS, FAIL
    if passed:
        PASS += 1
        print(f"  \u2705 {name}" + (f"  ({detail})" if detail else ""))
    else:
        FAIL += 1
        print(f"  \u274c {name}" + (f"  ({detail})" if detail else ""))


def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ============================================================
# Simuler les données
# ============================================================

# Kennebec scrape actuel (source de vérité)
current = {
    "ford-mustang-gt-noir-2022-06208": {
        "stock": "06208", "title": "Ford Mustang GT Noir 2022",
        "vin": "1FA6P8CF1N5107904", "price_int": 42995, "photos": [f"p{i}.jpg" for i in range(25)],
    },
    "dodge-hornet-r-t-plus-2024-44057a": {
        "stock": "44057A", "title": "Dodge Hornet R/T Plus 2024",
        "vin": "ZACPDFDWXR3A18931", "price_int": 42995, "photos": [f"p{i}.jpg" for i in range(30)],
    },
    "ram-1500-classic-slt-2023-06174": {
        "stock": "06174", "title": "Ram 1500 Classic SLT 2023",
        "vin": "3C6RR7LT2PG663255", "price_int": 39995, "photos": [f"p{i}.jpg" for i in range(20)],
    },
    "jeep-grand-cherokee-2019-46020a": {
        "stock": "46020A", "title": "Jeep Grand Cherokee 2019",
        "vin": "1C4RJFBG0GC458289", "price_int": 29995, "photos": [f"p{i}.jpg" for i in range(15)],
    },
}

# Inventory DB (ancien scrape) — le slug de la Mustang a changé!
inv_db = {
    "ford-mustang-gt-2022-06208": {  # ANCIEN slug (sans "noir")
        "stock": "06208", "price_int": 42995,
    },
    "dodge-hornet-r-t-plus-2024-44057a": {
        "stock": "44057A", "price_int": 44995,  # PRIX A CHANGÉ (44995 → 42995)
    },
    "ram-1500-classic-slt-2023-06174": {
        "stock": "06174", "price_int": 39995,
    },
}

# Posts DB (posts Facebook)
posts_db = {
    "ford-mustang-gt-2022-06208": {  # ANCIEN slug — marqué SOLD par erreur!
        "stock": "06208", "post_id": "820789524460241_1111", "status": "SOLD",
        "base_text": "\U0001f525 Ford Mustang GT 2022 \U0001f525\n\nBelle bête!",
        "published_at": "2026-04-01T00:00:00Z", "photo_count": 10,
    },
    "dodge-hornet-r-t-plus-2024-44057a": {
        "stock": "44057A", "post_id": "820789524460241_2222", "status": "ACTIVE",
        "base_text": "Hornet RT Plus", "published_at": "2026-04-10T00:00:00Z", "photo_count": 15,
    },
    "ram-1500-classic-slt-2023-06174": {
        "stock": "06174", "post_id": "820789524460241_3333", "status": "ACTIVE",
        "base_text": "Ram 1500", "published_at": "2026-04-09T00:00:00Z", "photo_count": 1,  # NO PHOTO!
    },
    "chevrolet-corvette-2020-99999": {  # Vraiment vendu (pas sur Kennebec)
        "stock": "99999", "post_id": "820789524460241_4444", "status": "ACTIVE",
        "base_text": "Corvette", "published_at": "2026-03-01T00:00:00Z", "photo_count": 20,
    },
}


# ============================================================
# Simuler la logique du cron
# ============================================================

# INDEX PAR STOCK
current_by_stock = {}
for slug, v in current.items():
    st = (v.get("stock") or "").strip().upper()
    if st:
        current_by_stock[st] = {**v, "_slug": slug}

inv_db_by_stock = {}
for slug, v in inv_db.items():
    st = (v.get("stock") or "").strip().upper()
    if st:
        inv_db_by_stock[st] = {**v, "_slug": slug}

posts_db_by_stock = {}
for slug, v in posts_db.items():
    st = (v.get("stock") or "").strip().upper()
    if st:
        posts_db_by_stock[st] = {**v, "_slug": slug}

current_stocks = set(current_by_stock.keys())

PRICE_CHANGE_THRESHOLD = 200

# ============================================================
# TEST 1: PRICE_CHANGED par stock
# ============================================================
section("1. PRICE_CHANGED par stock")

price_changed = []
for stock in (current_stocks & set(inv_db_by_stock.keys())):
    old = inv_db_by_stock.get(stock) or {}
    new = current_by_stock.get(stock) or {}
    old_p = old.get("price_int")
    new_p = new.get("price_int")
    if isinstance(old_p, int) and isinstance(new_p, int):
        if abs(old_p - new_p) > PRICE_CHANGE_THRESHOLD:
            new_slug = new.get("_slug", "")
            if new_slug:
                price_changed.append(new_slug)

test("Hornet prix changé (44995→42995)", "dodge-hornet-r-t-plus-2024-44057a" in price_changed,
     f"diff=2000 > seuil={PRICE_CHANGE_THRESHOLD}")
test("Mustang prix PAS changé", "ford-mustang" not in str(price_changed))
test("Ram prix PAS changé", "ram-1500" not in str(price_changed))


# ============================================================
# TEST 2: PHOTOS_ADDED par stock
# ============================================================
section("2. PHOTOS_ADDED par stock")

photos_added = []
for stock in (current_stocks & set(posts_db_by_stock.keys())):
    post_data = posts_db_by_stock.get(stock) or {}
    v = current_by_stock.get(stock) or {}
    slug = v.get("_slug") or post_data.get("_slug") or ""
    nb_kennebec = len(v.get("photos") or [])
    photo_count_db = post_data.get("photo_count")

    if isinstance(photo_count_db, int) and photo_count_db <= 1 and nb_kennebec > 1:
        photos_added.append(slug)

test("Ram photo_count=1, Kennebec=20 → TRIGGER",
     "ram-1500-classic-slt-2023-06174" in photos_added)
test("Hornet photo_count=15, Kennebec=30 → PAS de trigger",
     "dodge-hornet" not in str(photos_added))


# ============================================================
# TEST 3: SOLD vérifie par stock
# ============================================================
section("3. SOLD — Vérification par stock")

sold_slugs = []
posts_in_db_not_in_site = set(posts_db.keys()) - set(current.keys())
for slug in posts_in_db_not_in_site:
    post_data = posts_db.get(slug) or {}
    post_status = (post_data.get("status") or "").upper()
    post_id = (post_data.get("post_id") or "").strip()
    if post_status == "SOLD" or not post_id:
        continue
    post_stock = (post_data.get("stock") or "").strip().upper()
    if post_stock and post_stock in current_stocks:
        # BLOQUÉ — stock encore sur Kennebec
        continue
    sold_slugs.append(slug)

test("Mustang slug changé MAIS stock 06208 sur Kennebec → PAS VENDU",
     "ford-mustang-gt-2022-06208" not in sold_slugs,
     "stock 06208 trouvé dans current_stocks")
test("Corvette stock 99999 PAS sur Kennebec → VENDU",
     "chevrolet-corvette-2020-99999" in sold_slugs)


# ============================================================
# TEST 4: UNSOLD — Restaurer faux VENDU
# ============================================================
section("4. UNSOLD — Restaurer faux VENDU")

unsold_slugs = []
for stock in current_stocks:
    post_data = posts_db_by_stock.get(stock)
    if not post_data:
        continue
    post_status = (post_data.get("status") or "").upper()
    post_id = (post_data.get("post_id") or "").strip()
    post_slug = post_data.get("_slug") or ""
    if post_status == "SOLD" and post_id and post_slug:
        unsold_slugs.append(post_slug)

test("Mustang marquée SOLD + stock sur Kennebec → UNSOLD",
     "ford-mustang-gt-2022-06208" in unsold_slugs,
     "sera restaurée comme ACTIVE")
test("Hornet ACTIVE → PAS dans UNSOLD",
     "dodge-hornet" not in str(unsold_slugs))


# ============================================================
# TEST 5: Ordre des targets
# ============================================================
section("5. Ordre des targets (UNSOLD en premier)")

targets = (
    [(s, "UNSOLD") for s in unsold_slugs]
    + [(s, "PHOTOS_ADDED") for s in photos_added]
    + [(s, "PRICE_CHANGED") for s in price_changed]
    + [(s, "SOLD") for s in sold_slugs]
)

if targets:
    test("Premier target = UNSOLD", targets[0][1] == "UNSOLD",
         f"target[0]={targets[0]}")
    test("UNSOLD avant SOLD", 
         [t[1] for t in targets].index("UNSOLD") < [t[1] for t in targets].index("SOLD"))


# ============================================================
# BILAN
# ============================================================
section(f"BILAN")
print(f"  Kennebec stocks: {sorted(current_stocks)}")
print(f"  PRICE_CHANGED: {price_changed}")
print(f"  PHOTOS_ADDED: {photos_added}")
print(f"  SOLD: {sold_slugs}")
print(f"  UNSOLD: {unsold_slugs}")
print(f"  Targets: {[(s.split('-')[-1], e) for s, e in targets]}")
print()
total = PASS + FAIL
print(f"  \u2705 PASS: {PASS}")
print(f"  \u274c FAIL: {FAIL}")
if FAIL == 0:
    print(f"\n  \U0001f389 TOUS LES TESTS PASSENT!")
else:
    print(f"\n  \u26a0\ufe0f {FAIL} TESTS EN ÉCHEC")

sys.exit(1 if FAIL > 0 else 0)
