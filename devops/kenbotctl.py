#!/usr/bin/env python3
"""
Mini Emergent V2 - Version Puissante & Simple
"""

import argparse
import sys
import os
from dotenv import load_dotenv

load_dotenv('.secrets.env')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_client import RenderClient

def main():
    parser = argparse.ArgumentParser(description="Mini Emergent V2")
    parser.add_argument("command", choices=["kenbot", "luxura", "all", "status", "restart", "help"], nargs='?', default="help")
    parser.add_argument("--service", help="Nom du service à redémarrer (ex: kenbot-runner)")

    args = parser.parse_args()

    client = RenderClient()

    if args.command == "help":
        print("\n🚀 Mini Emergent V2 - Commandes simples :")
        print("   kenbot          → Voir seulement Kenbot")
        print("   luxura          → Voir seulement Luxura")
        print("   all             → Voir tous les services")
        print("   status          → Diagnostic complet")
        print("   restart --service NOM   → Redémarrer un service")
        return

    if args.command == "status":
        print("🔍 Diagnostic complet en cours...")
        client.list_services()
        print("✅ Système OK")
        return

    if args.command == "restart" and args.service:
        print(f"🔄 Redémarrage de {args.service}...")
        # On ajoutera la vraie fonction restart bientôt
        print("⏳ Fonction restart en cours de création...")
        return

    # Liste filtrée
    services = client.list_services()
    print(f"\n🔄 Services Render → {args.command.upper()}\n")

    keywords = {
        "kenbot": ["kenbot", "beauce", "calcauto", "facebook"],
        "luxura": ["luxura"],
        "all": [""]
    }

    kw_list = keywords.get(args.command, [""])
    filtered = [s for s in services if any(k in client.get_name(s).lower() for k in kw_list if k)]

    for s in filtered:
        name = client.get_name(s)
        status = client.get_status(s)
        print(f"  • {name} → {status}")

if __name__ == "__main__":
    main()
