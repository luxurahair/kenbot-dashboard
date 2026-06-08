#!/usr/bin/env python3
"""
Mini Emergent V3 - Version Puissante & Stable
"""

import argparse
import sys
import os
from dotenv import load_dotenv

load_dotenv('.secrets.env')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_client import RenderClient

def main():
    parser = argparse.ArgumentParser(description="Mini Emergent V3")
    parser.add_argument("command", choices=["kenbot", "luxura", "calcauto", "all", "restart", "env-list", "snapshot", "help"], nargs='?', default="help")
    parser.add_argument("--service", help="Nom du service (ex: kenbot-runner)")
    parser.add_argument("--key", help="Clé à modifier (avec env-set)")
    parser.add_argument("--value", help="Nouvelle valeur")

    args = parser.parse_args()

    client = RenderClient()

    if args.command == "help":
        print("\n🚀 Mini Emergent V3 - Commandes")
        print("   kenbot          → Services Kenbot")
        print("   luxura          → Services Luxura")
        print("   calcauto        → Services CalcAuto")
        print("   all             → Tous les services")
        print("   restart --service NOM")
        print("   env-list --service NOM")
        print("   snapshot")
        return

    # Commandes avancées
    if args.command == "restart" and args.service:
        print(f"🔄 Redémarrage de {args.service}...")
        # On implémentera la vraie fonction plus tard
        print("✅ Commande restart reçue (implémentation en cours)")
        return

    if args.command == "env-list" and args.service:
        print(f"📋 Variables d'environnement pour {args.service}...")
        print("✅ Commande env-list reçue (implémentation en cours)")
        return

    if args.command == "snapshot":
        print("💾 Création d'un snapshot complet des env vars Render...")
        print("✅ Snapshot demandé (fonction en cours de développement)")
        return

    # Liste des services
    services = client.list_services()
    print(f"\n🔄 Services Render → {args.command.upper()}\n")

    filters = {
        "kenbot": ["kenbot", "beauce", "facebook"],
        "luxura": ["luxura"],
        "calcauto": ["calcauto", "aipro"],
        "all": [""]
    }

    kw_list = filters.get(args.command, [""])
    filtered = [s for s in services if any(k in client.get_name(s).lower() for k in kw_list if k)]

    for s in filtered:
        name = client.get_name(s)
        status = client.get_status(s)
        print(f"  • {name} → {status}")

if __name__ == "__main__":
    main()
