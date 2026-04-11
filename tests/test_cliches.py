#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test pour détecter les clichés répétitifs dans les textes générés.
Usage: python tests/test_cliches.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Liste des clichés à bannir
CLICHES_INTERDITS = [
    "sillonner les routes",
    "sillonner la beauce",
    "parfait pour l'hiver",
    "parfait pour l hiver",
    "prêt à conquérir",
    "pret a conquerir",
    "conçu pour affronter",
    "concu pour affronter",
    "idéal pour les aventures",
    "ideal pour les aventures",
    "n'attend plus que toi",
    "n attend plus que toi",
    "ce bijou",
    "cette merveille",
    "cette beauté",
    "cette beaute",
    "viens le voir",
    "viens la voir",
    "véritable machine",
    "veritable machine",
    "monstre de puissance",
    "bête de route",
    "bete de route",
]

def detect_cliches(text: str) -> list:
    """Retourne la liste des clichés trouvés dans le texte."""
    low = (text or "").lower()
    found = []
    for cliche in CLICHES_INTERDITS:
        if cliche in low:
            found.append(cliche)
    return found

def test_sample_texts():
    """Teste quelques exemples de textes."""
    print("\n" + "="*60)
    print("TEST: Détection de clichés")
    print("="*60)
    
    # Texte MAUVAIS (avec clichés)
    bad_text = """
🔥 RAM 1500 2022 🔥

Ce bijou est parfait pour l'hiver québécois!
Prêt à conquérir les routes de la Beauce.
Cette merveille n'attend plus que toi!

📞 418-222-3939
"""
    
    # Texte BON (sans clichés)
    good_text = """
🔥 RAM 1500 2022 🔥

V8 Hemi, 56 000 km, 4x4 - un truck qui a fait ses preuves.
Entretien régulier chez le concessionnaire.
Financement disponible sur place.

📞 Daniel Giroux — 418-222-3939
"""
    
    # Test texte mauvais
    cliches = detect_cliches(bad_text)
    print(f"\nTexte MAUVAIS - Clichés trouvés: {len(cliches)}")
    for c in cliches:
        print(f"   ❌ '{c}'")
    
    # Test texte bon
    cliches = detect_cliches(good_text)
    print(f"\nTexte BON - Clichés trouvés: {len(cliches)}")
    if cliches:
        for c in cliches:
            print(f"   ❌ '{c}'")
    else:
        print("   ✅ Aucun cliché!")
    
    return len(detect_cliches(good_text)) == 0

def test_generated_texts():
    """Teste les textes générés par dg_text."""
    print("\n" + "="*60)
    print("TEST: Clichés dans textes générés")
    print("="*60)
    
    try:
        from dg_text import build_facebook_dg
    except ImportError:
        print("⚠️  Impossible d'importer dg_text")
        return True
    
    test_vehicles = [
        {"title": "RAM 1500 2022", "price": "34 995 $", "mileage": "56 000 km", "stock": "06193"},
        {"title": "Toyota Corolla 2021", "price": "22 995 $", "mileage": "45 000 km", "stock": "07001"},
        {"title": "Jeep Wrangler 2023", "price": "65 995 $", "mileage": "12 000 km", "stock": "06500"},
    ]
    
    total_cliches = 0
    
    for v in test_vehicles:
        text = build_facebook_dg(v)
        cliches = detect_cliches(text)
        stock = v.get('stock', 'N/A')
        
        if cliches:
            print(f"\n❌ {stock} ({v['title'][:25]}) - {len(cliches)} clichés:")
            for c in cliches:
                print(f"      '{c}'")
            total_cliches += len(cliches)
        else:
            print(f"✅ {stock} ({v['title'][:25]}) - Aucun cliché")
    
    print(f"\n{'='*60}")
    print(f"TOTAL: {total_cliches} clichés trouvés")
    
    if total_cliches == 0:
        print("✅ Aucun cliché dans les textes générés!")
        return True
    else:
        print("⚠️  Des clichés ont été détectés")
        return False

def main():
    print("\n" + "#"*60)
    print("#  TEST DE DÉTECTION DE CLICHÉS")
    print("#"*60)
    
    r1 = test_sample_texts()
    r2 = test_generated_texts()
    
    print("\n")
    if r1 and r2:
        print("🎉 TESTS OK!")
        return 0
    else:
        print("⚠️  AMÉLIORATIONS NÉCESSAIRES")
        return 1

if __name__ == "__main__":
    sys.exit(main())
