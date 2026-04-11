import time
from typing import Any, Dict

import requests

# Import du module centralisé pour la gestion du footer
from footer_utils import (
    has_footer,
    add_footer_if_missing,
    get_dealer_footer,
    smart_hashtags,
    remove_footer_marker,
    DEALER_PHONE,
)

FOOTER_MARKER = "[[DG_FOOTER]]"


def _fmt_money(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        n = int(float(value))
        return f"{n:,}".replace(",", " ") + " $"
    except Exception:
        return str(value).strip()


def _fmt_km(value: Any) -> str:
    if value in (None, ""):
        return ""
    try:
        n = int(float(value))
        return f"{n:,}".replace(",", " ") + " km"
    except Exception:
        return str(value).strip()


def _vehicle_price(vehicle: Dict[str, Any]) -> str:
    v = vehicle or {}
    raw = v.get("price")
    if raw in (None, ""):
        raw = v.get("price_int")
    return _fmt_money(raw)


def _vehicle_mileage(vehicle: Dict[str, Any]) -> str:
    v = vehicle or {}
    raw = v.get("mileage")
    if raw in (None, ""):
        raw = v.get("km")
    if raw in (None, ""):
        raw = v.get("km_int")
    return _fmt_km(raw)


def _smart_hashtags(vehicle: Dict[str, Any], event: str) -> str:
    v = vehicle or {}
    title = (v.get("title") or "").lower()
    text_blob = f"{title} {str(v).lower()}"

    tags = [
        "#DanielGiroux",
        "#Beauce",
        "#Quebec",
        "#SaintGeorges",
        "#Thetford",
    ]

    if event == "PRICE_CHANGED":
        tags.append("#BaisseDePrix")
    elif event == "NEW":
        tags.append("#NouvelArrivage")

    if "awd" in text_blob or "4x4" in text_blob:
        tags.append("#AWD")

    if "jeep" in title:
        tags.append("#Jeep")
    elif "ram" in title:
        tags.append("#Ram")
    elif "dodge" in title:
        tags.append("#Dodge")
    elif "chrysler" in title:
        tags.append("#Chrysler")

    if "challenger" in title:
        tags.append("#Challenger")
    if "hornet" in title:
        tags.append("#Hornet")
    if "wagoneer" in title:
        tags.append("#Wagoneer")
    if "big horn" in title:
        tags.append("#BigHorn")

    seen = set()
    out = []
    for tag in tags:
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            out.append(tag)

    return " ".join(out[:10]).strip()


def _dealer_footer(vehicle: Dict[str, Any], event: str) -> str:
    tags = _smart_hashtags(vehicle, event)
    return (
        "🔁 J’accepte les échanges : 🚗 auto • 🏍️ moto • 🛥️ bateau • 🛻 VTT • 🏁 côte-à-côte\n"
        "📸 Envoie-moi les photos + infos de ton échange (année / km / paiement restant) → je te reviens vite.\n"
        "📞 Daniel Giroux 418-222-3939\n"
        f"{tags}\n"
        f"{FOOTER_MARKER}"
    ).strip()


def ensure_single_footer(text: str, footer: str) -> str:
    """
    Ajoute le footer UNIQUEMENT si aucun footer n'est présent.
    Utilise footer_utils.has_footer pour une détection fiable.
    """
    base = (text or "").rstrip()
    
    # Utiliser la détection centralisée
    if has_footer(base):
        return remove_footer_marker(base)
    
    # Vérifier aussi le marqueur legacy
    if FOOTER_MARKER.lower() in base.lower():
        return remove_footer_marker(base)
    
    return f"{base}\n\n{footer}".strip()


def _fallback_text(slug: str, event: str, vehicle: Dict[str, Any]) -> str:
    v = vehicle or {}
    title = (v.get("title") or "Véhicule").strip()
    stock = (v.get("stock") or "").strip()
    vin = (v.get("vin") or "").strip()
    url = (v.get("url") or "").strip()
    price = _vehicle_price(v)
    mileage = _vehicle_mileage(v)
    old_price = _fmt_money(v.get("old_price"))
    new_price = _fmt_money(v.get("new_price"))

    lines = []

    if event == "PRICE_CHANGED" and old_price and new_price:
        lines.append(f"💥 Nouveau prix pour ce {title} !")
        lines.append("")
        lines.append(f"Avant : {old_price}")
        lines.append(f"Maintenant : {new_price}")
        lines.append("")
        lines.append("Si vous l’aviez à l’œil, c’est peut-être le bon moment pour passer à l’action.")
    else:
        lines.append(f"🔥 {title}")
        if price:
            lines.append(f"💰 {price}")
        if mileage:
            lines.append(f"📊 {mileage}")

    if stock:
        lines.append(f"🧾 Stock : {stock}")
    if vin:
        lines.append(f"🔢 VIN : {vin}")
    if url:
        lines.append("")
        lines.append(url)

    lines.append("")
    lines.append("📞 Daniel Giroux 418-222-3939")

    return "\n".join(lines).strip()


def generate_facebook_text(base_url: str, slug: str, event: str, vehicle: dict) -> str:
    url = f"{base_url.rstrip('/')}/generate"
    payload = {"slug": slug, "event": event, "vehicle": vehicle}

    last_err = None
    for attempt in range(1, 4):
        try:
            r = requests.post(url, json=payload, timeout=120)
            r.raise_for_status()
            j = r.json()

            txt = (j.get("facebook_text") or j.get("text") or "").strip()
            if txt:
                return ensure_single_footer(txt, _dealer_footer(vehicle, event))

            return ensure_single_footer(
                _fallback_text(slug, event, vehicle),
                _dealer_footer(vehicle, event),
            )

        except Exception as e:
            last_err = e
            time.sleep(2 * attempt)

    print(f"[TEXT_ENGINE FALLBACK] slug={slug} event={event} err={last_err}")
    return ensure_single_footer(
        _fallback_text(slug, event, vehicle),
        _dealer_footer(vehicle, event),
    )
