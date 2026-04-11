#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test du flux COMPLET de génération pour détecter le double footer.
Simule ce que fait runner_cron_prod.py

Usage: python tests/test_full_pipeline.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dg_text import build_facebook_dg
from ad_builder import build_ad
from text_engine_client import ensure_single_footer, _dealer_footer

# Simuler le footer de runner_cron_prod.py
def _ensure_contact_footer_runner(text: str) -> str:
    """Copie de la fonction de runner_cron_prod.py"""
    txt = (text or "").strip()
    must_have = "418-222-3939"
    if must_have in txt:
        return txt
    footer = "\n\n📞 Daniel Giroux 418-222-3939"
    return (txt + footer).strip()

def count_phone(text: str) -> int:
    """Compte les occurrences du téléphone."""
    return text.count("418-222-3939")

def count_echanges(text: str) -> int:
    """Compte les occurrences de 'J'accepte les échanges'."""
    return text.lower().count("j'accepte les échanges")

def test_stellantis_flow():
    """
    Test du flux Stellantis (sticker_to_ad → ad_builder → runner).
    C'est ici que le double footer apparaît!
    """
    print("\n" + "="*60)
    print("TEST: Flux Stellantis (Window Sticker)")
    print("="*60)
    
    # Simuler les options extraites d'un Window Sticker
    options = [
        {"title": "ENSEMBLE REMORQUAGE", "details": ["Attache classe IV", "Contrôleur intégré"]},
        {"title": "GROUPE TECHNOLOGIE", "details": ["Écran 12 pouces", "Navigation"]},
    ]
    
    # Étape 1: ad_builder.build_ad (ajoute un footer partiel)
    text_step1 = build_ad(
        title="RAM 1500 Big Horn 2022",
        price="42 995 $",
        mileage="35 000 km",
        stock="06300",
        vin="1C6RR7LT5NS123456",
        options=options,
        vehicle_url="https://www.kennebecdodge.ca/vehicle/06300",
    )
    
    phone_count_1 = count_phone(text_step1)
    echanges_count_1 = count_echanges(text_step1)
    
    print(f"\n📝 Après ad_builder.build_ad:")
    print(f"   - Téléphone: {phone_count_1}x")
    print(f"   - 'J'accepte les échanges': {echanges_count_1}x")
    
    # Étape 2: runner ajoute _ensure_contact_footer
    text_step2 = _ensure_contact_footer_runner(text_step1)
    
    phone_count_2 = count_phone(text_step2)
    echanges_count_2 = count_echanges(text_step2)
    
    print(f"\n📝 Après _ensure_contact_footer (runner):")
    print(f"   - Téléphone: {phone_count_2}x")
    print(f"   - 'J'accepte les échanges': {echanges_count_2}x")
    
    # Vérifier le résultat
    if phone_count_2 > 1:
        print(f"\n❌ PROBLÈME: Double téléphone détecté!")
        return False
    elif echanges_count_2 > 1:
        print(f"\n❌ PROBLÈME: Double 'échanges' détecté!")
        return False
    else:
        print(f"\n✅ OK: Pas de double footer dans le flux Stellantis")
        return True

def test_non_stellantis_flow():
    """
    Test du flux non-Stellantis (text_engine_client → runner).
    """
    print("\n" + "="*60)
    print("TEST: Flux non-Stellantis (dg_text)")
    print("="*60)
    
    vehicle = {
        "title": "Toyota RAV4 XLE 2021",
        "price": "32 995 $",
        "mileage": "28 000 km",
        "stock": "07100",
        "vin": "JTMP1RFV5MD123456",
        "url": "https://www.kennebecdodge.ca/vehicle/07100",
    }
    
    # Étape 1: dg_text génère le texte
    text_step1 = build_facebook_dg(vehicle)
    
    phone_count_1 = count_phone(text_step1)
    echanges_count_1 = count_echanges(text_step1)
    
    print(f"\n📝 Après build_facebook_dg:")
    print(f"   - Téléphone: {phone_count_1}x")
    print(f"   - 'J'accepte les échanges': {echanges_count_1}x")
    
    # Étape 2: text_engine_client ajoute ensure_single_footer
    footer = _dealer_footer(vehicle, "NEW")
    text_step2 = ensure_single_footer(text_step1, footer)
    
    phone_count_2 = count_phone(text_step2)
    echanges_count_2 = count_echanges(text_step2)
    
    print(f"\n📝 Après ensure_single_footer (text_engine_client):")
    print(f"   - Téléphone: {phone_count_2}x")
    print(f"   - 'J'accepte les échanges': {echanges_count_2}x")
    
    # Étape 3: runner ajoute _ensure_contact_footer
    text_step3 = _ensure_contact_footer_runner(text_step2)
    
    phone_count_3 = count_phone(text_step3)
    echanges_count_3 = count_echanges(text_step3)
    
    print(f"\n📝 Après _ensure_contact_footer (runner):")
    print(f"   - Téléphone: {phone_count_3}x")
    print(f"   - 'J'accepte les échanges': {echanges_count_3}x")
    
    # Vérifier le résultat
    if phone_count_3 > 1:
        print(f"\n❌ PROBLÈME: Double téléphone détecté!")
        return False
    elif echanges_count_3 > 1:
        print(f"\n❌ PROBLÈME: Double 'échanges' détecté!")
        return False
    else:
        print(f"\n✅ OK: Pas de double footer dans le flux non-Stellantis")
        return True

def test_sticker_to_ad_standalone():
    """
    Test de sticker_to_ad.build_ad qui ajoute son propre footer.
    """
    print("\n" + "="*60)
    print("TEST: sticker_to_ad.build_ad standalone")
    print("="*60)
    
    try:
        from sticker_to_ad import build_ad as sticker_build_ad
    except ImportError:
        print("⚠️  Impossible d'importer sticker_to_ad")
        return True
    
    options = [
        {"title": "ENSEMBLE 4X4", "details": ["Différentiel arrière", "Plaque de protection"]},
    ]
    
    text = sticker_build_ad(
        title="Jeep Wrangler Rubicon 2023",
        price="65 995 $",
        mileage="8 000 km",
        stock="06400",
        vin="1C4JJXR68PW123456",
        options=options,
    )
    
    phone_count = count_phone(text)
    echanges_count = count_echanges(text)
    
    print(f"\n📝 sticker_to_ad.build_ad:")
    print(f"   - Téléphone: {phone_count}x")
    print(f"   - 'J'accepte les échanges': {echanges_count}x")
    
    if phone_count > 1:
        print(f"\n❌ PROBLÈME: Double téléphone dans sticker_to_ad!")
        return False
    elif echanges_count > 1:
        print(f"\n❌ PROBLÈME: Double 'échanges' dans sticker_to_ad!")
        return False
    else:
        print(f"\n✅ OK: Pas de double footer dans sticker_to_ad")
        return True

def main():
    print("\n" + "#"*60)
    print("#  TEST DU FLUX COMPLET - DÉTECTION DOUBLE FOOTER")
    print("#"*60)
    
    results = []
    
    results.append(("Flux Stellantis", test_stellantis_flow()))
    results.append(("Flux non-Stellantis", test_non_stellantis_flow()))
    results.append(("sticker_to_ad standalone", test_sticker_to_ad_standalone()))
    
    print("\n" + "#"*60)
    print("#  RÉSUMÉ")
    print("#"*60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {name:30} {status}")
        if not passed:
            all_passed = False
    
    print("\n")
    if all_passed:
        print("🎉 TOUS LES FLUX SONT OK!")
        return 0
    else:
        print("⚠️  PROBLÈMES DÉTECTÉS - CORRECTION NÉCESSAIRE")
        return 1

if __name__ == "__main__":
    sys.exit(main())
