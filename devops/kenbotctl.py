#!/usr/bin/env python3
"""
Mini Emergent v1.0 - kenbotctl (Filtrage précis)
"""

import argparse
import sys
import os
from dotenv import load_dotenv

load_dotenv('.secrets.env')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_client import RenderClient

class Context:
    def __init__(self, project="kenbot"):
        self.project = project
        self.render = RenderClient()
        
        # Filtres très précis
        if project == "kenbot":
            self.keywords = ["kenbot", "beauce", "calcauto", "facebook weekend", "facebook educational", "facebook product"]
        else:
            self.keywords = ["luxura", "luxura-"]

    def list_render_services(self):
        services = self.render.list_services()
        print(f"\n🔄 Services Render → {self.project.upper()}\n")
        
        filtered = []
        for s in services:
            name = self.render.get_name(s).lower()
            if any(kw in name for kw in self.keywords):
                filtered.append(s)
        
        print(f"   {len(filtered)} services trouvés pour {self.project}:\n")
        for s in filtered:
            name = self.render.get_name(s)
            status = self.render.get_status(s)
            print(f"  • {name} → {status}")

def main():
    parser = argparse.ArgumentParser(description="Mini Emergent CLI")
    parser.add_argument("command", choices=["render-list", "help"], nargs='?', default="help")
    parser.add_argument("--project", choices=["kenbot", "luxura"], default="kenbot")

    args = parser.parse_args()

    if args.command == "help":
        print("Usage: python devops/kenbotctl.py render-list --project kenbot")
        return

    context = Context(args.project)
    context.list_render_services()

if __name__ == "__main__":
    main()
