#!/usr/bin/env python3
"""
Mini Emergent V3.1 — Version Consolidée & Puissante
====================================================
CLI unique pour gérer les services Render des 3 projets logiques
(Kenbot / Luxura / CalcAuto).

Toutes les commandes ci-dessous sont **réellement implémentées** :
    kenbot | luxura | calcauto | all      → liste les services
    restart    --service NOM              → redéploie un service
    env-list   --service NOM              → liste les env vars
    snapshot   [--project NAME]           → snapshot env vars (alerte vars critiques)
    diagnostic [--project NAME]           → diagnostic complet
    help                                  → affiche cette aide
"""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv(".secrets.env")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contexts import ALL_PROJECTS, get_context  # noqa: E402
from protect_render_envvars import RenderEnvProtector  # noqa: E402
from render_client import RenderClient  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Mini Emergent V3.1")
    parser.add_argument(
        "command",
        choices=[
            "kenbot",
            "luxura",
            "calcauto",
            "all",
            "restart",
            "env-list",
            "snapshot",
            "diagnostic",
            "help",
        ],
        nargs="?",
        default="help",
    )
    parser.add_argument("--service", help="Nom du service (ex: kenbot-runner)")
    parser.add_argument(
        "--project",
        choices=list(ALL_PROJECTS.keys()) + ["all"],
        default="all",
    )

    args = parser.parse_args()

    if args.command == "help":
        print(__doc__)
        return

    client = RenderClient()

    # ── Listes par projet ────────────────────────────────────
    if args.command in ["kenbot", "luxura", "calcauto", "all"]:
        if args.command == "all":
            services = client.list_services()
            label = "ALL"
        else:
            services = get_context(args.command).filtered_services()
            label = args.command.upper()

        print(f"\n🔄 Services Render → {label}\n")
        for s in services:
            print(f"  • {client.get_name(s)} → {client.get_status(s)}")
        if not services:
            print("  (aucun service trouvé)")
        return

    # ── Restart ──────────────────────────────────────────────
    if args.command == "restart":
        if not args.service:
            print("❌ Utilisation : restart --service NOM")
            sys.exit(1)
        print(f"🔄 Redémarrage de {args.service}...")
        svc = client.find_service_by_name(args.service)
        if not svc:
            print(f"❌ Service '{args.service}' non trouvé")
            sys.exit(1)
        success = client.restart_service(svc.get("id"))
        sys.exit(0 if success else 1)

    # ── Env list ─────────────────────────────────────────────
    if args.command == "env-list":
        if not args.service:
            print("❌ Utilisation : env-list --service NOM")
            sys.exit(1)
        svc = client.find_service_by_name(args.service)
        if not svc:
            print(f"❌ Service '{args.service}' non trouvé")
            sys.exit(1)
        envs = client.get_env_vars(svc.get("id"))
        print(f"\n📋 {len(envs)} variable(s) pour {args.service} :\n")
        for k in sorted(envs):
            v = envs[k]
            preview = (v[:60] + "…") if v and len(v) > 60 else v
            print(f"  • {k} = {preview!r}")
        return

    # ── Snapshot ─────────────────────────────────────────────
    if args.command == "snapshot":
        if args.project == "all":
            for p in ALL_PROJECTS:
                RenderEnvProtector(p).snapshot()
        else:
            RenderEnvProtector(args.project).snapshot()
        return

    # ── Diagnostic ───────────────────────────────────────────
    if args.command == "diagnostic":
        from diagnostic import run

        target = args.project if args.project != "all" else "kenbot"
        run(target)
        return


if __name__ == "__main__":
    main()
