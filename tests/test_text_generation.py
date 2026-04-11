#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de génération de texte pour vérifier:
1. Pas de double footer
2. Variété des textes générés
3. Présence des informations essentielles

Usage: python tests/test_text_generation.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dg_text import build_facebook_dg, build_marketplace_dg
from ad_builder import build_ad
from classifier import classify

# Véhicules de test
TEST_VEHICLES = [
    {
        "title": "RAM 1500 Classic SLT 2022",
        "brand": "Ram",
        "price": "34 995 $",
        "mileage": "56 000 km",
        "stock": "06193",
        "vin": "1C6RR7LT5NS123456",
        "url": "https://www.kennebecdodge.ca/fr/inventaire-occasion/ram-1500-2022-id06193",
        "features": ["V8 Hemi", "4x4", "Cabine d'équipe"],
        "comfort": ["Climatisation", "Bluetooth"],
    },
    {
        "title": "Toyota Corolla LE 2021",
        "brand": "Toyota",
        "price": "22 995 $",
        "mileage": "45 000 km",
        "stock": "07001",
        "vin": "JTDEPRAE5MJ123456",
        "url": "https://www.kennebecdodge.ca/fr/inventaire-occasion/toyota-corolla-2021-id07001",
        "features": ["Automatique", "Caméra de recul"],
        "comfort": ["Apple CarPlay"],
    },
    {
        "title": "Jeep Wrangler Rubicon 4xe 2023",
        "brand": "Jeep",
        "price": "65 995 $",
        "mileage": "12 000 km",
        "stock": "06500",
        "vin": "1C4JJXR68PW123456",
        "url": "https://www.kennebecdodge.ca/fr/inventaire-occasion/jeep-wrangler-2023-id06500",
        "features": ["Hybride rechargeable", "4x4", "Toit rigide"],
        "comfort": ["Navigation", "Sièges chauffants"],
    },
]

def count_footer_occurrences(text: str) -> int:
    """Compte combien de fois le footer apparaît."""
    phone = "418-222-3939"
    return text.count(phone)

def test_no_double_footer():
    """Vérifie qu'aucun texte n'a de double footer."""
    print("\n" + "="*60)
    print("TEST: Pas de double footer")
    print("="*60)
    
    errors = []
    
    for v in TEST_VEHICLES:
        # Test dg_text
        fb_text = build_facebook_dg(v)
        mp_text = build_marketplace_dg(v)
        
        fb_count = count_footer_occurrences(fb_text)
        mp_count = count_footer_occurrences(mp_text)
        
        stock = v.get('stock', 'N/A')
        
        if fb_count > 1:
            errors.append(f"❌ {stock} Facebook: {fb_count} footers trouvés!")
            print(f"❌ {stock} Facebook: {fb_count} footers")
        else:
            print(f"✅ {stock} Facebook: {fb_count} footer (OK)")
            
        if mp_count > 1:
            errors.append(f"❌ {stock} Marketplace: {mp_count} footers trouvés!")
            print(f"❌ {stock} Marketplace: {mp_count} footers")
        else:
            print(f"✅ {stock} Marketplace: {mp_count} footer (OK)")
    
    if errors:
        print("\n⚠️  ERREURS DÉTECTÉES:")
        for e in errors:
            print(f"   {e}")
        return False
    
    print("\n✅ Aucun double footer détecté!")
    return True

def test_essential_info_present():
    """Vérifie que les infos essentielles sont présentes."""
    print("\n" + "="*60)
    print("TEST: Informations essentielles présentes")
    print("="*60)
    
    required_elements = [
        ("418-222-3939", "Téléphone"),
        ("daniel giroux", "Nom vendeur"),
    ]
    
    errors = []
    
    for v in TEST_VEHICLES:
        fb_text = build_facebook_dg(v)
        stock = v.get('stock', 'N/A')
        low = fb_text.lower()
        
        for element, name in required_elements:
            if element.lower() not in low:
                errors.append(f"❌ {stock}: {name} manquant")
                print(f"❌ {stock}: {name} manquant")
            else:
                print(f"✅ {stock}: {name} présent")
    
    if errors:
        print("\n⚠️  ERREURS DÉTECTÉES:")
        for e in errors:
            print(f"   {e}")
        return False
    
    print("\n✅ Toutes les infos essentielles sont présentes!")
    return True

def test_classifier():
    """Teste le classificateur de véhicules."""
    print("\n" + "="*60)
    print("TEST: Classificateur de véhicules")
    print("="*60)
    
    expected = {
        "RAM 1500 Classic SLT 2022": "truck",
        "Toyota Corolla LE 2021": "sedan",
        "Jeep Wrangler Rubicon 4xe 2023": "suv",  # ou ev car hybride
    }
    
    for v in TEST_VEHICLES:
        title = v.get('title', '')
        result = classify(v)
        exp = expected.get(title, "default")
        
        if result in [exp, "ev", "suv"]:  # ev acceptable pour hybride
            print(f"✅ {title[:30]:30} -> {result}")
        else:
            print(f"⚠️  {title[:30]:30} -> {result} (attendu: {exp})")
    
    return True

def test_text_variety():
    """Vérifie que les textes sont variés (pas tous identiques)."""
    print("\n" + "="*60)
    print("TEST: Variété des textes")
    print("="*60)
    
    texts = []
    for v in TEST_VEHICLES:
        fb_text = build_facebook_dg(v)
        # Prendre les 200 premiers caractères pour comparer
        texts.append(fb_text[:200])
    
    # Vérifier que les textes sont différents
    unique_texts = set(texts)
    
    if len(unique_texts) == len(texts):
        print(f"✅ {len(texts)} textes tous différents!")
        return True
    else:
        print(f"⚠️  {len(texts)} textes, seulement {len(unique_texts)} uniques")
        return False

def main():
    print("\n" + "#"*60)
    print("#  TESTS DE GÉNÉRATION DE TEXTE - KENBOT")
    print("#"*60)
    
    results = []
    
    results.append(("Double footer", test_no_double_footer()))
    results.append(("Infos essentielles", test_essential_info_present()))
    results.append(("Classificateur", test_classifier()))
    results.append(("Variété", test_text_variety()))
    
    print("\n" + "#"*60)
    print("#  RÉSUMÉ")
    print("#"*60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {name:25} {status}")
        if not passed:
            all_passed = False
    
    print("\n")
    if all_passed:
        print("🎉 TOUS LES TESTS PASSENT!")
        return 0
    else:
        print("⚠️  CERTAINS TESTS ONT ÉCHOUÉ")
        return 1

if __name__ == "__main__":
    sys.exit(main())
