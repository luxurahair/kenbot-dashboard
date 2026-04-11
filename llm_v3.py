"""
llm_v3.py

Génération de textes Facebook HUMAINS et INTELLIGENTS pour les annonces auto.
Utilise vehicle_intelligence.py pour adapter le ton, les angles et le contenu
à chaque véhicule spécifique.

Version 3.0 — Textes qui sonnent comme un vrai vendeur passionné, pas un robot.
"""

import os
import random
from typing import Dict, Any, Optional, List

from vehicle_intelligence import build_vehicle_context, humanize_options


# ─── OpenAI client ───
def _get_openai():
    try:
        from openai import OpenAI
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            return None
        return OpenAI(api_key=api_key)
    except ImportError:
        return None


# ─── Prompts par type de véhicule ───

SYSTEM_PROMPT = """Tu es Daniel Giroux, vendeur passionné chez Kennebec Dodge Chrysler à Saint-Georges en Beauce.
Tu écris des annonces Facebook pour des véhicules d'occasion.

RÈGLES ABSOLUES:
- Tu écris en français québécois naturel. Pas de français de France. Pas de robot.
- Tu parles comme un VRAI vendeur qui connaît ses chars. Pas de phrases génériques.
- JAMAIS de "Prêt à dominer les routes" ou "faire tourner les têtes" — c'est cliché.
- JAMAIS de "sillonner la Beauce" ou "conquérir les chemins" — c'est du robot.
- JAMAIS mentionner "la Beauce", "routes de la Beauce" ou "paysages beauceron". On vend des chars, pas du tourisme.
- Chaque texte doit être UNIQUE. Si tu vends un Challenger, parle du V8. Si c'est un Wrangler, parle du off-road.
- Le ton est direct, authentique, passionné. Comme si tu parlais à un ami au garage.
- Tu CONNAIS les véhicules. Tu sais ce qui rend chaque modèle spécial.
- Maximum 3-4 phrases pour l'intro. Pas de roman.
- Pas de hashtags dans l'intro.
- Pas d'emojis dans l'intro (ils viennent après dans le corps de l'annonce).
"""

def _build_prompt_for_vehicle(ctx: Dict[str, Any], event: str = "NEW", options_text: str = "") -> str:
    """Construit le prompt spécifique au véhicule."""

    # Info de base
    title = ctx.get("title", "")
    brand = ctx.get("brand", "").capitalize()
    model = ctx.get("model", "")
    trim = ctx.get("trim", "")
    year = ctx.get("year", "")
    price_fmt = ctx.get("price_formatted", "")
    km_fmt = ctx.get("km_formatted", "")
    km_desc = ctx.get("km_description", "")
    price_desc = ctx.get("price_description", "")

    # Intelligence véhicule
    vehicle_type = ctx.get("vehicle_type", "general")
    hp = ctx.get("hp", "")
    engine = ctx.get("engine", "")
    trim_vibe = ctx.get("trim_vibe", "")
    model_known_for = ctx.get("model_known_for", "")
    brand_identity = ctx.get("brand_identity", "")
    brand_angles = ctx.get("brand_angles", [])

    # Construire les infos spécifiques
    specs_info = []
    if hp:
        specs_info.append(f"Moteur: {engine} — {hp} chevaux")
    elif engine:
        specs_info.append(f"Moteur: {engine}")
    if trim_vibe:
        specs_info.append(f"Ce trim: {trim_vibe}")
    if model_known_for:
        specs_info.append(f"Ce modèle est connu pour: {model_known_for}")
    if brand_identity:
        specs_info.append(f"La marque {brand}: {brand_identity}")

    # Options humanisées
    human_options = []
    if options_text:
        human_options = humanize_options(options_text)

    prompt = f"""Écris une annonce Facebook pour ce véhicule:

VÉHICULE: {title}
PRIX: {price_fmt}
KILOMÉTRAGE: {km_fmt} ({km_desc})
POSITIONNEMENT PRIX: {price_desc}
TYPE: {vehicle_type}

CONNAISSANCES SPÉCIFIQUES:
{chr(10).join(specs_info) if specs_info else "Aucune info spécifique disponible."}

OPTIONS/ÉQUIPEMENTS CONFIRMÉS:
{chr(10).join(f"- {o}" for o in human_options) if human_options else "Aucune option confirmée."}

ANGLES DE VENTE SUGGÉRÉS: {', '.join(brand_angles[:3]) if brand_angles else 'qualité, valeur, confiance'}

INSTRUCTIONS:
1. Écris une INTRO de 3-4 phrases maximum. Naturelle, directe, passionnée.
   - Mentionne ce qui rend CE véhicule spécial (pas une intro générique)
   - Si tu connais le moteur/HP, mentionne-le naturellement
   - Adapte le ton au type: {"adrénaline et son du moteur" if vehicle_type == "muscle_car" else "robustesse et capacité" if vehicle_type in ("pickup", "pickup_hd") else "aventure et liberté" if vehicle_type == "off_road" else "confort et raffinement" if vehicle_type == "suv_premium" else "style et économie" if vehicle_type in ("citadine", "suv_compact") else "exclusivité et rêve" if vehicle_type in ("exotique", "collector") else "polyvalence et fiabilité"}

2. Puis le CORPS structuré:
   - Titre avec le nom complet et l'année
   - Prix
   - Kilométrage
   - Stock
   - 5-8 équipements/caractéristiques en points (en français, pas de jargon technique brut)
   - Si c'est un Stellantis avec sticker: mention "Window Sticker vérifié"

3. FERME avec: le nom Daniel Giroux et le numéro 418-222-3939.
   Ne mets PAS "Kennebec Dodge" dans le footer (il est ajouté automatiquement).

FORMAT DE SORTIE: Texte prêt à copier-coller sur Facebook. Utilise des emojis avec parcimonie dans le corps (pas dans l'intro).
"""

    if event == "PRICE_CHANGED":
        old_price = ctx.get("old_price", "")
        new_price = ctx.get("new_price", "")
        prompt += f"""
ÉVÉNEMENT SPÉCIAL: BAISSE DE PRIX
Ancien prix: {old_price}
Nouveau prix: {new_price}
→ Commence par mentionner la baisse de prix de façon naturelle et excitante.
→ Fais sentir que c'est une opportunité sans être agressif.
"""

    return prompt


# ─── Variations d'intro pour éviter la répétition ───
INTRO_STYLES = [
    "direct",       # Va droit au but: "J'ai un [vehicule] qui..."
    "storytelling",  # Raconte une mini-histoire: "Y'a des chars qui..."
    "question",     # Pose une question: "Tu cherches un truck qui..."
    "expertise",    # Montre ta connaissance: "Le [modèle], c'est..."
    "opportunité",  # Focus sur le deal: "Celui-là, à ce prix-là..."
]


def generate_smart_text(
    vehicle: Dict[str, Any],
    event: str = "NEW",
    options_text: str = "",
    old_price: Any = None,
    new_price: Any = None,
) -> Optional[str]:
    """
    Génère un texte Facebook intelligent et humain pour un véhicule.

    Args:
        vehicle: Dict avec title, stock, vin, price_int, km_int, url, etc.
        event: "NEW", "PRICE_CHANGED", "PHOTOS_ADDED"
        options_text: Texte brut des options du sticker (optionnel)
        old_price: Ancien prix (pour PRICE_CHANGED)
        new_price: Nouveau prix (pour PRICE_CHANGED)

    Returns:
        Texte Facebook prêt à publier, ou None si échec
    """
    client = _get_openai()
    if not client:
        return None

    # Construire le contexte enrichi
    ctx = build_vehicle_context(vehicle)
    if old_price:
        ctx["old_price"] = f"{int(old_price):,}".replace(",", " ") + " $"
    if new_price:
        ctx["new_price"] = f"{int(new_price):,}".replace(",", " ") + " $"

    # Choisir un style d'intro aléatoire
    style = random.choice(INTRO_STYLES)

    # Construire le prompt
    prompt = _build_prompt_for_vehicle(ctx, event, options_text)
    prompt += f"\n\nSTYLE D'INTRO: {style}"

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.85,
            max_tokens=1200,
        )

        text = response.choices[0].message.content.strip()

        # Post-traitement
        text = _post_process(text)
        return text

    except Exception as e:
        print(f"[LLM_V3 ERROR] {e}", flush=True)
        return None


def generate_intro_v3(vehicle: Dict[str, Any], max_chars: int = 300) -> Optional[str]:
    """
    Génère SEULEMENT une intro courte et punchy pour un véhicule.
    Utilisée pour ajouter au-dessus d'un texte existant.
    """
    client = _get_openai()
    if not client:
        return None

    ctx = build_vehicle_context(vehicle)
    style = random.choice(INTRO_STYLES)

    title = ctx.get("title", "")
    hp = ctx.get("hp", "")
    engine = ctx.get("engine", "")
    trim_vibe = ctx.get("trim_vibe", "")
    model_known_for = ctx.get("model_known_for", "")
    km_desc = ctx.get("km_description", "")
    price_fmt = ctx.get("price_formatted", "")
    vehicle_type = ctx.get("vehicle_type", "general")

    prompt = f"""Écris SEULEMENT une intro de 2-3 phrases pour cette annonce Facebook.
Véhicule: {title}
Prix: {price_fmt}
KM: {ctx.get('km_formatted', '')} ({km_desc})
{f'Moteur: {engine} — {hp} HP' if hp else ''}
{f'Ce modèle: {model_known_for}' if model_known_for else ''}
{f'Ce trim: {trim_vibe}' if trim_vibe else ''}
Style: {style}
Type: {vehicle_type}

RÈGLES: Max {max_chars} caractères. Pas d'emojis. Pas de clichés. Pas de "routes de la Beauce". 
Parle comme un vrai vendeur québécois passionné qui connaît ses chars.
Mentionne ce qui rend CE véhicule spécial."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.9,
            max_tokens=200,
        )
        text = response.choices[0].message.content.strip()
        text = text.strip('"').strip("'")
        return text[:max_chars]
    except Exception as e:
        print(f"[LLM_V3 INTRO ERROR] {e}", flush=True)
        return None


def _post_process(text: str) -> str:
    """Nettoyage post-génération."""
    # Retirer les guillemets englobants
    text = text.strip('"').strip("'")

    # Retirer les clichés qui auraient pu passer
    cliches = [
        "prêt à dominer",
        "faire tourner les têtes",
        "sillonner la beauce",
        "conquérir les chemins",
        "dominer les routes",
        "parcourir les routes de beauce",
        "arpenter les routes",
        "routes de la beauce",
        "routes de beauce",
        "chemins de la beauce",
        "paysages de la beauce",
        "paysages beauceron",
    ]
    for c in cliches:
        if c in text.lower():
            # Retirer la phrase contenant le cliché
            lines = text.split("\n")
            text = "\n".join(l for l in lines if c not in l.lower())

    return text.strip()


# ─── Test local ───
if __name__ == "__main__":
    # Test avec quelques véhicules
    test_vehicles = [
        {"title": "Dodge CHALLENGER R/T SCAT PACK BLANC 2023", "stock": "06234", "vin": "2C3CDZFJ1PH593481", "price_int": 79995, "km_int": 11500},
        {"title": "Jeep WRANGLER RUBICON 4XE 2024", "stock": "06106", "vin": "1C4HJXFN5RW123456", "price_int": 62995, "km_int": 15586},
        {"title": "Ram 2500 BIG HORN 2025", "stock": "06230", "vin": "3C6UR5DJ1RG123456", "price_int": 71995, "km_int": 25},
        {"title": "LAMBORGHIN I 2024", "stock": "06232", "vin": "", "price_int": 343995, "km_int": 8900},
        {"title": "Ford MUSTANG 2022", "stock": "46104A", "vin": "", "price_int": 35995, "km_int": 21433},
        {"title": "Fiat 500 E RED 2024", "stock": "44220A", "vin": "", "price_int": 23995, "km_int": 22},
    ]

    for v in test_vehicles:
        print(f"\n{'='*60}")
        print(f"TEST: {v['title']}")
        print(f"{'='*60}")
        ctx = build_vehicle_context(v)
        print(f"  Brand: {ctx['brand']} | Model: {ctx['model']} | Trim: {ctx['trim']}")
        print(f"  Type: {ctx['vehicle_type']} | HP: {ctx['hp']} | Engine: {ctx['engine']}")
        print(f"  Vibe: {ctx['trim_vibe']}")
        print(f"  KM: {ctx['km_description']} | Prix: {ctx['price_description']}")
        print()

        text = generate_smart_text(v)
        if text:
            print(text[:500])
        else:
            print("  [Pas de clé OpenAI — test parsing seulement]")
