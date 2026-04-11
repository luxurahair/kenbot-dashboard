"""
vin_decoder.py

Decode les VINs via l'API NHTSA vPIC (gratuit, sans cle API).
Retourne les specs du vehicule: moteur, HP, transmission, drive, places, securite.
"""

import requests
from typing import Dict, Any, Optional

NHTSA_URL = "https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"

# Cache simple en memoire pour eviter les appels repetitifs
_cache: Dict[str, Dict[str, Any]] = {}


def decode_vin(vin: str) -> Optional[Dict[str, Any]]:
    """
    Decode un VIN via NHTSA et retourne les specs utiles.
    Retourne None si le VIN est invalide ou vide.
    """
    vin = (vin or "").strip().upper()
    if len(vin) < 11:
        return None

    if vin in _cache:
        return _cache[vin]

    try:
        r = requests.get(NHTSA_URL.format(vin=vin), timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[VIN_DECODER] Erreur API NHTSA pour {vin}: {e}")
        return None

    raw = {}
    for item in data.get("Results", []):
        val = (item.get("Value") or "").strip()
        if val:
            raw[item["Variable"]] = val

    # Extraire les specs utiles
    specs = {
        "vin": vin,
        "make": raw.get("Make", ""),
        "model": raw.get("Model", ""),
        "year": raw.get("Model Year", ""),
        "trim": raw.get("Trim", ""),
        "body_class": raw.get("Body Class", ""),
        # Moteur
        "engine_cylinders": raw.get("Engine Number of Cylinders", ""),
        "engine_displacement_l": raw.get("Displacement (L)", ""),
        "engine_hp": raw.get("Engine Brake (hp) From", ""),
        "engine_model": raw.get("Engine Model", ""),
        "engine_config": raw.get("Engine Configuration", ""),
        "fuel_primary": raw.get("Fuel Type - Primary", ""),
        "fuel_secondary": raw.get("Fuel Type - Secondary", ""),
        "turbo": raw.get("Turbo", ""),
        "electrification": raw.get("Electrification Level", ""),
        # Transmission
        "transmission": raw.get("Transmission Style", ""),
        "transmission_speeds": raw.get("Transmission Speeds", ""),
        "drive_type": raw.get("Drive Type", ""),
        # Capacite
        "seats": raw.get("Number of Seats", ""),
        "seat_rows": raw.get("Number of Seat Rows", ""),
        "gvwr": raw.get("Gross Vehicle Weight Rating From", ""),
        # Fabrication
        "plant_country": raw.get("Plant Country", ""),
        "plant_city": raw.get("Plant City", ""),
        # Securite
        "abs": raw.get("Anti-lock Braking System (ABS)", ""),
        "esc": raw.get("Electronic Stability Control (ESC)", ""),
        "traction_control": raw.get("Traction Control", ""),
        "tpms": raw.get("Tire Pressure Monitoring System (TPMS) Type", ""),
        "keyless": raw.get("Keyless Ignition", ""),
        "adaptive_cruise": raw.get("Adaptive Cruise Control (ACC)", ""),
        "auto_braking": raw.get("Crash Imminent Braking (CIB)", ""),
        "forward_collision": raw.get("Forward Collision Warning (FCW)", ""),
        "pedestrian_braking": raw.get("Pedestrian Automatic Emergency Braking (PAEB)", ""),
        "blind_spot": raw.get("Blind Spot Warning (BSW)", ""),
        "lane_departure": raw.get("Lane Departure Warning (LDW)", ""),
        "lane_keeping": raw.get("Lane Keeping Assistance (LKA)", ""),
        "backup_camera": raw.get("Backup Camera", ""),
        "rear_cross_traffic": raw.get("Rear Cross Traffic Alert", ""),
        "headlamp_type": raw.get("Headlamp Light Source", ""),
        "drl": raw.get("Daytime Running Light (DRL)", ""),
    }

    _cache[vin] = specs
    return specs


def format_engine_line(specs: Dict[str, Any]) -> str:
    """Formate la ligne moteur lisible."""
    parts = []
    cyl = specs.get("engine_cylinders", "")
    disp = specs.get("engine_displacement_l", "")
    hp = specs.get("engine_hp", "")
    config = specs.get("engine_config", "")
    turbo = specs.get("turbo", "")

    if cyl and disp:
        eng = f"{cyl} cylindres"
        if config:
            eng += f" {config.lower()}"
        eng += f" {disp}L"
        parts.append(eng)
    elif disp:
        parts.append(f"{disp}L")

    if hp:
        parts.append(f"{hp} HP")

    if turbo and turbo.lower() not in ("", "not applicable"):
        parts.append("turbo")

    return " — ".join(parts) if parts else ""


def format_specs_for_prompt(specs: Dict[str, Any]) -> str:
    """Formate les specs en texte lisible pour le prompt IA."""
    if not specs:
        return ""

    lines = []

    # Moteur
    engine = format_engine_line(specs)
    if engine:
        lines.append(f"Moteur: {engine}")

    fuel = specs.get("fuel_primary", "")
    fuel2 = specs.get("fuel_secondary", "")
    elec = specs.get("electrification", "")
    if elec and "hev" in elec.lower():
        lines.append(f"Hybride: {elec}")
    elif fuel2 and fuel2.lower() == "electric":
        lines.append("Hybride (electrique secondaire)")
    elif fuel:
        lines.append(f"Carburant: {fuel}")

    # Transmission
    trans = specs.get("transmission", "")
    speeds = specs.get("transmission_speeds", "")
    if trans:
        t = trans
        if speeds:
            t += f" {speeds} vitesses"
        lines.append(f"Transmission: {t}")

    drive = specs.get("drive_type", "")
    if drive:
        lines.append(f"Motricite: {drive}")

    # Capacite
    seats = specs.get("seats", "")
    rows = specs.get("seat_rows", "")
    if seats:
        s = f"{seats} places"
        if rows and int(rows) > 2:
            s += f", {rows} rangees"
        lines.append(s)

    # Fabrication
    country = specs.get("plant_country", "")
    city = specs.get("plant_city", "")
    if country:
        fab = f"Fabrique: {country}"
        if city:
            fab += f" ({city})"
        lines.append(fab)

    # Securite
    safety = []
    safety_map = {
        "adaptive_cruise": "Cruise adaptatif",
        "auto_braking": "Freinage d'urgence automatique",
        "pedestrian_braking": "Detection pietons",
        "blind_spot": "Avertissement angle mort",
        "lane_keeping": "Aide au maintien de voie",
        "lane_departure": "Avertissement sortie de voie",
        "backup_camera": "Camera de recul",
        "rear_cross_traffic": "Alerte trafic transversal arriere",
        "keyless": "Demarrage sans cle",
    }
    for key, label in safety_map.items():
        val = specs.get(key, "")
        if val and val.lower() in ("standard", "yes"):
            safety.append(label)

    headlamp = specs.get("headlamp_type", "")
    if headlamp and "led" in headlamp.lower():
        safety.append("Phares LED")

    if safety:
        lines.append(f"Securite de serie: {', '.join(safety)}")

    return "\n".join(lines)
