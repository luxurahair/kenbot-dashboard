#!/usr/bin/env python3
"""
Mini Emergent v1.0 - Version simplifiée
"""

import argparse
import sys
import os
from dotenv import load_dotenv

load_dotenv('.secrets.env')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_client import RenderClient

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["render-list", "help"], nargs='?', default="help")
    parser.add_argument("--project", choices=["kenbot", "luxura"], default="kenbot")
    args = parser.parse_args()

    if args.command == "help":
        print("Usage: python devops/kenbotctl.py render-list")
        return

    client = RenderClient()
    services = client.list_services()

    print(f"\n🔄 Services Render ({args.project}):")
    for s in services:
        name = s.get('name') or s.get('service', {}).get('name') or s.get('id') or "N/A"
        status = s.get('status') or s.get('state') or "unknown"
        print(f"  • {name} → {status}")

if __name__ == "__main__":
    main()
