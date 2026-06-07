#!/usr/bin/env python3
"""
Mini Emergent v1.0 - kenbotctl (Version simplifiée)
"""

import argparse
import sys
import os
from pathlib import Path

# Charger les secrets
try:
    from dotenv import load_dotenv
    load_dotenv('.secrets.env')
except ImportError:
    pass

# Import direct sans dossier contexts compliqué
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

class SimpleContext:
    def __init__(self, project="kenbot"):
        self.project = project
        from render_client import RenderClient
        self.render = RenderClient()

    def list_render_services(self):
        services = self.render.list_services()
        print(f"\n🔄 Services Render ({self.project}):")
        for s in services:
            name = s.get('name') or "N/A"
            status = s.get('status') or "unknown"
            print(f"  • {name} → {status}")

    def run_diagnostic(self):
        print(f"Diagnostic {self.project} en cours...")
        self.list_render_services()

    def protect_envvars(self):
        print("Protection env vars en cours...")

def main():
    parser = argparse.ArgumentParser(description="Mini Emergent CLI")
    parser.add_argument("command", choices=["render-list", "diagnostic", "protect", "help"], nargs='?', default="help")
    parser.add_argument("--project", choices=["kenbot", "luxura"], default="kenbot")

    args = parser.parse_args()

    context = SimpleContext(args.project)

    if args.command == "render-list":
        context.list_render_services()
    elif args.command == "diagnostic":
        context.run_diagnostic()
    elif args.command == "protect":
        context.protect_envvars()
    else:
        print("Commandes : render-list, diagnostic, protect")

if __name__ == "__main__":
    main()
