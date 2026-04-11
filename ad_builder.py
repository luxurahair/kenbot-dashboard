#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ad_builder.py
from __future__ import annotations

import re
from typing import Any, Dict, List

# -----------------------------
# Blacklist (Window Sticker)
# -----------------------------
BLACKLIST_TERMS = (
    "ECOPRELEVEMENT", "ECO PRELEVEMENT", "ECO-PRÉLÈVEMENT", "ÉCOPRÉLÈVEMENT", "ECOPRÉLÈVEMENT",
    "FEDERAL", "FÉDÉRAL",
    "TAX", "TAXE",
    "FEE", "FRAIS",
    "LEVY", "PRÉLÈVEMENT", "PRELEVEMENT",
    "DESTINATION", "EXPEDITION", "EXPÉDITION",
    "MSRP", "PRIX TOTAL", "TOTAL PRICE",
)

def is_blacklisted_line(s: str) -> bool:
    if not s:
        return True
    u = s.upper()
    return any(t in u for t in BLACKLIST_TERMS)


# -----------------------------
# Hashtags / Marques
# -----------------------------
def choose_hashtags(title: str) -> str:
    base = [
        "#VehiculeOccasion", "#AutoUsagée", "#Quebec", "#Beauce",
        "#SaintGeorges", "#KennebecDodge", "#DanielGiroux"
    ]
    low = (title or "").lower()
    if "ram" in low:
        base.insert(0, "#RAM")
    if "jeep" in low:
        base.insert(0, "#Jeep")
    if "dodge" in low:
        base.insert(0, "#Dodge")
    if "chrysler" in low:
        base.insert(0, "#Chrysler")

    out: List[str] = []
    seen = set()
    for t in base:
        k = t.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return " ".join(out)


def is_allowed_stellantis_brand(txt: str) -> bool:
    low = (txt or "").lower()
    allowed = (
        "ram", "dodge", "jeep", "chrysler",
        "alfa", "alfaromeo", "alfa romeo",
        "fiat", "wagoneer"
    )
    return any(a in low for a in allowed)


# -----------------------------
# Normalisation Prix / KM
# -----------------------------
def _digits_only(s: str) -> str:
    return re.sub(r"[^\d]", "", s or "")


def _fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def normalize_price(price: str) -> str:
    """
    Accepte:
      "33995", "33 995", "33,995", "33 995 $", "CAD 33995"
    Retour:
      "33 995 $"
    """
    raw = (price or "").strip()
    if not raw:
        return ""

    digits = _digits_only(raw)
    if not digits:
        return ""

    try:
        n = int(digits)
    except Exception:
        return ""

    # garde-fou anti-n'importe-quoi
    if n < 1000 or n > 500000:
        return ""

    return f"{_fmt_int(n)} $"


def normalize_km(mileage: str) -> str:
    """
    Sort TOUJOURS "xx xxx km"
    Supporte miles -> km si le texte contient mi/miles/mile.
    """
    raw = (mileage or "").strip().lower()
    if not raw:
        return ""

    digits = _digits_only(raw)
    if not digits:
        return ""

    try:
        n = int(digits)
    except Exception:
        return ""

    if n < 0 or n > 600000:
        return ""

    is_miles = (" mi" in raw) or raw.endswith("mi") or ("miles" in raw) or ("mile" in raw)
    if is_miles:
        n = int(round(n * 1.60934))

    return f"{_fmt_int(n)} km"


# -----------------------------
# Builder final (texte prêt à publier)
# -----------------------------
def build_ad(
    title: str,
    price: str,
    mileage: str,
    stock: str,
    vin: str,
    options: List[Dict[str, Any]],
    *,
    vehicle_url: str = "",
) -> str:
    lines: List[str] = []

    t = (title or "").strip()
    s = (stock or "").strip().upper()
    v = (vin or "").strip().upper()

    p = normalize_price(price)
    m = normalize_km(mileage)

    # --- Titre ---
    if t:
        lines.append(f"🔥 {t} 🔥")
        lines.append("")

    # --- Infos clés ---
    if p:
        lines.append(f"💥 {p} 💥")
    if m:
        lines.append(f"📊 Kilométrage : {m}")
    if s:
        lines.append(f"🧾 Stock : {s}")
    lines.append("")

    # --- Accessoires (Window Sticker) ---
    if options:
        lines.append("✨ ACCESSOIRES OPTIONNELS (Window Sticker)")
        lines.append("")

        seen_titles = set()

        for g in options:
            tt = (g.get("title") or "").strip()
            details = g.get("details") or []

            # skip titres vides / blacklisted / doublons
            if not tt or is_blacklisted_line(tt):
                continue
            k = tt.casefold()
            if k in seen_titles:
                continue
            seen_titles.add(k)

            # ✅ IMPORTANT: on n'affiche JAMAIS le prix des options
            lines.append(f"✅  {tt}")

            # sous-options filtrées + blacklist + dédoublonnage
            seen_details = set()
            kept = 0
            for d in details:
                if kept >= 6:
                    break
                dd = (d or "").strip()
                if not dd or is_blacklisted_line(dd):
                    continue
                dk = dd.casefold()
                if dk in seen_details:
                    continue
                seen_details.add(dk)

                lines.append(f"        ▫️ {dd}")
                kept += 1

        lines.append("")
        lines.append("📌 Le reste des détails est dans le Window Sticker :")
        lines.append("")
        if v:
            lines.append(f"https://www.chrysler.com/hostd/windowsticker/getWindowStickerPdf.do?vin={v}")
        else:
            lines.append("(VIN introuvable — lien Window Sticker non généré)")
        lines.append("")

    # --- Lien Kennebec (optionnel) ---
    if vehicle_url:
        lines.append("🔗 Fiche complète :")
        lines.append(vehicle_url)
        lines.append("")

    # --- Échanges ---
    lines.append("🔁 J’accepte les échanges : 🚗 auto • 🏍️ moto • 🛥️ bateau • 🛻 VTT • 🏁 côte-à-côte")
    lines.append("📸 Envoie-moi les photos + infos de ton échange (année / km / paiement restant) → je te reviens vite.")

    return "\n".join(lines).strip() + "\n"
