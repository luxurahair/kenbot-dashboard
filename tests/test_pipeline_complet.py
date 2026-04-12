#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_pipeline_complet.py

Programme de test du pipeline complet:
1. Extraction VIN depuis le titre / VIN
2. Detection Stellantis 2018+
3. Decodage VIN via NHTSA
4. Extraction options sticker PDF (si dispo en local ou URL)
5. Build ad text (ad_builder)
6. Footer + lien Window Sticker
7. Humanisation IA (si OPENAI_API_KEY dispo)
8. Detection no_photo
9. Pipeline _build_ad_text complet (dry run)

Usage:
    python test_pipeline_complet.py
    python test_pipeline_complet.py --vin ZACPDFDWXR3A18931
    python test_pipeline_complet.py --with-ai   # teste aussi OpenAI
"""

import os
import sys
import re
import json
import time
import tempfile
import traceback
from pathlib import Path
from typing import Dict, Any, List, Optional

# Ajouter le repertoire racine au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================
# RESULTATS
# ============================================================
RESULTS: List[Dict[str, Any]] = []
PASS = 0
FAIL = 0
SKIP = 0


def test(name: str, passed: bool, detail: str = ""):
    global PASS, FAIL
    status = "PASS" if passed else "FAIL"
    if passed:
        PASS += 1
    else:
        FAIL += 1
    icon = "\u2705" if passed else "\u274c"
    RESULTS.append({"name": name, "status": status, "detail": detail})
    print(f"  {icon} {name}" + (f"  ({detail})" if detail else ""))


def skip(name: str, reason: str = ""):
    global SKIP
    SKIP += 1
    RESULTS.append({"name": name, "status": "SKIP", "detail": reason})
    print(f"  \u23ed  {name}  (SKIP: {reason})")


def section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


# ============================================================
# 1. VIN YEAR EXTRACTION
# ============================================================
_VIN_YEAR_MAP = {
    "J": 2018, "K": 2019, "L": 2020, "M": 2021,
    "N": 2022, "P": 2023, "R": 2024, "S": 2025, "T": 2026,
    "A": 2010, "B": 2011, "C": 2012, "D": 2013,
    "E": 2014, "F": 2015, "G": 2016, "H": 2017,
}


def _extract_year(v: Dict[str, Any]) -> int:
    title = (v.get("title") or "").strip()
    m = re.search(r"\b(20[12]\d)\b", title)
    if m:
        return int(m.group(1))
    vin = (v.get("vin") or "").strip().upper()
    if len(vin) >= 10:
        yr_char = vin[9]
        if yr_char in _VIN_YEAR_MAP:
            return _VIN_YEAR_MAP[yr_char]
    return 0


def _is_stellantis_vin(vin: str) -> bool:
    vin = (vin or "").strip().upper()
    return len(vin) == 17 and vin.startswith(("1C", "2C", "3C", "ZAC", "ZFA"))


def _is_stellantis_2018_plus(v: Dict[str, Any]) -> bool:
    vin = (v.get("vin") or "").strip().upper()
    if not _is_stellantis_vin(vin):
        return False
    year = _extract_year(v)
    return year >= 2018


def test_vin_detection():
    section("1. DETECTION VIN + ANNEE + STELLANTIS")

    cases = [
        # (title, vin, expected_year, expected_stellantis, expected_2018plus)
        ("Dodge Hornet R/T Plus 2024", "ZACPDFDWXR3A18931", 2024, True, True),
        ("Dodge Hornet GT 2023", "ZACNDFAN6P3A03259", 2023, True, True),
        ("Dodge Challenger SRT Hellcat 2021", "2C3CDZC91MH665365", 2021, True, True),
        ("Ram 1500 Classic SLT 2023", "3C6RR7LT2PG663255", 2023, True, True),
        ("Ram 1500 Tradesman 2021", "1C6RRFCG9MN663396", 2021, True, True),
        ("Jeep Wrangler Rubicon 4XE 2024", "1C4JXAN7RW1363440", 2024, True, True),
        ("Chrysler 300 2017", "2C3CCAAB9HN123456", 2017, True, False),
        ("Toyota Corolla 2022", "2T1BURHE5NC123456", 2022, False, False),
        ("Ford Mustang GT 2022", "1FA6P8CF1N5107904", 2022, False, False),
        ("Ferrari 488 GTB 2017", "ZFF79ALA0H0230000", 2017, False, False),
        ("Plymouth Satellite 1969", "RM23H9A123456XXXX", 0, False, False),  # VIN pre-1981, year=0 attendu
    ]

    for title, vin, exp_year, exp_stell, exp_2018 in cases:
        v = {"title": title, "vin": vin}
        year = _extract_year(v)
        is_stell = _is_stellantis_vin(vin)
        is_2018 = _is_stellantis_2018_plus(v)

        test(
            f"Year: {title[:35]}",
            year == exp_year,
            f"got={year} exp={exp_year}"
        )
        test(
            f"Stellantis: {title[:35]}",
            is_stell == exp_stell,
            f"got={is_stell} exp={exp_stell}"
        )
        test(
            f"2018+: {title[:35]}",
            is_2018 == exp_2018,
            f"got={is_2018} exp={exp_2018}"
        )


# ============================================================
# 2. VIN DECODER (NHTSA)
# ============================================================
def test_vin_decoder():
    section("2. DECODAGE VIN VIA NHTSA")

    try:
        from vin_decoder import decode_vin, format_specs_for_prompt, format_engine_line
    except ImportError:
        skip("Import vin_decoder", "Module non disponible")
        return

    # Test avec un vrai VIN Hornet R/T Plus 2024
    test_vins = [
        ("ZACPDFDWXR3A18931", "Hornet R/T Plus 2024", "Dodge", "Hornet"),
        ("2C3CDZC91MH665365", "Challenger SRT Hellcat 2021", "Dodge", "Challenger"),
        ("1C6RRFCG9MN663396", "Ram 1500 Tradesman 2021", "Ram", "1500"),
    ]

    for vin, desc, exp_make, exp_model in test_vins:
        specs = decode_vin(vin)
        if specs is None:
            skip(f"NHTSA decode {desc}", "API timeout ou erreur")
            continue

        test(
            f"NHTSA decode {desc}",
            bool(specs),
            f"make={specs.get('make')} model={specs.get('model')}"
        )

        make = (specs.get("make") or "").lower()
        test(
            f"  Make = {exp_make}",
            exp_make.lower() in make,
            f"got='{specs.get('make')}'"
        )

        # Specs pour prompt
        prompt_text = format_specs_for_prompt(specs)
        test(
            f"  Prompt text non vide",
            len(prompt_text) > 20,
            f"{len(prompt_text)} chars"
        )

        # Verification moteur
        engine = format_engine_line(specs)
        test(
            f"  Engine line non vide",
            len(engine) > 5,
            f"'{engine}'"
        )

        print(f"    [Specs] {prompt_text[:120]}...")


# ============================================================
# 3. STICKER PDF EXTRACTION
# ============================================================
def test_sticker_extraction():
    section("3. EXTRACTION OPTIONS STICKER PDF")

    try:
        from sticker_to_ad import extract_spans_pdfminer, extract_option_groups_from_spans
        from ad_builder import build_ad as build_ad_from_options
    except ImportError as e:
        skip("Import sticker_to_ad / ad_builder", str(e))
        return

    # Tester si on peut telecharger un PDF Hornet depuis Chrysler.com
    import requests as req

    test_vin = "ZACPDFDWXR3A18931"  # Hornet R/T Plus 2024
    pdf_url = f"https://www.chrysler.com/hostd/windowsticker/getWindowStickerPdf.do?vin={test_vin}"

    print(f"  Telechargement PDF: {pdf_url[:70]}...")

    pdf_bytes = None
    try:
        r = req.get(pdf_url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        if r.status_code == 200 and r.content and r.content.lstrip().startswith(b"%PDF"):
            pdf_bytes = r.content
            test("PDF telecharge (Hornet R/T Plus 2024)", True, f"{len(pdf_bytes)} bytes")
        else:
            test("PDF telecharge", False, f"status={r.status_code} size={len(r.content or b'')}")
    except Exception as e:
        skip("PDF telecharge", f"Erreur: {e}")

    if not pdf_bytes:
        skip("Extraction options", "Pas de PDF disponible")
        return

    # Ecrire le PDF dans un fichier temporaire
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp = f.name

        # Extraction spans
        spans = extract_spans_pdfminer(tmp)
        test(
            "Extraction spans PDFMiner",
            spans is not None and len(spans) > 0,
            f"{len(spans or [])} spans"
        )

        if not spans:
            skip("Extraction groupes", "Pas de spans")
            return

        # Extraction groupes d'options
        groups = extract_option_groups_from_spans(spans)
        test(
            "Extraction groupes d'options",
            groups is not None and len(groups) > 0,
            f"{len(groups or [])} groupes"
        )

        if not groups:
            return

        # Afficher les groupes
        for i, g in enumerate(groups[:5]):
            title = g.get("title", "")
            details = g.get("details", [])
            print(f"    Groupe {i+1}: {title} ({len(details)} sous-options)")

        # Build ad
        ad_text = build_ad_from_options(
            title="Dodge Hornet R/T Plus 2024",
            price="42 995 $",
            mileage="18 234 km",
            stock="44057A",
            vin=test_vin,
            options=groups,
            vehicle_url="https://www.kennebecdodge.ca/fr/inventaire-occasion/dodge-hornet-r-t-plus-2024-44057a",
        )

        test("build_ad retourne du texte", len(ad_text) > 200, f"{len(ad_text)} chars")

        # ============================================================
        # 4. VERIFICATIONS STRUCTURELLES
        # ============================================================
        section("4. VERIFICATIONS STRUCTURE ANNONCE STELLANTIS")

        # Titre
        test("Titre present", "\U0001f525" in ad_text, "emoji feu")

        # Prix
        test("Prix present", "42 995 $" in ad_text or "42995" in ad_text)

        # Stock
        test("Stock present", "44057A" in ad_text)

        # Options ✅
        checkmark_count = ad_text.count("\u2705")
        test("Options \u2705 presentes", checkmark_count > 0, f"{checkmark_count} options principales")

        # Sous-options ▫️
        subopt_count = ad_text.count("\u25ab\ufe0f")
        test("Sous-options \u25ab\ufe0f presentes", subopt_count > 0, f"{subopt_count} sous-options")

        # Structure: ✅ en MAJUSCULES?
        lines = ad_text.split("\n")
        checkmark_lines = [l for l in lines if "\u2705" in l]
        upper_count = 0
        for cl in checkmark_lines:
            # Extraire le texte apres ✅
            after = cl.split("\u2705", 1)[-1].strip()
            if after and after == after.upper():
                upper_count += 1
        # Au moins la moitie devrait etre en majuscules
        if checkmark_lines:
            test(
                "Options \u2705 en MAJUSCULES",
                upper_count >= len(checkmark_lines) * 0.5,
                f"{upper_count}/{len(checkmark_lines)} en majuscules"
            )

        # Lien Window Sticker
        sticker_link = f"https://www.chrysler.com/hostd/windowsticker/getWindowStickerPdf.do?vin={test_vin}"
        test("Lien Window Sticker present", sticker_link in ad_text)

        # "Le reste des details est dans le Window Sticker"
        test("Mention Window Sticker", "window sticker" in ad_text.lower() or "Window Sticker" in ad_text)

        # Echanges
        test("Section echanges", "change" in ad_text.lower() or "echange" in ad_text.lower())

        # Pas de prix d'options (BLACKLIST)
        from ad_builder import BLACKLIST_TERMS
        for term in ["MSRP", "DESTINATION", "FEDERAL", "TAXE"]:
            test(f"Blacklist: pas de '{term}'", term not in ad_text.upper())

        # Afficher le texte complet
        print(f"\n{'~'*60}")
        print("ANNONCE GENEREE (sticker brut):")
        print(f"{'~'*60}")
        # Limiter l'affichage
        if len(ad_text) > 2000:
            print(ad_text[:2000] + "\n... [tronque]")
        else:
            print(ad_text)

    finally:
        if tmp:
            try:
                os.remove(tmp)
            except Exception:
                pass


# ============================================================
# 5. FOOTER
# ============================================================
def test_footer():
    section("5. FOOTER DANIEL GIROUX")

    from footer_utils import has_footer, add_footer_if_missing, count_footer_occurrences

    text_no_footer = "\U0001f525 RAM 1500 2022 \U0001f525\n\n\U0001f4a5 34 995 $ \U0001f4a5"
    test("Texte sans footer detecte", not has_footer(text_no_footer))

    text_with = text_no_footer + "\n\n\U0001f4de Daniel Giroux \u2014 418-222-3939"
    test("Texte avec footer detecte", has_footer(text_with))

    result = add_footer_if_missing(text_no_footer)
    test("Footer ajoute si absent", has_footer(result))
    test("Pas de double footer", count_footer_occurrences(result) == 1)

    result2 = add_footer_if_missing(result)
    test("Pas de triple footer", count_footer_occurrences(result2) == 1)

    # Footer dans une annonce sticker
    from ad_builder import build_ad as build_ad_from_options
    ad = build_ad_from_options(
        title="Test", price="30000", mileage="50000",
        stock="12345", vin="1C4JXAN7RW1363441",
        options=[{"title": "GROUP A", "details": ["opt1", "opt2"]}],
    )
    sticker_link = "chrysler.com/hostd/windowsticker"
    test("Annonce sticker contient lien sticker", sticker_link in ad.lower() or "windowsticker" in ad.lower())


# ============================================================
# 6. HUMANISATION IA (optionnel)
# ============================================================
def test_ai_humanization():
    section("6. HUMANISATION IA (OpenAI)")

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        skip("Humanisation IA", "OPENAI_API_KEY non defini")
        return

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except ImportError:
        skip("Import OpenAI", "pip install openai")
        return

    # Texte brut sticker a humaniser
    raw_text = """🔥 Dodge Hornet R/T Plus 2024 🔥

💥 42 995 $ 💥
📊 Kilometres : 18 234 km
🧾 Stock : 44057A

✨ ACCESSOIRES OPTIONNELS (Window Sticker)

✅  HORNET R/T PLUS
        ▫️ 1.3L Turbo Engine with 268HP
        ▫️ 6-Speed Automatic Transmission
        ▫️ All-Wheel Drive

✅  SAFETY & SECURITY GROUP
        ▫️ Blind Spot Monitoring
        ▫️ Rear Cross Path Detection
        ▫️ Lane Departure Warning

📌 Le reste des details est dans le Window Sticker :

https://www.chrysler.com/hostd/windowsticker/getWindowStickerPdf.do?vin=ZACPDFDWXR3A18931

📞 Daniel Giroux — 418-222-3939
#DanielGiroux #Beauce #Quebec"""

    system_msg = (
        "Tu es Daniel Giroux, vendeur passionne chez Kennebec Dodge Chrysler a Saint-Georges.\n"
        "Humanise cette annonce:\n"
        "1. INTRO: 3-4 phrases percutantes, quebecoises\n"
        "2. TITRE: plus vendeur\n"
        "3. OPTIONS: ✅ MAJUSCULES humanisees, ▫️ minuscules\n"
        "4. NE SUPPRIME AUCUNE LIGNE ✅ ou ▫️\n"
        "5. Footer = COPIE EXACTE\n"
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": f"Humanise:\n\n{raw_text}"},
            ],
            temperature=0.8,
            max_tokens=2000,
        )
        humanized = response.choices[0].message.content.strip()

        test("IA retourne du texte", len(humanized) > 200, f"{len(humanized)} chars")

        # Verifications post-humanisation
        test("Footer preserve (418-222-3939)", "418-222-3939" in humanized)
        test("Options ✅ preservees", humanized.count("\u2705") >= 2, f"{humanized.count(chr(0x2705))} ✅")
        test("Sous-options ▫️ preservees", humanized.count("\u25ab\ufe0f") >= 2, f"{humanized.count(chr(0x25ab) + chr(0xfe0f))} ▫️")
        test("Lien sticker preserve", "windowsticker" in humanized.lower())
        test("Hashtag #DanielGiroux", "#DanielGiroux" in humanized)

        # Anti-vulgarite
        vulgar = ["couilles", "balls", "badass", "bitch", "merde", "crisse", "tabarnac", "fuck"]
        has_vulgar = any(v in humanized.lower() for v in vulgar)
        test("Pas de vulgarite", not has_vulgar)

        # Anti-cliches
        cliches = ["sillonner", "dominer", "routes de la beauce"]
        has_cliche = any(c in humanized.lower() for c in cliches)
        test("Pas de cliches interdits", not has_cliche)

        print(f"\n{'~'*60}")
        print("ANNONCE HUMANISEE (AI):")
        print(f"{'~'*60}")
        if len(humanized) > 2000:
            print(humanized[:2000] + "\n... [tronque]")
        else:
            print(humanized)

    except Exception as e:
        test("Appel OpenAI", False, str(e))


# ============================================================
# 7. NO_PHOTO DETECTION
# ============================================================
def test_no_photo():
    section("7. DETECTION NO_PHOTO (FB vs KENNEBEC)")

    from pathlib import Path

    # _is_no_photo_fallback
    real_photos = [Path("/tmp/test_06174_01.jpg"), Path("/tmp/test_06174_02.jpg")]
    no_photo = [Path("/tmp/test_06174_NO_PHOTO.jpg")]
    empty = []

    def _is_no_photo_fallback(photos):
        if not photos:
            return False
        if len(photos) == 1 and "NO_PHOTO" in photos[0].name:
            return True
        return False

    test("Vraies photos = pas fallback", not _is_no_photo_fallback(real_photos))
    test("NO_PHOTO = fallback detecte", _is_no_photo_fallback(no_photo))
    test("Vide = pas fallback", not _is_no_photo_fallback(empty))

    # ── Nouvelle logique: FB vs Kennebec ──
    def simulate_photos_added(post_data, kennebec_photos):
        """Simule la detection PHOTOS_ADDED comme dans runner_cron_prod.py"""
        nb_kennebec = len(kennebec_photos)
        if nb_kennebec == 0:
            return False, "no_kennebec_photos"

        photo_count_db = post_data.get("photo_count", None)
        has_no_photo_flag = post_data.get("no_photo", None)

        # Methode 5: FB photos <= 1 ET Kennebec > 1
        if isinstance(photo_count_db, int) and photo_count_db <= 1 and nb_kennebec > 1:
            return True, "FB_VS_KENNEBEC"

        # Methode 1: Flag no_photo
        if has_no_photo_flag is True:
            return True, "NO_PHOTO_FLAG"

        # Methode 2: Text hints
        base_text = (post_data.get("base_text") or "").lower()
        if "photos suivront" in base_text or "sans photo" in base_text:
            return True, "TEXT_HINT"

        return False, "no_match"

    # Cas 1: FB a 1 photo, Kennebec a 25 → TRIGGER
    triggered, method = simulate_photos_added(
        {"photo_count": 1, "no_photo": False, "base_text": "Annonce normale"},
        [f"photo_{i}.jpg" for i in range(25)]
    )
    test("FB=1 photo, Kennebec=25 → TRIGGER", triggered, f"method={method}")

    # Cas 2: FB a 0 photos, Kennebec a 30 → TRIGGER
    triggered, method = simulate_photos_added(
        {"photo_count": 0, "no_photo": False, "base_text": "Annonce"},
        [f"photo_{i}.jpg" for i in range(30)]
    )
    test("FB=0 photos, Kennebec=30 → TRIGGER", triggered, f"method={method}")

    # Cas 3: FB a 15 photos, Kennebec a 25 → PAS de trigger
    triggered, method = simulate_photos_added(
        {"photo_count": 15, "no_photo": False, "base_text": "Annonce complete"},
        [f"photo_{i}.jpg" for i in range(25)]
    )
    test("FB=15 photos, Kennebec=25 → PAS de trigger", not triggered, f"method={method}")

    # Cas 4: no_photo=True, Kennebec a des photos → TRIGGER
    triggered, method = simulate_photos_added(
        {"photo_count": 0, "no_photo": True, "base_text": "Photos suivront"},
        [f"photo_{i}.jpg" for i in range(20)]
    )
    test("no_photo=True + photos dispo → TRIGGER", triggered, f"method={method}")

    # Cas 5: Kennebec a 0 photos → PAS de trigger
    triggered, method = simulate_photos_added(
        {"photo_count": 0, "no_photo": True, "base_text": "Sans photo"},
        []
    )
    test("Kennebec=0 → PAS de trigger", not triggered, f"method={method}")

    # Cas 6: Text hint "photos suivront" + photos dispo → TRIGGER
    triggered, method = simulate_photos_added(
        {"photo_count": None, "no_photo": None, "base_text": "Photos suivront bientot"},
        [f"photo_{i}.jpg" for i in range(10)]
    )
    test("Text hint + photos dispo → TRIGGER", triggered, f"method={method}")

    # Cas 7: FB a 10 photos, Kennebec a 10 → PAS de trigger
    triggered, method = simulate_photos_added(
        {"photo_count": 10, "no_photo": False, "base_text": "Belle annonce"},
        [f"photo_{i}.jpg" for i in range(10)]
    )
    test("FB=10, Kennebec=10 → PAS de trigger", not triggered, f"method={method}")


# ============================================================
# 8. PIPELINE COMPLET (integration)
# ============================================================
def test_full_pipeline():
    section("8. PIPELINE COMPLET (integration)")

    try:
        from vin_decoder import decode_vin, format_specs_for_prompt
        from ad_builder import build_ad as build_ad_from_options
        from footer_utils import add_footer_if_missing, has_footer
    except ImportError as e:
        skip("Import modules", str(e))
        return

    # Vehicule test: Hornet R/T Plus 2024
    v = {
        "title": "Dodge Hornet R/T Plus 2024",
        "vin": "ZACPDFDWXR3A18931",
        "stock": "44057A",
        "price_int": 42995,
        "km_int": 18234,
        "url": "https://www.kennebecdodge.ca/fr/inventaire-occasion/dodge-hornet-r-t-plus-2024-44057a",
        "photos": [f"https://example.com/photo_{i}.jpg" for i in range(1, 30)],
    }

    vin = v["vin"]

    # Etape 1: Detection
    test("Pipeline: Stellantis detecte", _is_stellantis_vin(vin))
    test("Pipeline: 2018+ detecte", _is_stellantis_2018_plus(v))
    test("Pipeline: Annee = 2024", _extract_year(v) == 2024)

    # Etape 2: VIN decode
    specs = decode_vin(vin)
    if specs:
        test("Pipeline: VIN decode OK", bool(specs))
        vin_text = format_specs_for_prompt(specs)
        test("Pipeline: Specs texte", len(vin_text) > 20, f"{len(vin_text)} chars")
    else:
        skip("Pipeline: VIN decode", "NHTSA indisponible")
        vin_text = ""

    # Etape 3: Sticker PDF (si possible)
    import requests as req
    pdf_url = f"https://www.chrysler.com/hostd/windowsticker/getWindowStickerPdf.do?vin={vin}"

    sticker_text = ""
    options = []
    try:
        r = req.get(pdf_url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        if r.status_code == 200 and r.content and r.content.lstrip().startswith(b"%PDF"):
            from sticker_to_ad import extract_spans_pdfminer, extract_option_groups_from_spans

            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                f.write(r.content)
                tmp = f.name

            try:
                spans = extract_spans_pdfminer(tmp) or []
                options = extract_option_groups_from_spans(spans) or []
            finally:
                os.remove(tmp)

            if options:
                sticker_text = build_ad_from_options(
                    title=v["title"],
                    price=f"{v['price_int']} $",
                    mileage=f"{v['km_int']} km",
                    stock=v["stock"],
                    vin=vin,
                    options=options,
                    vehicle_url=v["url"],
                )
                test("Pipeline: Sticker PDF extrait", True, f"{len(options)} groupes, {len(sticker_text)} chars")
            else:
                test("Pipeline: Sticker PDF extrait", False, "0 groupes d'options")
        else:
            skip("Pipeline: Sticker PDF", f"HTTP {r.status_code}")
    except Exception as e:
        skip("Pipeline: Sticker PDF", str(e))

    # Etape 4: Footer
    if sticker_text:
        final = add_footer_if_missing(sticker_text)
        test("Pipeline: Footer ajoute", has_footer(final))

        # Verifier lien sticker dans le texte final
        test(
            "Pipeline: Lien Window Sticker dans annonce",
            f"windowsticker/getWindowStickerPdf.do?vin={vin}" in final
        )

        # Verifier structure ✅/▫️
        test("Pipeline: Options ✅", final.count("\u2705") >= 1)
        test("Pipeline: Sous-options ▫️", final.count("\u25ab\ufe0f") >= 1)

    # Resume
    section("RESUME PIPELINE")
    print(f"  VIN:         {vin}")
    print(f"  Stellantis:  {_is_stellantis_vin(vin)}")
    print(f"  2018+:       {_is_stellantis_2018_plus(v)}")
    print(f"  Annee:       {_extract_year(v)}")
    print(f"  VIN decode:  {'OK' if specs else 'FAIL'}")
    print(f"  Sticker PDF: {'OK' if sticker_text else 'NON DISPO'}")
    print(f"  Options:     {len(options)} groupes")
    print(f"  Texte:       {len(sticker_text)} chars")
    if vin_text:
        print(f"  Specs NHTSA: {vin_text[:100]}...")


# ============================================================
# MAIN
# ============================================================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--vin", default=None, help="VIN specifique a tester")
    parser.add_argument("--with-ai", action="store_true", help="Tester aussi OpenAI")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  TEST PIPELINE COMPLET — KENBOT STICKER + IA + FOOTER")
    print("=" * 70)

    start = time.time()

    test_vin_detection()
    test_vin_decoder()
    test_sticker_extraction()
    test_footer()
    test_no_photo()
    test_full_pipeline()

    if args.with_ai:
        test_ai_humanization()
    else:
        section("6. HUMANISATION IA (OpenAI)")
        skip("Humanisation IA", "Utilise --with-ai pour activer")

    elapsed = time.time() - start

    # ============================================================
    # BILAN
    # ============================================================
    section(f"BILAN FINAL ({elapsed:.1f}s)")
    total = PASS + FAIL + SKIP
    print(f"  \u2705 PASS:  {PASS}")
    print(f"  \u274c FAIL:  {FAIL}")
    print(f"  \u23ed  SKIP:  {SKIP}")
    print(f"  Total:    {total}")
    print()

    if FAIL == 0:
        print("  \U0001f389 TOUS LES TESTS PASSENT!")
    else:
        print(f"  \u26a0\ufe0f  {FAIL} TESTS EN ECHEC:")
        for r in RESULTS:
            if r["status"] == "FAIL":
                print(f"     \u274c {r['name']}: {r['detail']}")

    # Sauvegarder le rapport
    report_path = "/app/test_reports/pipeline_test.json"
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": round(elapsed, 1),
            "pass": PASS,
            "fail": FAIL,
            "skip": SKIP,
            "results": RESULTS,
        }, f, indent=2, ensure_ascii=False)
    print(f"\n  Rapport: {report_path}")

    sys.exit(1 if FAIL > 0 else 0)
