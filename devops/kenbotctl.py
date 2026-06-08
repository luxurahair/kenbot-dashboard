#!/usr/bin/env python3
"""
Mini Emergent V2 - Version Stable
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
    parser.add_argument("command", choices=["kenbot", "luxura", "all", "help"], nargs='?', default="help")

    args = parser.parse_args()

    client = RenderClient()

    if args.command == "help":
        print("\n🚀 Mini Emergent V2")
        print("   kenbot     → Services Kenbot")
        print("   luxura     → Services Luxura")
        print("   all        → Tous les services")
        return

    services = client.list_services()
    print(f"\n🔄 Services Render → {args.command.upper()}\n")

    if args.command == "all":
        filtered = services
    elif args.command == "kenbot":
        filtered = [s for s in services if any(k in client.get_name(s).lower() for k in ["kenbot", "beauce", "calcauto", "facebook"])]
    else:  # luxura
        filtered = [s for s in services if "luxura" in client.get_name(s).lower()]

    for s in filtered:
        name = client.get_name(s)
        status = client.get_status(s)
        print(f"  • {name} → {status}")

if __name__ == "__main__":
    main()
