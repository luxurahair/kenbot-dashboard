#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de détection du footer pour éviter les doublons.
Usage: python tests/test_footer_detection.py
"""

import sys
sys.path.insert(0, '..')

# Marqueurs qui indiquent qu'un footer est déjà présent
FOOTER_MARKERS = [
    "418-222-3939",
    "daniel giroux",
    "j'accepte les échanges",
    "écris-moi en privé",
    "#danielgiroux",
]

def has_footer(text: str) -> bool:
    """Détecte si un footer est déjà présent dans le texte."""
    low = (text or "").lower()
    matches = sum(1 for m in FOOTER_MARKERS if m in low)
    return matches >= 2

def test_footer_detection():
    """Tests unitaires pour la détection de footer."""
    
    # Cas 1: Texte SANS footer
    text_no_footer = """
🔥 RAM 1500 Classic SLT 2022 🔥

💥 34 995 $ 💥
📊 Kilométrage : 56 000 km

✨ ÉQUIPEMENTS
■ V8 Hemi
■ 4x4
■ Cabine d'équipe
"""
    assert not has_footer(text_no_footer), "❌ ÉCHEC: Texte sans footer détecté comme ayant un footer"
    print("✅ Test 1 OK: Texte sans footer correctement détecté")
    
    # Cas 2: Texte AVEC footer complet
    text_with_footer = """
🔥 RAM 1500 Classic SLT 2022 🔥

💥 34 995 $ 💥

🔁 J'accepte les échanges : 🚗 auto • 🏍️ moto
📞 Daniel Giroux — 418-222-3939
#DanielGiroux #Beauce
"""
    assert has_footer(text_with_footer), "❌ ÉCHEC: Texte avec footer non détecté"
    print("✅ Test 2 OK: Texte avec footer correctement détecté")
    
    # Cas 3: Texte avec footer PARTIEL (juste téléphone)
    text_partial = """
🔥 Jeep Wrangler 2021 🔥
Appelle-moi: 418-222-3939
"""
    # Un seul marqueur = pas assez pour être sûr
    result = has_footer(text_partial)
    print(f"⚠️  Test 3: Texte partiel (1 marqueur) -> has_footer={result}")
    
    # Cas 4: Texte avec 2 marqueurs (seuil minimum)
    text_two_markers = """
🔥 Dodge Charger 2020 🔥
📞 Daniel Giroux
418-222-3939
"""
    assert has_footer(text_two_markers), "❌ ÉCHEC: 2 marqueurs devraient suffire"
    print("✅ Test 4 OK: 2 marqueurs = footer détecté")
    
    # Cas 5: Double footer (le problème actuel)
    text_double_footer = """
🔥 RAM 1500 2022 🔥

🔁 J'accepte les échanges
📞 Daniel Giroux — 418-222-3939

🔁 J'accepte les échanges : 🚗 auto • 🏍️ moto
📸 Envoie-moi les photos
📞 Daniel Giroux — 418-222-3939
#DanielGiroux
"""
    assert has_footer(text_double_footer), "❌ ÉCHEC: Double footer non détecté"
    print("✅ Test 5 OK: Double footer correctement détecté")
    
    print("\n" + "="*50)
    print("✅ TOUS LES TESTS PASSENT!")
    print("="*50)

if __name__ == "__main__":
    test_footer_detection()
