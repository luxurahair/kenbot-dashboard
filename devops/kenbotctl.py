#!/usr/bin/env python3
"""
Mini Emergent v1.0 - kenbotctl
"""

import argparse
import sys
import os
from pathlib import Path

# Charger les variables d'environnement (.secrets.env)
try:
    from dotenv import load_dotenv
    load_dotenv('.secrets.env')
    print("✅ .secrets.env chargé")
except ImportError:
    print("⚠️ python-dotenv non installé (RENDER_API_KEY risque de manquer)")

# Ajout du chemin pour les imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import des contextes
try:
    from contexts.kenbot import KenbotContext
    from contexts.luxura import LuxuraContext
except ImportError as e:
    print("❌ Erreur d'import :", e)
    print("Dossier actuel :", os.getcwd())
    sys.exit(1)


def print_help():
    print("\n🚀 Mini Emergent - kenbotctl")
    print("=" * 50)
    print("Commandes disponibles :\n")
    print("  render-list                  → Liste tous les services Render")
    print("  diagnostic                   → Diagnostic complet")
    print("  protect                      → Snapshot des variables Render")
    print("\nExemple :")
    print("  python devops/kenbotctl.py render-list --project kenbot")


def main():
    parser = argparse.ArgumentParser(description="Mini Emergent CLI")
    parser.add_argument("command", choices=["render-list", "diagnostic", "protect", "help"], nargs='?', default="help")
    parser.add_argument("--project", choices=["kenbot", "luxura"], default="kenbot")

    args = parser.parse_args()

    if args.command == "help":
        print_help()
        return

    if args.project == "kenbot":
        context = KenbotContext()
    else:
        context = LuxuraContext()

    if args.command == "render-list":
        context.list_render_services()
    elif args.command == "diagnostic":
        context.run_diagnostic()
    elif args.command == "protect":
        context.protect_envvars()


if __name__ == "__main__":
    main()
