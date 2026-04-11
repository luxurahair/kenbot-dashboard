#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
sticker_to_ad.py
- Extrait les OPTIONS (Window Sticker PDF) pour enrichir une annonce Facebook
- Sources:
  - Prix/KM/Titre: viennent du site Kennebec (passés via args --price/--mileage/--title)
  - Sticker: options + VIN (fallback) + titre (fallback si pas fourni)
- Parsing:
  - PDFMiner spans (layout) -> groupage PRIX à droite + détails indentés
  - Fallback texte brut (pdfminer extract_text)
  - Dernier recours OCR (poppler + tesseract)
- Ne pas afficher les prix des options (on s'en sert pour parser seulement)
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

# ---------- PDF text extraction (pdfminer) ----------
from pdfminer.high_level import extract_pages
from pdfminer.high_level import extract_text as pdfminer_extract_text
from pdfminer.layout import LTTextContainer, LTChar, LTAnno

# ---------- Optional: decrypt PDFs ----------
try:
    import pikepdf  # type: ignore
except Exception:
    pikepdf = None

# ---------- OCR fallback ----------
try:
    import pytesseract  # type: ignore
    from PIL import Image  # type: ignore
except Exception:
    pytesseract = None
    Image = None


# ------------------------------
# Data structures
# ------------------------------

@dataclass
class Span:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    bold_ratio: float  # 0..1


# ------------------------------
# Helpers
# ------------------------------

def normalize(s: str) -> str:
    s = (s or "").replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def is_price_token(s: str) -> bool:
    s = normalize(s)
    # accepte $ collé, après, etc.
    return bool(re.search(r"(\$\s*)?\b\d[\d\s.,]*\b\s*\$?", s))


def extract_price(s: str) -> Optional[str]:
    s = normalize(s)
    # capture 595, 2,395, 2 395, 2,395.00 etc.
    m = re.search(r"(?i)(?:\$\s*)?(\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{2})?)\s*\$?", s)
    if not m:
        return None
    raw = normalize(m.group(1)).replace(" ", "")
    return f"{raw} $" if raw else None


def looks_like_junk(s: str) -> bool:
    if not s:
        return True

    low = s.lower()
    low = (low
       .replace("’", "'")
       .replace("−", "-")
       .replace("–", "-")
       .replace("\u00a0", " ")
)

    banned = (
        "année modèle",
        "annee modele",
        "prix de base",
        "prix total",
        "p.d.s.f",
        "pdsf",
        "préparation",
        "preparation",
        "frais d'expédition",
        "frais d expedition",
        "destination",
        "destination charge",
        "freight",
        "shipping",
        "energuide",
        "consommation",
        "annual fuel cost",
        "coût annuel",
        "cout annuel",
        "garantie",
        "assistance routière",
        "assistance routiere",
        "transférable",
        "transferable",
        "motopropulseur",
        "fca canada",
        "ce véhicule est fabriqué",
        "ce vehicule est fabrique",
        "vehicles.nrcan",
        "vehicules.nrcan",
        "indice",
        "smog",
        "carbon",
        "tailpipe",
        "government of canada",
        "visitez le site web",
        "contactez",
        "pour de plus amples renseignements",
        "manufacturer's suggested retail price",
        "suggested retail price",
        "msrp",
        "tariff adjustment",
        "total price",
        "base price",
        "destination charge",
        "freight charge",
        "destination charge",
        "tariff adjustment",
        "federal a/c excise tax",
        "frais d’expédition",
        "taxe d’accise",
        "taxe d'accise",
        "federal a c excise tax",  # OCR parfois enlève le slash)
    )
    if any(b in low for b in banned):
        return True

    if "http" in low or "www." in low:
        return True

    # trop long = souvent paragraphe
    if len(s) > 90:
        return True

    return False


def detect_hybrid_from_text(txt: str) -> bool:
    t = (txt or "").lower()
    return any(k in t for k in (
        "phev",
        "plug-in",
        "plug in",
        "plug-in hybrid",
        "hybrid",
        "hybride",
        "vehicule hybride",
        "véhicule hybride",
        "vehicule hybride rechargeable",
        "véhicule hybride rechargeable",
        "vhr",
        "plug–in hybrid vehicle",
        "plug-in hybrid vehicle",
    ))


def is_hard_stop_detail(t: str) -> bool:
    """
    Stop net quand on arrive dans le bas du sticker (dealer/shipped/sold).
    FR + EN.
    """
    low = (t or "").lower().strip()

    stop_phrases = (
        # FR
        "le concessionnaire",
        "peut vendre moins cher",
        "expedier a", "expédier à",
        "expedie a", "expédié à",
        "vendu a", "vendu à",
        "par le concessionnaire",
        # EN
        "the dealer",
        "may sell for less",
        "shipped to",
        "sold to",
        "by dealer",
    )

    if low == "s.l.":
        return True

    return any(k in low for k in stop_phrases)


def extract_vin_from_text(txt: str) -> str:
    """
    Cherche un VIN même s'il est écrit avec des séparateurs (ex: 1C6—RR7LG5NS—241151).
    Retourne 17 caractères alphanum (sans I/O/Q).
    """
    if not txt:
        return ""

    t = (txt or "").upper()

    m = re.search(r"\b([A-HJ-NPR-Z0-9]{17})\b", t)
    if m:
        return m.group(1)

    m2 = re.search(
        r"\b([A-HJ-NPR-Z0-9]{3,6})\s*[-–—]\s*([A-HJ-NPR-Z0-9]{4,8})\s*[-–—]\s*([A-HJ-NPR-Z0-9]{3,8})\b",
        t,
    )
    if m2:
        cand = (m2.group(1) + m2.group(2) + m2.group(3))
        cand = re.sub(r"[^A-Z0-9]", "", cand)
        if len(cand) == 17 and not re.search(r"[IOQ]", cand):
            return cand

    blob = re.sub(r"[^A-Z0-9\-–—\s]", " ", t)
    blob = re.sub(r"\s+", " ", blob).strip()
    compact = re.sub(r"[\s\-–—]", "", blob)

    for i in range(0, max(0, len(compact) - 16)):
        win = compact[i: i + 17]
        if re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", win) and not re.search(r"[IOQ]", win):
            return win

    return ""


def clean_option_line(s: str) -> str:
    s = normalize(s)
    s = re.sub(r"\bwww\.[^\s]+", "", s, flags=re.I).strip()
    s = re.sub(r"\s{2,}", " ", s).strip()
    return s


def choose_hashtags(title: str) -> str:
    t = (title or "").lower()

    # Toujours présents
    BASE_TAGS = [
        "#Beauce", "#SaintGeorges", "#Quebec",
        "#AutoUsagée", "#VehiculeOccasion",
        "#DanielGiroux"
    ]

    # Marque -> intention
    BRAND_TAGS = {
        "ram": ["#RAM", "#Truck", "#Pickup"],
        "jeep": ["#Jeep", "#4x4", "#SUV"],
        "dodge": ["#Dodge", "#Performance"],
        "chrysler": ["#Chrysler", "#Familiale"],
        "alfa": ["#AlfaRomeo", "#Performance"],
    }

    # Modèle -> précision marketing
    MODEL_TAGS = {
        # Dodge
        "hornet": ["#Hornet", "#SUV", "#Performance"],
        "challenger": ["#Challenger", "#MuscleCar"],
        "charger": ["#Charger", "#MuscleCar"],
        "durango": ["#Durango", "#SUV"],

        # RAM
        "promaster": ["#ProMaster", "#Cargo", "#Van"],
        "1500": ["#RAM1500", "#Pickup"],
        "2500": ["#RAM2500", "#HeavyDuty"],

        # Jeep
        "wagoneer": ["#Wagoneer", "#SUV", "#4x4"],
        "wrangler": ["#Wrangler", "#OffRoad", "#4x4"],
        "grand cherokee": ["#GrandCherokee", "#LuxurySUV", "#4x4"],
        "gladiator": ["#Gladiator", "#Pickup4x4"],
    }

    # Variantes / mots-clés
    VARIANT_TAGS = {
        "r/t": ["#RT"],
        " rt ": ["#RT"],  # aide quand "RT" est séparé
        "plus": ["#Plus"],
        "hybrid": ["#Hybride"],
        "plug-in": ["#HybrideRechargeable"],
        "phev": ["#HybrideRechargeable"],
        "awd": ["#AWD"],
        "4x4": ["#4x4"],
        "4wd": ["#4x4"],
        "v8": ["#V8"],
    }

    tags = []

    # 1) Marque (première qui match)
    for brand, btags in BRAND_TAGS.items():
        if brand in t:
            tags.extend(btags)
            break

    # 2) Modèle (peut en matcher plusieurs)
    for model, mtags in MODEL_TAGS.items():
        if model in t:
            tags.extend(mtags)

    # 3) Variantes
    for key, vtags in VARIANT_TAGS.items():
        if key in t:
            tags.extend(vtags)

    # 4) Base
    tags.extend(BASE_TAGS)

    # 5) Dédoublonnage + limite
    out, seen = [], set()
    for x in tags:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            out.append(x)

    return " ".join(out[:18])


# ------------------------------
# PDF decrypt (optional)
# ------------------------------

def maybe_decrypt_pdf(in_pdf: Path) -> Path:
    if not pikepdf:
        return in_pdf
    try:
        with pikepdf.open(str(in_pdf), allow_overwriting_input=False) as pdf:
            out = Path(tempfile.gettempdir()) / (in_pdf.stem + "_unlocked.pdf")
            pdf.save(str(out))
            return out
    except Exception:
        return in_pdf


# ------------------------------
# PDF miner spans extraction
# ------------------------------

def extract_spans_pdfminer(pdf_path: Path, max_pages: int = 2) -> List[Span]:
    spans: List[Span] = []
    pages = 0

    def iter_objs(obj):
        if isinstance(obj, (LTChar, LTAnno)):
            yield obj
            return
        try:
            for x in obj:
                yield x
        except TypeError:
            yield obj

    for page_layout in extract_pages(str(pdf_path)):
        pages += 1

        for element in page_layout:
            if not isinstance(element, LTTextContainer):
                continue

            for text_line in element:
                chars: List[LTChar] = []
                txt_parts: List[str] = []
                x0 = y0 = float("inf")
                x1 = y1 = float("-inf")

                for obj in iter_objs(text_line):
                    if isinstance(obj, LTChar):
                        chars.append(obj)
                        txt_parts.append(obj.get_text())
                        x0 = min(x0, obj.x0)
                        y0 = min(y0, obj.y0)
                        x1 = max(x1, obj.x1)
                        y1 = max(y1, obj.y1)
                    elif isinstance(obj, LTAnno):
                        txt_parts.append(obj.get_text())

                text = normalize("".join(txt_parts))
                if not text:
                    continue

                bold = 0
                for c in chars:
                    fname = (getattr(c, "fontname", "") or "").lower()
                    if any(k in fname for k in ("bold", "black", "demi", "heavy", "semibold")):
                        bold += 1
                bold_ratio = (bold / len(chars)) if chars else 0.0

                spans.append(
                    Span(
                        text=text,
                        x0=x0 if x0 != float("inf") else 0.0,
                        y0=y0 if y0 != float("inf") else 0.0,
                        x1=x1 if x1 != float("-inf") else 0.0,
                        y1=y1 if y1 != float("-inf") else 0.0,
                        bold_ratio=bold_ratio,
                    )
                )

        if pages >= max_pages:
            break

    return spans


# ------------------------------
# Big title extraction (best effort)
# ------------------------------

def extract_big_title(spans: List[Span]) -> Optional[str]:
    """
    Titre = plus gros texte (hauteur bbox) en haut du sticker.
    Regroupe d'abord les spans par ligne (Y proche), puis prend la ligne
    la plus "grosse" (y1-y0) dans le haut de page, en filtrant MSRP/prix/etc.
    """
    if not spans:
        return None

    Y_LINE_TOL = 3.0
    sps = sorted(spans, key=lambda sp: (-sp.y0, sp.x0))

    lines: List[Dict[str, Any]] = []
    for sp in sps:
        txt = normalize(sp.text)
        if not txt:
            continue

        placed = False
        for ln in lines:
            if abs(ln["y0"] - sp.y0) <= Y_LINE_TOL:
                ln["parts"].append(sp)
                ln["y0"] = max(ln["y0"], sp.y0)
                ln["y1"] = max(ln["y1"], sp.y1)
                ln["x0"] = min(ln["x0"], sp.x0)
                ln["x1"] = max(ln["x1"], sp.x1)
                placed = True
                break

        if not placed:
            lines.append({"parts": [sp], "x0": sp.x0, "x1": sp.x1, "y0": sp.y0, "y1": sp.y1})

    def line_text(ln) -> str:
        parts = sorted(ln["parts"], key=lambda sp: sp.x0)
        return normalize(" ".join(p.text for p in parts))

    def line_bold_ratio(ln) -> float:
        parts = ln["parts"]
        if not parts:
            return 0.0
        return sum(p.bold_ratio for p in parts) / len(parts)

    max_y = max(sp.y1 for sp in spans)
    top_cut = max_y * 0.70

    BAD = (
        "année modèle", "annee modele",
        "manufacturer's suggested retail price", "suggested retail price", "msrp",
        "p.d.s.f", "pdsf",
        "prix de base", "prix total",
        "destination", "destination charge",
        "frais d'expédition", "frais d expedition",
    )

    cands: List[Tuple[float, str]] = []
    for ln in lines:
        if ln["y1"] < top_cut:
            continue

        txt = line_text(ln)
        if not txt:
            continue
        low = txt.lower()
        if any(b in low for b in BAD):
            continue
        if not (8 <= len(txt) <= 90):
            continue

        br = line_bold_ratio(ln)
        h = ln["y1"] - ln["y0"]
        score = (h * 100.0) + (br * 10.0) + min(len(txt), 70) * 0.1
        cands.append((score, txt))

    if not cands:
        return None

    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


# ------------------------------
# OCR fallback (optional)
# ------------------------------

def ocr_extract_text(pdf_path: Path) -> str:
    if not pytesseract or not Image:
        return ""

    import subprocess

    tmpdir = Path(tempfile.mkdtemp(prefix="sticker_ocr_"))
    outprefix = tmpdir / "page"
    cmd = ["pdftoppm", "-f", "1", "-l", "2", "-png", str(pdf_path), str(outprefix)]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return ""

    # concat simple des pages dispo
    texts = []
    for img in (tmpdir / "page-1.png", tmpdir / "page-2.png"):
        if not img.exists():
            continue
        try:
            im = Image.open(img)
            texts.append(pytesseract.image_to_string(im, lang="fra+eng") or "")
        except Exception:
            pass
    return "\n".join(texts).strip()


def extract_option_groups_from_ocr(text: str) -> List[Dict[str, Any]]:
    """
    OCR fallback: construit des groupes.
    Titres = lignes qui contiennent un prix (utilisé comme ancre).
    Détails = lignes suivantes sans prix (souvent indentées).
    """
    lines_raw = (text or "").splitlines()

    def indent_level(s: str) -> int:
        return len(s) - len(s.lstrip(" "))

    lines = [(normalize(x), indent_level(x)) for x in lines_raw]
    lines = [(t, ind) for (t, ind) in lines if t]

    price_re = re.compile(r"(?i)(?:\$\s*)?(\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{2})?)\s*\$?")

    # ✅ titres qu'on ne veut JAMAIS voir comme options
    banned_titles = (
        "destination charge",
        "freight",
        "freight charge",
        "shipping",
        "tariff adjustment",
        "msrp",
        "manufacturer's suggested retail price",
        "suggested retail price",
        "p.d.s.f", "pdsf",
        "prix total",
        "total price",
        "prix de base",
        "base price",
        "federal a/c excise tax",
        "federal a c excise tax",  # OCR enlève souvent le slash
    )

    groups: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for (ln, ind) in lines:
        if is_hard_stop_detail(ln):
            break

        m = price_re.search(ln)
        if m:
            p = extract_price(ln)

            title = price_re.sub("", ln).strip(" -–:•\t")
            title = clean_option_line(title)

            # ❌ skip titres vides / junk / prix-only / banned
            if not title:
                continue
            if looks_like_junk(title):
                continue
            # prix-only (ex: "$2,395")
            if extract_price(title) and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", title)) < 2:
                continue
            lowt = title.lower()
            if any(b in lowt for b in banned_titles):
                continue

            if current:
                groups.append(current)
            current = {"title": title, "price": p, "details": []}
            continue

        # détails
        if current:
            d = clean_option_line(ln)
            if not d:
                continue
            if looks_like_junk(d):
                continue
            # skip prix-only en détail
            if extract_price(d) and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", d)) < 2:
                continue
            # si pas indenté et trop long, on skip (souvent du texte de bas de page)
            if ind < 2 and len(d) > 80:
                continue
            if d.lower() != current["title"].lower():
                current["details"].append(d)

    if current:
        groups.append(current)

    # dédoublonne titres
    final, seen = [], set()
    for g in groups:
        k = (g.get("title") or "").lower().strip()
        if k and k not in seen:
            seen.add(k)
            final.append(g)

    return final[:12]


# ------------------------------
# Brand filter
# ------------------------------

def is_allowed_stellantis_brand(txt: str) -> bool:
    low = (txt or "").lower()
    allowed = ("ram", "dodge", "jeep", "chrysler", "alfa", "alfaromeo", "alfa romeo")
    return any(a in low for a in allowed)


# ------------------------------
# Ad builder (NEVER show option prices)
# ------------------------------

def build_ad(
    title: str,
    price: str,
    mileage: str,
    stock: str,
    vin: str,
    options: List[Dict[str, Any]],
    is_hybrid: bool = False,
    dealer: str = "Kennebec Dodge Chrysler — Saint-Georges (Beauce)",
    year: str = "",
    transmission: str = "",
    drivetrain: str = "",
) -> str:

    lines: List[str] = []

    title = (title or "").strip()

    # --- Titre ---
    lines.append(f"🔥 {title} 🔥")
    lines.append("")

    # --- Infos clés (site Kennebec) ---
    if price:
        lines.append(f"💥 {price} 💥")
    if mileage:
        lines.append(f"📊 Kilométrage : {mileage}")

    # 📍 Concession
    if dealer:
        lines.append(f"📍 {dealer}")

    lines.append("")

    # ✅ HYBRIDE / PHEV (détecté depuis le sticker)
    if is_hybrid:
        lines.append("⚡ Véhicule hybride rechargeable (PHEV)")
        lines.append("")

    # 🚗 DÉTAILS (Kennebec)
    details: List[str] = []
    if stock:
        details.append(f"✅ Inventaire : {stock}")
    if year:
        details.append(f"✅ Année : {year}")
    if vin:
        details.append(f"✅ VIN : {vin}")
    if transmission:
        details.append(f"✅ Transmission : {transmission}")
    if drivetrain:
        details.append(f"✅ Entraînement : {drivetrain}")

    if details:
        lines.append("🚗 DÉTAILS")
        lines.extend(details)
        lines.append("")

    # --- Accessoires ---
    if options:
        lines.append("✨ ACCESSOIRES OPTIONNELS (Window Sticker)")
        lines.append("")

        for g in options:
            t = (g.get("title") or "").strip()
            details2 = g.get("details") or []
            if not t:
                continue

            # ✅ on n'affiche JAMAIS le prix sticker
            lines.append(f"✅  {t}")

            for d in details2[:12]:
                dd = (d or "").strip()
                if not dd:
                    continue
                if looks_like_junk(dd):
                    continue
                # skip prix-only
                if extract_price(dd) and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", dd)) < 2:
                    continue
                lines.append(f"        ▫️ {dd}")

        lines.append("")
        lines.append("📌 Le reste des détails est dans le Window Sticker :")
        lines.append("")
        if vin:
            lines.append(f"https://www.chrysler.com/hostd/windowsticker/getWindowStickerPdf.do?vin={vin}")
        else:
            lines.append("(VIN introuvable — ajoute --vin pour générer le lien)")
        lines.append("")

    # NOTE: Footer retiré pour éviter les doublons.
    # Le footer sera ajouté par runner via footer_utils.add_footer_if_missing()

    return "\n".join(lines).strip() + "\n"


# ------------------------------
# Options extraction (groups from spans) — FR+EN anchors, price-driven grouping
# ------------------------------

def extract_option_groups_from_spans(spans: List[Span]) -> List[Dict[str, Any]]:
    if not spans:
        return []

    def is_junk_detail(t: str) -> bool:
        low = (t or "").lower().strip()
        if looks_like_junk(t):
            return True
        if re.fullmatch(r"[\d\s\-–—]+", t or ""):
            return True
        if any(k in low for k in ("expedier", "vendu", "concessionnaire", "dealer", "shipped", "sold")):
            return True
        return False

    # Anchor FR + EN
    ANCHORS = ("ACCESSOIRES OPTIONNELS", "OPTIONAL EQUIPMENT")
    anchors = [sp for sp in spans if any(a in (sp.text or "").upper() for a in ANCHORS)]
    if not anchors:
        return []

    anchor = max(anchors, key=lambda sp: sp.y0)
    anchor_y = anchor.y0

    RIGHT_TEXT_MIN_X = 250
    RIGHT_TEXT_MAX_X = 445
    PRICE_MIN_X = 445

    DETAIL_INDENT_X = 315

    right_text: List[Span] = []
    prices: List[Tuple[float, str]] = []

    for sp in spans:
        if sp.y0 > anchor_y:
            continue

        t = clean_option_line(sp.text)
        if not t:
            continue

        if RIGHT_TEXT_MIN_X <= sp.x0 <= RIGHT_TEXT_MAX_X:
            if not looks_like_junk(t):
                right_text.append(sp)

        if sp.x0 >= PRICE_MIN_X and is_price_token(sp.text):
            p = extract_price(sp.text)
            if p:
                prices.append((sp.y0, p))

    right_text.sort(key=lambda s: s.y0, reverse=True)

    def nearest_price(y: float, tol: float = 6.0) -> Optional[str]:
        best = None
        best_dy = 9999.0
        for py, p in prices:
            dy = abs(py - y)
            if dy < best_dy:
                best_dy = dy
                best = p
        return best if best is not None and best_dy <= tol else None

    groups: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for sp in right_text:
        text = clean_option_line(sp.text)
        if not text:
            continue

        # ✅ (2) skip lignes "prix seulement" (ex: "$2,395" ou "2,395 $")
        if extract_price(text) and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", text)) < 2:
            continue

        # ✅ (2) skip lignes junk (TOTAL PRICE, MSRP, etc.)
        if looks_like_junk(text):
            continue

        up = text.upper()
        if any(a in up for a in ANCHORS):
            continue

        if is_hard_stop_detail(text):
            break

        p = nearest_price(sp.y0)
        is_detail_by_indent = sp.x0 >= DETAIL_INDENT_X

        # PRIX aligné -> TITRE (même si pas bold)
        if p is not None:
            # ✅ (3) refuser un "titre" qui est juste un prix
            if extract_price(text) and len(re.sub(r"[^A-Za-zÀ-ÿ]", "", text)) < 2:
                continue
            # ✅ (3) refuser titres junk
            if looks_like_junk(text):
                continue

            if current:
                groups.append(current)
            current = {"title": text, "price": p, "details": []}
            continue

        # sinon détail
        if current:
            if is_junk_detail(text):
                continue
            if (not is_detail_by_indent) and len(text) > 70:
                continue
            if text.lower() != (current.get("title") or "").lower():
                current["details"].append(text)

    if current:
        groups.append(current)

    cleaned: List[Dict[str, Any]] = []

    BAN_TITLES = (
     "destination charge",
     "tariff adjustment",
     "federal a/c excise tax",
     "federal a c excise tax",
     "federal a c excise tax",
 )

    for g in groups:
        opt_title = (g.get("title") or "").strip()
        if not opt_title:
            continue

        lowt = opt_title.lower()
        up = opt_title.upper()

        if "TAXE ACCISE" in up:
            continue
        if any(x in lowt for x in BAN_TITLES):
            continue
        if looks_like_junk(opt_title):
            continue

        cleaned.append(g)

    return cleaned[:12]


# ------------------------------
# Options extraction (text fallback) — FR+EN anchor
# ------------------------------

def extract_paid_options_from_text(txt: str) -> List[str]:
    """
    Fallback texte brut:
    - repère ACCESSOIRES OPTIONNELS / OPTIONAL EQUIPMENT
    - collecte labels (sans $) et prix (ligne prix)
    - associe (zip)
    """
    raw_lines = (txt or "").splitlines()
    lines = [re.sub(r"\s+", " ", l).strip() for l in raw_lines]

    money_re = re.compile(r"(?i)(?:\$\s*)?(\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{2})?)\s*\$?")
    price_only_re = re.compile(r"(?i)^\s*(?:\$\s*)?(\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{2})?)\s*\$?\s*$")

    def is_price_only(line: str) -> Optional[str]:
        m = price_only_re.match(line or "")
        if not m:
            return None
        raw = normalize(m.group(1)).replace(" ", "")
        return f"{raw} $" if raw else None

    def is_stop(line: str) -> bool:
        return is_hard_stop_detail(line)

    start_idx = None
    for i, l in enumerate(lines):
        u = (l or "").upper()
        if ("ACCESSOIRES OPTIONNELS" in u) or ("OPTIONAL EQUIPMENT" in u):
            start_idx = i
            break
    if start_idx is None:
        return []

    labels: List[str] = []
    prices: List[str] = []

    for j in range(start_idx + 1, len(lines)):
        l = (lines[j] or "").strip()
        if not l:
            continue
        if is_stop(l):
            break

        p = is_price_only(l)
        if p:
            prices.append(p)
            continue

        if money_re.search(l):
            continue

        cand = clean_option_line(l)
        if not cand or looks_like_junk(cand):
            continue
        labels.append(cand)

    keep_prefixes = (
        "ENSEMBLE", "ATTELAGE", "COMMANDE", "TAPIS", "ESSIEU", "PNEU", "PNEUS",
        "CROCHETS", "PLAQUE", "AJOUT", "TAXE", "SUPPORT", "SIEGE", "SIÈGE", "PRISE",
        "BANQUETTE", "BANQ", "DIFFERENTIEL", "DIFF", "GROUP", "PACKAGE", "MOPAR",
        "CLASS", "CARGO", "SAFETY", "PREMIUM", "CUSTOMER",
    )

    filtered_labels = []
    for lb in labels:
        up = lb.upper()
        if up.startswith(keep_prefixes):
            filtered_labels.append(lb)

    use_labels = filtered_labels if filtered_labels else labels

    n = min(len(use_labels), len(prices))
    out = [f"{use_labels[i]} ({prices[i]})" for i in range(n)]

    final, seen = [], set()
    for x in out:
        k = x.lower()
        if k not in seen:
            seen.add(k)
            final.append(x)

    return final[:12]


# ------------------------------
# Main
# ------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="Chemin vers le window sticker PDF")
    ap.add_argument("--out", default="/tmp/output_stickers", help="Dossier de sortie OU chemin .txt")
    ap.add_argument("--title", default="", help="Titre affiché de l'annonce (idéalement du site Kennebec)")
    ap.add_argument("--price", default="", help="Prix (vient du site Kennebec)")
    ap.add_argument("--mileage", default="", help="Kilométrage (vient du site Kennebec)")
    ap.add_argument("--stock", default="", help="Numéro d'inventaire (ex: 06213)")
    ap.add_argument("--vin", default="", help="VIN (optionnel, sinon auto-extrait)")
    ap.add_argument("--url", default="", help="(Optionnel) URL fiche - ignorée volontairement")

    # ✅ NOUVEAUX CHAMPS (viennent de KenBot)
    ap.add_argument("--dealer", default="Kennebec Dodge Chrysler — Saint-Georges (Beauce)", help="Concession (Kennebec)")
    ap.add_argument("--year", default="", help="Année (vient de Kennebec)")
    ap.add_argument("--transmission", default="", help="Transmission (vient de Kennebec)")
    ap.add_argument("--drivetrain", default="", help="Entraînement (vient de Kennebec)")

    args = ap.parse_args()

    if not args.price.strip() or not args.mileage.strip():
        print("⛔ Prix/KM manquants: ils doivent venir du site Kennebec (passes --price et --mileage).", file=sys.stderr)
        # return 2


    pdf_path = Path(args.pdf).expanduser()
    if not pdf_path.exists():
        print(f"PDF introuvable: {pdf_path}", file=sys.stderr)
        return 2

    unlocked = maybe_decrypt_pdf(pdf_path)

    # spans (coords) -> 2 pages
    spans = extract_spans_pdfminer(unlocked, max_pages=2)

    # texte brut fallback -> 2 pages
    page_txt = pdfminer_extract_text(str(unlocked), maxpages=2) or ""
    is_hybrid = detect_hybrid_from_text(page_txt)

    # filtre marque (Stellantis)
    if page_txt.strip() and not is_allowed_stellantis_brand(page_txt):
        print("⛔ Sticker ignoré: marque hors RAM/Dodge/Jeep/Chrysler/Alfa Romeo.")
        return 0

    # VIN (auto si pas fourni)
    auto_vin = extract_vin_from_text(page_txt)
    vin = args.vin.strip() or auto_vin

    # Stock (sert aussi à fallback titre si besoin)
    auto_stock = pdf_path.parent.name or pdf_path.stem
    stock = re.sub(r"\s+", "", (args.stock.strip() or auto_stock).strip()) or pdf_path.stem

    # Titre: priorité au site, sinon "gros titre" pdf, sinon stock
    auto_title = extract_big_title(spans) or ""
    title = args.title.strip() or auto_title or stock or pdf_path.stem

    # options groups via spans
    groups = extract_option_groups_from_spans(spans)

    # fallback texte (si groups vide)
    if not groups and page_txt.strip():
        flat = extract_paid_options_from_text(page_txt)
        groups = [{"title": x, "price": None, "details": []} for x in flat]

    # fallback OCR (dernier recours)
    if not groups:
        ocr_txt = ocr_extract_text(unlocked)
        if ocr_txt:
            groups = extract_option_groups_from_ocr(ocr_txt)

    # Annonce
    ad = build_ad(
    title=title,
    price=args.price.strip(),
    mileage=args.mileage.strip(),
    stock=stock,
    vin=vin,
    options=groups,
    is_hybrid=is_hybrid,
    dealer=args.dealer.strip(),
    year=args.year.strip(),
    transmission=args.transmission.strip(),
    drivetrain=args.drivetrain.strip(),
)

    out_target = Path(args.out).expanduser()
    if out_target.suffix.lower() == ".txt":
        out_path = out_target
        out_dir = out_path.parent
    else:
        out_dir = out_target
        out_path = out_dir / f"{stock}_facebook.txt"

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(ad, encoding="utf-8")
    print(f"Écrit: {out_path}")

    if not groups:
        print("⚠️ Aucun accessoire optionnel détecté (parseur à ajuster pour ce format).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
