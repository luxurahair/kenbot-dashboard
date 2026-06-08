#!/usr/bin/env python3
"""
Mini Emergent v1.0 - Accès Direct
"""

import argparse
import sys
import os
from dotenv import load_dotenv

load_dotenv('.secrets.env')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_client import RenderClient

def main():
    parser = argparse.ArgumentParser(description="Mini Emergent - Accès Direct")
    parser.add_argument("command", choices=["kenbot", "luxura", "all", "help"], nargs='?', default="help")
    
    args = parser.parse_args()

    client = RenderClient()

    if args.command == "help":
        print("\n🚀 Commandes directes :")
        print("   python3 devops/kenbotctl.py kenbot")
        print("   python3 devops/kenbotctl.py luxura")
        print("   python3 devops/kenbotctl.py all")
        return

    services = client.list_services()
    
    if args.command == "all":
        print(f"\n🔄 TOUS les services Render ({len(services)})\n")
        for s in services:
            name = client.get_name(s)
            status = client.get_status(s)
            print(f"  • {name} → {status}")
    elif args.command == "kenbot":
        print(f"\n🔄 Services KENBOT\n")
        for s in services:
            name = client.get_name(s)
            if "kenbot" in name.lower() or "beauce" in name.lower() or "calcauto" in name.lower() or "facebook" in name.lower():
                print(f"  • {name} → {client.get_status(s)}")
    elif args.command == "luxura":
        print(f"\n🔄 Services LUXURA\n")
        for s in services:
            name = client.get_name(s)
            if "luxura" in name.lower():
                print(f"  • {name} → {client.get_status(s)}")

if __name__ == "__main__":
    main()
