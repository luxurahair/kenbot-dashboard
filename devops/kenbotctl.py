#!/usr/bin/env python3
"""
Mini Emergent V3.2 — Puissant & Stable
"""

import argparse
import sys
import os
from dotenv import load_dotenv

load_dotenv('.secrets.env')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_client import RenderClient
from contexts import ALL_PROJECTS, get_context
from protect_render_envvars import RenderEnvProtector

def main():
    parser = argparse.ArgumentParser(description="Mini Emergent V3.2")
    parser.add_argument("command", choices=["kenbot", "luxura", "calcauto", "all", "restart", "env-list", "env-set", "snapshot", "diagnostic", "help"], nargs='?', default="help")
    parser.add_argument("--service", help="Nom du service (ex: kenbot-runner)")
    parser.add_argument("--key", help="Clé à modifier (avec env-set)")
    parser.add_argument("--value", help="Nouvelle valeur (avec env-set)")
    parser.add_argument("--project", choices=list(ALL_PROJECTS.keys()) + ["all"], default="all")

    args = parser.parse_args()

    if args.command == "help":
        print(__doc__)
        print("\nCommandes :")
        print("  kenbot | luxura | calcauto | all")
        print("  restart --service NOM")
        print("  env-list --service NOM")
        print("  env-set --service NOM --key CLE --value VALEUR")
        print("  snapshot [--project NOM]")
        print("  diagnostic [--project NOM]")
        return

    client = RenderClient()

    # List commands
    if args.command in ["kenbot", "luxura", "calcauto", "all"]:
        if args.command == "all":
            services = client.list_services()
            label = "ALL"
        else:
            ctx = get_context(args.command)
            services = ctx.filtered_services()
            label = args.command.upper()
        print(f"\n🔄 Services Render → {label}\n")
        for s in services:
            print(f"  • {client.get_name(s)} → {client.get_status(s)}")
        return

    # Restart
    if args.command == "restart":
        if not args.service:
            print("❌ --service requis")
            sys.exit(1)
        svc = client.find_service_by_name(args.service)
        if not svc:
            print(f"❌ Service '{args.service}' non trouvé")
            sys.exit(1)
        print(f"🔄 Redémarrage {args.service}...")
        success = client.restart_service(svc.get("id"))
        sys.exit(0 if success else 1)

    # Env-list
    if args.command == "env-list":
        if not args.service:
            print("❌ --service requis")
            sys.exit(1)
        svc = client.find_service_by_name(args.service)
        if not svc:
            print(f"❌ Service '{args.service}' non trouvé")
            sys.exit(1)
        envs = client.get_env_vars(svc.get("id"))
        print(f"\n📋 {len(envs)} variables pour {args.service}:\n")
        for k, v in sorted(envs.items()):
            preview = (v[:60] + "...") if len(v or "") > 60 else (v or "")
            print(f"  • {k} = {preview}")
        return

    # Env-set (nouveau)
    if args.command == "env-set":
        if not args.service or not args.key or args.value is None:
            print("❌ Usage : env-set --service NOM --key CLE --value VALEUR")
            sys.exit(1)
        svc = client.find_service_by_name(args.service)
        if not svc:
            print(f"❌ Service '{args.service}' non trouvé")
            sys.exit(1)
        print(f"🔧 Mise à jour {args.key} sur {args.service}...")
        success = client.set_env_var(svc.get("id"), args.key, args.value)
        if success:
            print("💾 N'oublie pas de redémarrer :")
            print(f"   python3 devops/kenbotctl.py restart --service {args.service}")
        sys.exit(0 if success else 1)

    # Snapshot
    if args.command == "snapshot":
        target = args.project if args.project != "all" else None
        if target:
            RenderEnvProtector(target).snapshot()
        else:
            for p in ALL_PROJECTS:
                RenderEnvProtector(p).snapshot()
        return

    # Diagnostic
    if args.command == "diagnostic":
        from diagnostic import run
        run(args.project if args.project != "all" else "kenbot")
        return

if __name__ == "__main__":
    main()
