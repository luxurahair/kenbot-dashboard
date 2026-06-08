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
    parser.add_argument("command", choices=["kenbot", "luxura", "calcauto", "all", "help"], nargs='?', default="help")

    args = parser.parse_args()

    client = RenderClient()

    if args.command == "help":
        print("\n🚀 Mini Emergent V2")
        print("   kenbot     → Services Kenbot (dashboard, beauce, news, FB regen, competitors)")
        print("   luxura     → Services Luxura (multi-tape, itip, genius, halo)")
        print("   calcauto   → Services CalcAuto AiPro (OCR scan + master codes)")
        print("   all        → Tous les services")
        return

    services = client.list_services()
    print(f"\n🔄 Services Render → {args.command.upper()}\n")

    def name_of(s):
        return client.get_name(s).lower()

    if args.command == "all":
        filtered = services
    elif args.command == "calcauto":
        filtered = [s for s in services if any(k in name_of(s) for k in ["calcauto", "aipro"])]
    elif args.command == "kenbot":
        # 2026-06-08 : CalcAuto séparé dans son propre contexte → exclu d'ici
        filtered = [
            s for s in services
            if any(k in name_of(s) for k in ["kenbot", "beauce", "facebook"])
            and not any(k in name_of(s) for k in ["calcauto", "aipro"])
        ]
    else:  # luxura
        filtered = [s for s in services if "luxura" in name_of(s)]

    for s in filtered:
        name = client.get_name(s)
        status = client.get_status(s)
        print(f"  • {name} → {status}")

if __name__ == "__main__":
    main()
