# llm.py – Génération AI améliorée pour Daniel Giroux
# VERSION 2.0 - Textes variés, sans clichés
import os
import random
from typing import Dict, Any, Optional, List

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# Importer le classifier pour adapter le ton
try:
    from classifier import classify
except ImportError:
    def classify(v):
        return "default"

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_client: Optional[OpenAI] = None


# ============================================================
# CONFIGURATION - CLICHÉS INTERDITS
# ============================================================

CLICHES_INTERDITS = """
❌ PHRASES STRICTEMENT INTERDITES (ne JAMAIS utiliser):
- "sillonner les routes"
- "sillonner la Beauce"  
- "parfait pour l'hiver québécois"
- "affronter l'hiver"
- "prêt à conquérir"
- "conçu pour affronter"
- "idéal pour les aventures"
- "n'attend plus que toi"
- "ce bijou"
- "cette merveille"
- "cette beauté"
- "viens le voir"
- "véritable machine"
- "monstre de puissance"
- "bête de route"
- "sensation de conduite"
- "vous séduira"
- "ne cherchez plus"
- "l'occasion parfaite"
"""

# ============================================================
# ANGLES PAR TYPE DE VÉHICULE
# ============================================================

ANGLES_PAR_TYPE = {
    "truck": {
        "focus": "Capacité de travail, remorquage, fiabilité long terme",
        "exemples": [
            "Parle de sa capacité de remorquage ou de sa boîte",
            "Mentionne son usage pour le travail ou les projets",
            "Évoque sa robustesse prouvée",
        ],
    },
    "suv": {
        "focus": "Famille, espace, polyvalence 4 saisons, sécurité",
        "exemples": [
            "Parle de l'espace pour la famille",
            "Mentionne la traction intégrale pour l'hiver",
            "Évoque les équipements de sécurité",
        ],
    },
    "exotic": {
        "focus": "Exclusivité, prestige, investissement, rareté",
        "exemples": [
            "Parle de sa rareté sur le marché",
            "Mentionne son entretien impeccable",
            "Évoque l'opportunité d'investissement",
        ],
    },
    "sedan": {
        "focus": "Économie, fiabilité quotidienne, confort",
        "exemples": [
            "Parle de sa consommation d'essence raisonnable",
            "Mentionne sa fiabilité reconnue",
            "Évoque son confort pour les trajets quotidiens",
        ],
    },
    "coupe": {
        "focus": "Performance, style, plaisir de conduire",
        "exemples": [
            "Parle de ses performances",
            "Mentionne son look distinctif",
            "Évoque le plaisir de conduite",
        ],
    },
    "ev": {
        "focus": "Économies carburant, technologie, avenir",
        "exemples": [
            "Parle des économies sur l'essence",
            "Mentionne l'autonomie",
            "Évoque les incitatifs gouvernementaux",
        ],
    },
    "minivan": {
        "focus": "Famille nombreuse, espace cargo, praticité",
        "exemples": [
            "Parle de l'espace pour toute la famille",
            "Mentionne les portes coulissantes pratiques",
            "Évoque l'espace de rangement",
        ],
    },
    "default": {
        "focus": "Polyvalence, bon rapport qualité-prix, état impeccable",
        "exemples": [
            "Parle de son état général",
            "Mentionne son entretien régulier",
            "Évoque sa polyvalence",
        ],
    },
}

# ============================================================
# VARIATIONS DE TON
# ============================================================

VARIATIONS_INTRO = [
    "Commence par une question rhétorique courte",
    "Commence par un fait concret sur le véhicule",
    "Commence par mentionner pourquoi tu vends ce modèle",
    "Commence directement par le bénéfice principal",
    "Commence par une observation personnelle de vendeur",
]


# ============================================================
# HELPERS
# ============================================================

def get_client() -> Optional[OpenAI]:
    global _client
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or not OpenAI:
        return None
    if _client is None:
        _client = OpenAI(api_key=api_key)
    return _client


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


def _get_features_text(vehicle: Dict[str, Any]) -> str:
    """Extrait les équipements pour enrichir le prompt."""
    features = vehicle.get("features") or []
    comfort = vehicle.get("comfort") or []
    all_features = features + comfort
    
    if not all_features:
        return "Non spécifiés"
    
    # Prendre les 5 premiers
    return ", ".join(str(f) for f in all_features[:5])


def _safe_trim(text: str, max_chars: int) -> str:
    txt = (text or "").strip()
    if len(txt) <= max_chars:
        return txt

    phone = "418-222-3939"
    if phone in txt:
        idx = txt.find(phone) + len(phone)
        if idx <= max_chars:
            return txt[:idx].rstrip(" .,!?;:-")

    cut = txt[:max_chars].rstrip(" .,!?;:-")
    return cut + "..."


# ============================================================
# GÉNÉRATION PRINCIPALE
# ============================================================

def generate_ad_text(
    vehicle: Dict[str, Any],
    kind: str = "default",
    max_chars: int = 400,  # Augmenté de 220 à 400
) -> str:
    """
    Génère une accroche AI Facebook VARIÉE, centrée sur Daniel Giroux.
    
    VERSION 2.0 - Améliorations:
    - Textes plus longs (400 chars au lieu de 220)
    - Clichés interdits explicitement
    - Angle adapté au type de véhicule
    - Variations de ton pour éviter la répétition
    
    Args:
        vehicle: Dictionnaire avec les infos du véhicule
        kind: "default", "price_changed", "truck", "suv", etc.
        max_chars: Limite de caractères (défaut: 400)
    
    Returns:
        Texte de l'accroche ou chaîne vide si erreur.
    """
    client = get_client()
    if not client:
        return ""

    v = vehicle or {}
    title = (v.get("title") or "Véhicule").strip()
    price = _vehicle_price(v)
    mileage = _vehicle_mileage(v)
    stock = str(v.get("stock") or "").strip()
    url = str(v.get("url") or "").strip()
    old_price = _fmt_money(v.get("old_price"))
    new_price = _fmt_money(v.get("new_price"))
    features = _get_features_text(v)
    
    # Classifier le véhicule pour adapter le ton
    vehicle_type = classify(v) if kind == "default" else kind
    if vehicle_type == "price_changed":
        vehicle_type = classify(v)  # Garder le type pour l'angle
    
    # Récupérer l'angle approprié
    angle_config = ANGLES_PAR_TYPE.get(vehicle_type, ANGLES_PAR_TYPE["default"])
    focus = angle_config["focus"]
    exemple = random.choice(angle_config["exemples"])
    
    # Variation de ton
    variation = random.choice(VARIATIONS_INTRO)
    
    # Construire l'angle selon le type d'événement
    if kind == "price_changed":
        event_angle = f"""
ÉVÉNEMENT: BAISSE DE PRIX
- Ancien prix: {old_price}
- Nouveau prix: {new_price}
- Fais sentir l'opportunité avec un ton vendeur humain
- Mentionne clairement la baisse de prix
- Crée un sentiment d'urgence SANS être agressif
"""
    else:
        event_angle = f"""
ÉVÉNEMENT: NOUVEAU VÉHICULE
- {exemple}
- Focus sur: {focus}
"""

    system_prompt = f"""Tu es Daniel Giroux, vendeur automobile chez Kennebec Dodge à Saint-Georges (Beauce, Québec) depuis 2009.

{CLICHES_INTERDITS}

✅ TON STYLE OBLIGATOIRE:
- Parle en "je" ou "moi" (JAMAIS "nous" ou au nom de l'entreprise)
- Français québécois naturel et authentique
- Direct, chaleureux, crédible
- Vendeur humain, pas robotique
- AUCUNE invention - utilise SEULEMENT les données fournies
- {variation}

📋 DONNÉES DU VÉHICULE:
- Titre: {title}
- Prix: {price}
- Kilométrage: {mileage}
- Stock: {stock}
- Équipements: {features}

{event_angle}

🎯 OBJECTIF:
Écris une accroche Facebook de {max_chars} caractères maximum.
- 2-3 phrases naturelles
- Mentionne UN détail SPÉCIFIQUE du véhicule (pas générique)
- Au plus 1 emoji pertinent
- NE PAS inclure de hashtags
- NE PAS terminer par le téléphone (il sera ajouté automatiquement)
"""

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"Génère une accroche vendeuse et UNIQUE pour ce {title}. Évite absolument les clichés listés.",
                },
            ],
            max_tokens=150,  # Augmenté de 90 à 150
            temperature=0.9,  # Augmenté pour plus de variété
            top_p=0.95,
        )

        txt = (response.choices[0].message.content or "").strip()
        
        # Vérifier qu'aucun cliché n'est présent
        txt = _filter_cliches(txt)
        
        return _safe_trim(txt, max_chars)

    except Exception as e:
        print(f"[ERROR AI] {e}")
        return ""


def _filter_cliches(text: str) -> str:
    """
    Filtre de sécurité: retire les clichés si l'IA en a quand même généré.
    """
    cliches_to_check = [
        "sillonner les routes",
        "sillonner la beauce",
        "parfait pour l'hiver",
        "prêt à conquérir",
        "prête à dominer",
        "dominer les routes",
        "n'attend plus que toi",
        "ce bijou",
        "cette merveille",
    ]
    
    low = text.lower()
    for cliche in cliches_to_check:
        if cliche in low:
            # L'IA a ignoré les instructions - on retourne vide
            print(f"[AI WARNING] Cliché détecté et filtré: {cliche}")
            return ""
    
    return text


# ============================================================
# HUMANIZE - Rendre le texte moins robotique
# ============================================================

def humanize_text(raw_text: str, vehicle: Dict[str, Any] = None) -> str:
    """
    Prend un texte généré (souvent robotique avec listes) et le rend plus naturel.
    
    Cette fonction est conçue pour être appelée APRÈS la génération du texte
    par sticker_to_ad.py ou ad_builder.py pour donner un élan plus humain.
    
    Args:
        raw_text: Le texte brut généré (peut contenir des listes, emojis, etc.)
        vehicle: Optionnel - infos du véhicule pour contexte
    
    Returns:
        Le texte humanisé avec une intro plus naturelle.
    """
    client = get_client()
    if not client:
        return raw_text  # Pas d'API = retourner tel quel
    
    # Extraire les infos clés du texte
    v = vehicle or {}
    title = v.get("title") or _extract_title_from_text(raw_text)
    
    system_prompt = f"""Tu es Daniel Giroux, vendeur automobile authentique de la Beauce depuis 2009.

{CLICHES_INTERDITS}

🎯 TA MISSION:
On te donne un texte d'annonce automobile DÉJÀ GÉNÉRÉ qui est trop robotique.
Tu dois RÉÉCRIRE SEULEMENT L'INTRODUCTION (les 2-3 premières phrases) pour la rendre:
- Plus naturelle et humaine
- Avec ton style vendeur authentique
- SANS les clichés interdits ci-dessus
- En gardant les VRAIES infos du véhicule

⚠️ RÈGLES STRICTES:
1. NE TOUCHE PAS aux sections techniques (équipements, options, prix, etc.)
2. NE TOUCHE PAS au footer (contact, échanges, hashtags)
3. RÉÉCRIS SEULEMENT l'intro pour qu'elle soit plus accrocheuse
4. Maximum 2-3 phrases pour l'intro
5. Parle en "je" - c'est TOI Daniel qui vend
6. Mentionne UN détail SPÉCIFIQUE du véhicule (pas générique)

✅ EXEMPLES DE BON STYLE:
- "🔥 Un Scat Pack avec 11 500 km, c'est rare. Celui-là sort du garage d'un gars qui en prenait soin."
- "💪 J'ai rentré ce Challenger la semaine passée. 6.4L Hemi, boîte auto 8 vitesses - tu vas sourire!"
- "✨ Le proprio l'a gardé 2 ans, toujours dans le garage l'hiver. Audio Harman/Kardon, régulateur adaptatif - bien équipé."

📌 EMOJIS PERMIS (2-3 max dans l'intro):
🔥 💪 ✨ 🚗 💥 👀 ⚡ - utilise-les pour donner de la vie!

❌ ÉVITE ABSOLUMENT:
- "prête à dominer les routes"
- "sillonner la Beauce"
- "n'attend plus que toi"
- Tout ce qui sonne générique ou robot
"""

    user_message = f"""Voici le texte d'annonce à améliorer:

{raw_text[:2000]}

Réécris SEULEMENT l'introduction (2-3 premières phrases) pour la rendre plus naturelle et humaine, style Daniel Giroux. Garde tout le reste intact."""

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            max_tokens=300,
            temperature=0.85,
        )
        
        result = (response.choices[0].message.content or "").strip()
        
        # Vérifier les clichés
        result = _filter_cliches(result)
        if not result:
            return raw_text  # Cliché détecté, garder l'original
        
        return result
        
    except Exception as e:
        print(f"[ERROR humanize] {e}")
        return raw_text


def _extract_title_from_text(text: str) -> str:
    """Extrait le titre du véhicule depuis le texte brut."""
    lines = (text or "").strip().split("\n")
    for line in lines[:5]:
        # Chercher une ligne avec emoji feu ou qui ressemble à un titre
        if "🔥" in line or ("20" in line and any(w in line.upper() for w in ["RAM", "DODGE", "JEEP", "TOYOTA", "FORD"])):
            return line.replace("🔥", "").strip()
    return ""


def generate_intro_only(vehicle: Dict[str, Any], max_chars: int = 250) -> str:
    """
    Génère SEULEMENT une intro accrocheuse (sans le corps de l'annonce).
    
    Utile pour ajouter une intro humaine avant un texte technique généré
    par sticker_to_ad.py.
    
    Args:
        vehicle: Dictionnaire avec les infos du véhicule
        max_chars: Limite de caractères pour l'intro
    
    Returns:
        Une intro accrocheuse de 2-3 phrases.
    """
    client = get_client()
    if not client:
        return ""
    
    v = vehicle or {}
    title = (v.get("title") or "Véhicule").strip()
    price = _vehicle_price(v)
    mileage = _vehicle_mileage(v)
    features = _get_features_text(v)
    
    # Classifier pour adapter le ton
    vehicle_type = classify(v)
    angle_config = ANGLES_PAR_TYPE.get(vehicle_type, ANGLES_PAR_TYPE["default"])
    focus = angle_config["focus"]
    
    system_prompt = f"""Tu es Daniel Giroux, vendeur automobile de la Beauce depuis 2009.

{CLICHES_INTERDITS}

📋 VÉHICULE:
- Titre: {title}
- Prix: {price}
- Kilométrage: {mileage}
- Équipements notables: {features}
- Type: {vehicle_type} (focus: {focus})

🎯 ÉCRIS UNE INTRO DE {max_chars} CARACTÈRES MAX:
- 2-3 phrases naturelles, style vendeur authentique
- Parle en "je" - c'est TOI Daniel
- Mentionne UN détail SPÉCIFIQUE
- AUCUN cliché de la liste interdite
- Pas de hashtags, pas de téléphone (ajoutés après)
- Juste l'accroche qui donne envie de lire la suite
- UTILISE 2-3 emojis pour donner de la vie: 🔥 💪 ✨ ⚡ 👀 🚗
"""

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Génère une intro accrocheuse pour ce {title}."},
            ],
            max_tokens=120,
            temperature=0.9,
        )
        
        result = (response.choices[0].message.content or "").strip()
        result = _filter_cliches(result)
        
        return _safe_trim(result, max_chars)
        
    except Exception as e:
        print(f"[ERROR intro] {e}")
        return ""


# ============================================================
# FONCTION DE TEST
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST llm.py v2.0")
    print("=" * 60)
    
    # Test sans API (vérifie juste que le code charge)
    test_vehicle = {
        "title": "RAM 1500 Big Horn 2022",
        "price": "42 995 $",
        "mileage": "35 000 km",
        "stock": "06300",
        "features": ["V8 Hemi", "4x4", "Remorquage 5000 lbs"],
    }
    
    vehicle_type = classify(test_vehicle)
    print(f"✅ Véhicule classifié: {vehicle_type}")
    
    angle = ANGLES_PAR_TYPE.get(vehicle_type, ANGLES_PAR_TYPE["default"])
    print(f"✅ Focus: {angle['focus']}")
    print(f"✅ Exemple: {random.choice(angle['exemples'])}")
    
    print("\n✅ Module chargé correctement!")
    print("   (Pour tester la génération, définir OPENAI_API_KEY)")
