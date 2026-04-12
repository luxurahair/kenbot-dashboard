# -*- coding: utf-8 -*-
"""
footer_utils.py - Module centralisé pour la gestion du footer Daniel Giroux.

RÈGLE D'OR: Le footer ne doit être ajouté qu'UNE SEULE FOIS, à UN SEUL ENDROIT.
Ce module est la source de vérité pour:
1. Détecter si un footer existe déjà
2. Ajouter un footer si nécessaire
3. Générer le footer standard

Usage:
    from footer_utils import has_footer, add_footer_if_missing, get_dealer_footer
"""

from __future__ import annotations
from typing import List, Optional

# ============================================================
# CONFIGURATION DU FOOTER
# ============================================================

DEALER_NAME = "Daniel Giroux"
DEALER_PHONE = "418-222-3939"
DEALER_TITLE = "Conseiller expert"
DEALER_EXPERIENCE = "20 ans"
DEALER_DEALERSHIP = "Kennebec Dodge Chrysler"
DEALER_LOCATION = "Saint-Georges, Beauce"

# Marqueurs qui indiquent qu'un footer est déjà présent
FOOTER_MARKERS = [
    "418-222-3939",
    "418 222 3939",
    "daniel giroux",
    "conseiller expert",
    "j'accepte les échanges",
    "j'accepte les echanges",
    "#danielgiroux",
    "[[dg_footer]]",
]

FOOTER_MARKER_THRESHOLD = 1


# ============================================================
# DÉTECTION DE FOOTER
# ============================================================

def has_footer(text: str) -> bool:
    """
    Détecte si un footer Daniel Giroux est déjà présent dans le texte.
    
    Returns:
        True si un footer est détecté, False sinon.
    """
    if not text:
        return False
    
    low = text.lower()
    
    # Vérification rapide: le téléphone est unique et obligatoire
    if DEALER_PHONE in text or "418 222 3939" in text:
        return True
    
    # Vérification secondaire: compter les marqueurs
    matches = sum(1 for marker in FOOTER_MARKERS if marker in low)
    return matches >= FOOTER_MARKER_THRESHOLD


def count_footer_occurrences(text: str) -> int:
    """
    Compte combien de fois le footer semble apparaître.
    Utile pour détecter les doubles footers.
    
    Returns:
        Nombre d'occurrences du téléphone (indicateur principal).
    """
    if not text:
        return 0
    return text.count(DEALER_PHONE) + text.count("418 222 3939")


def has_double_footer(text: str) -> bool:
    """
    Détecte si un texte a un DOUBLE footer (bug à corriger).
    
    Returns:
        True si double footer détecté.
    """
    return count_footer_occurrences(text) > 1


# ============================================================
# GÉNÉRATION DU FOOTER
# ============================================================

def get_dealer_footer(
    include_echanges: bool = True,
    include_hashtags: bool = True,
    hashtags: Optional[List[str]] = None,
) -> str:
    """
    Signature professionnelle Daniel Giroux — humaine, chaleureuse, experte.
    """
    lines = []

    # Signature pro
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(f"🙋‍♂️ {DEALER_NAME}")
    lines.append(f"🏆 {DEALER_TITLE} depuis près de {DEALER_EXPERIENCE}")
    lines.append(f"🏢 {DEALER_DEALERSHIP}")
    lines.append(f"📍 {DEALER_LOCATION}")
    lines.append("")
    lines.append(f"📞 {DEALER_PHONE} — appelez-moi, ça me fait plaisir!")
    lines.append(f"💬 Ou écrivez-moi en privé ici sur Messenger")
    lines.append("")

    if include_echanges:
        lines.append("🔄 J'accepte les échanges :")
        lines.append("🚗 Auto  🏍️ Moto  🛥️ Bateau  🛻 VTT  🏁 Côte-à-côte")
        lines.append("📸 Envoyez-moi les photos + infos de votre véhicule")
        lines.append("    (année, km, paiement restant) → je vous reviens rapidement!")
        lines.append("")

    lines.append("🤝 Financement disponible — on trouve une solution ensemble.")
    lines.append("")

    if include_hashtags:
        if hashtags:
            lines.append(" ".join(hashtags))
        else:
            lines.append("#DanielGiroux #ConseillerExpert #KennebecDodge #Beauce #SaintGeorges #Québec")

    return "\n".join(lines).strip()


def get_minimal_footer() -> str:
    """
    Retourne un footer minimal (juste le téléphone).
    Utilisé quand on veut s'assurer que le contact est présent.
    """
    return f"📞 {DEALER_NAME} {DEALER_PHONE}"


# ============================================================
# AJOUT INTELLIGENT DU FOOTER
# ============================================================

def add_footer_if_missing(
    text: str,
    footer: Optional[str] = None,
    force_minimal: bool = False,
) -> str:
    """
    Ajoute le footer UNIQUEMENT s'il n'est pas déjà présent.
    
    C'est LA fonction à utiliser partout pour éviter les doubles footers.
    
    Args:
        text: Le texte à traiter
        footer: Footer personnalisé (sinon footer standard)
        force_minimal: Si True, utilise le footer minimal
    
    Returns:
        Le texte avec footer (ajouté ou non selon détection).
    """
    text = (text or "").strip()
    
    if not text:
        return text
    
    # Si footer déjà présent, ne rien faire
    if has_footer(text):
        return text
    
    # Choisir le footer à ajouter
    if footer:
        footer_to_add = footer
    elif force_minimal:
        footer_to_add = get_minimal_footer()
    else:
        footer_to_add = get_dealer_footer()
    
    return f"{text}\n\n{footer_to_add}".strip()


def ensure_contact_present(text: str) -> str:
    """
    S'assure que le numéro de téléphone est présent.
    N'ajoute que le minimum si absent.
    
    C'est une version "légère" de add_footer_if_missing.
    """
    text = (text or "").strip()
    
    if not text:
        return text
    
    # Si le téléphone est déjà là, rien à faire
    if DEALER_PHONE in text or "418 222 3939" in text:
        return text
    
    # Ajouter seulement le contact minimal
    return f"{text}\n\n{get_minimal_footer()}".strip()


# ============================================================
# NETTOYAGE
# ============================================================

def remove_footer_marker(text: str) -> str:
    """
    Retire le marqueur [[DG_FOOTER]] s'il est présent.
    Ce marqueur est utilisé pour éviter les doublons mais ne doit pas
    apparaître dans le texte final.
    """
    return (text or "").replace("[[DG_FOOTER]]", "").replace("[[dg_footer]]", "").strip()


def clean_double_footer(text: str) -> str:
    """
    Tente de nettoyer un double footer.
    
    ⚠️ À utiliser avec précaution - préférer prévenir que guérir.
    """
    if not has_double_footer(text):
        return text
    
    # Stratégie simple: trouver la dernière occurrence du téléphone
    # et garder tout ce qui est avant + cette dernière occurrence
    
    # TODO: Implémenter si nécessaire
    # Pour l'instant, on retourne le texte tel quel
    return text


# ============================================================
# HELPERS POUR HASHTAGS
# ============================================================

def smart_hashtags(
    make: str = "",
    model: str = "",
    title: str = "",
    event: str = "NEW",
) -> List[str]:
    """
    Génère des hashtags intelligents basés sur le véhicule.
    """
    tags = ["#DanielGiroux", "#Beauce", "#Quebec", "#SaintGeorges"]
    
    # Event
    if event == "PRICE_CHANGED":
        tags.insert(0, "#BaisseDePrix")
    elif event == "NEW":
        tags.insert(0, "#NouvelArrivage")
    
    # Marque
    text_blob = f"{make} {model} {title}".lower()
    
    brand_tags = {
        "ram": ["#RAM", "#Truck"],
        "jeep": ["#Jeep", "#4x4"],
        "dodge": ["#Dodge"],
        "chrysler": ["#Chrysler"],
        "toyota": ["#Toyota"],
        "honda": ["#Honda"],
        "ford": ["#Ford"],
        "chevrolet": ["#Chevrolet", "#Chevy"],
        "gmc": ["#GMC"],
    }
    
    for brand, btags in brand_tags.items():
        if brand in text_blob:
            tags = btags + tags
            break
    
    # Caractéristiques
    if "4x4" in text_blob or "awd" in text_blob or "4wd" in text_blob:
        if "#4x4" not in tags:
            tags.append("#4x4")
    
    if "hybrid" in text_blob or "hybride" in text_blob:
        tags.append("#Hybride")
    
    # Dédoublonner
    seen = set()
    unique = []
    for t in tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)
    
    return unique[:12]


# ============================================================
# TESTS INTÉGRÉS
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST footer_utils.py")
    print("=" * 60)
    
    # Test 1: Détection sans footer
    text_no_footer = "🔥 RAM 1500 2022 🔥\n\n💥 34 995 $ 💥"
    assert not has_footer(text_no_footer), "FAIL: Faux positif"
    print("✅ Test 1: Texte sans footer détecté correctement")
    
    # Test 2: Détection avec footer
    text_with_footer = "🔥 RAM 1500 🔥\n\n📞 Daniel Giroux — 418-222-3939"
    assert has_footer(text_with_footer), "FAIL: Faux négatif"
    print("✅ Test 2: Texte avec footer détecté correctement")
    
    # Test 3: Ajout de footer
    result = add_footer_if_missing(text_no_footer)
    assert has_footer(result), "FAIL: Footer non ajouté"
    assert count_footer_occurrences(result) == 1, "FAIL: Double footer"
    print("✅ Test 3: Footer ajouté correctement")
    
    # Test 4: Pas de double ajout
    result2 = add_footer_if_missing(result)
    assert count_footer_occurrences(result2) == 1, "FAIL: Double footer après 2e appel"
    print("✅ Test 4: Pas de double footer après 2e appel")
    
    # Test 5: Double footer détecté
    double = text_with_footer + "\n\n📞 Daniel Giroux — 418-222-3939"
    assert has_double_footer(double), "FAIL: Double footer non détecté"
    print("✅ Test 5: Double footer détecté")
    
    print("\n" + "=" * 60)
    print("🎉 TOUS LES TESTS PASSENT!")
    print("=" * 60)
