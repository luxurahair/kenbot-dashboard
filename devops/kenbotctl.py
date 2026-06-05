#!/usr/bin/env python3
"""
Mini Emergent v1.0 - kenbotctl
CLI central pour gérer Kenbot et Luxura en toute sécurité.
"""

import argparse
import sys
from pathlib import Path

# Import des contextes
try:
    from contexts.kenbot import KenbotContext
    from contexts.luxura import LuxuraContext
except ImportError:
    print("❌ Erreur : Les contextes ne sont pas trouvés.")
    print("   Assure-toi d'avoir le dossier devops/contexts/")
    sys.exit(1)


def print_help():
    print("\n🚀 Mini Emergent - kenbotctl")
    print("=" * 50)
    print("Commandes disponibles :\n")
    print("  render-list                  → Liste tous les services Render")
    print("  env-list --service XXX       → Liste les variables d'un service")
    print("  diagnostic                   → Diagnostic complet du système")
    print("  protect                      → Snapshot des env vars Render")
    print("  restart --service XXX        → Redémarre un service")
    print("\nOptions :")
    print("  --project kenbot|luxura      → (défaut: kenbot)")
    print("\nExemples :")
    print("  python devops/kenbotctl.py render-list --project kenbot")
    print("  python devops/kenbotctl.py env-list --service kenbot-runner")
    print("  python devops/kenbotctl.py diagnostic")


def main():
    parser = argparse.ArgumentParser(description="Mini Emergent CLI")
    parser.add_argument("command", choices=[
        "render-list", "env-list", "diagnostic", "protect", 
        "restart", "help"
    ], nargs='?', default="help")
    parser.add_argument("--project", choices=["kenbot", "luxura"], default="kenbot")
    parser.add_argument("--service", help="Nom du service Render (ex: kenbot-runner)")

    args = parser.parse_args()

    if args.command == "help":
        print_help()
        return

    # Sélection du contexte
    if args.project == "kenbot":
        context = KenbotContext()
    else:
        context = LuxuraContext()

    # Exécution de la commande
    if args.command == "render-list":
        context.list_render_services()
    elif args.command == "env-list":
        if not args.service:
            print("❌ Tu dois spécifier --service")
        else:
            context.list_env_vars(args.service)
    elif args.command == "diagnostic":
        context.run_diagnostic()
    elif args.command == "protect":
        context.protect_envvars()
    elif args.command == "restart":
        if not args.service:
            print("❌ Tu dois spécifier --service")
        else:
            context.restart_service(args.service)
    else:
        print_help()


if __name__ == "__main__":
    main()
