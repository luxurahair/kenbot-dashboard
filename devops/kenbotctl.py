#!/usr/bin/env python3
"""
Mini Emergent V3 — Stable & fonctionnel
=======================================
CLI unique pour gérer les services Render des 3 projets logiques
(Kenbot / Luxura / CalcAuto).

Toutes les commandes ci-dessous sont **réellement implémentées** :
    kenbot | luxura | calcauto | all      → liste les services
    restart   --service NOM               → redéploie un service
    env-list  --service NOM               → liste les env vars
    snapshot  [--project NAME]            → snapshot complet des env vars
    help                                  → affiche cette aide
"""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv(".secrets.env")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contexts import ALL_PROJECTS, get_context  # noqa: E402
from render_client import RenderClient  # noqa: E402


def _print_services(label, services, client):
    print(f"\n🔄 Services Render → {label.upper()}\n")
    for s in services:
        print(f"  • {client.get_name(s)} → {client.get_status(s)}")
    if not services:
        print("  (aucun service trouvé)")


def main():
    parser = argparse.ArgumentParser(description="Mini Emergent V3")
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
            "help",
        ],
        nargs="?",
        default="help",
    )
    parser.add_argument("--service", help="Nom du service (ex: kenbot-runner)")
    parser.add_argument(
        "--project",
        choices=list(ALL_PROJECTS.keys()) + ["all"],
        help="Limite snapshot à un projet (default: all)",
    )

    args = parser.parse_args()

    if args.command == "help":
        print(__doc__)
        return

    client = RenderClient()

    # ── Listes par projet ────────────────────────────────────
    if args.command in ALL_PROJECTS:
        ctx = get_context(args.command)
        _print_services(args.command, ctx.filtered_services(), client)
        return

    if args.command == "all":
        _print_services("all", client.list_services(), client)
        return

    # ── Restart ──────────────────────────────────────────────
    if args.command == "restart":
        if not args.service:
            print("❌ --service requis. Ex: --service kenbot-dashboard-api")
            sys.exit(1)
        svc = client.find_service_by_name(args.service)
        if not svc:
            print(f"❌ Service '{args.service}' introuvable sur Render")
            sys.exit(1)
        print(f"🔄 Redémarrage de {args.service} (id={svc.get('id')})...")
        ok = client.restart_service(svc.get("id"))
        sys.exit(0 if ok else 1)

    # ── Env list ─────────────────────────────────────────────
    if args.command == "env-list":
        if not args.service:
            print("❌ --service requis. Ex: --service kenbot-runner")
            sys.exit(1)
        svc = client.find_service_by_name(args.service)
        if not svc:
            print(f"❌ Service '{args.service}' introuvable sur Render")
            sys.exit(1)
        envs = client.get_env_vars(svc.get("id"))
        print(f"\n📋 {len(envs)} variable(s) pour {args.service} :\n")
        for k in sorted(envs):
            v = envs[k]
            preview = (v[:40] + "…") if v and len(v) > 40 else v
            print(f"  • {k} = {preview!r}")
        return

    # ── Snapshot ─────────────────────────────────────────────
    if args.command == "snapshot":
        from protect_render_envvars import RenderEnvProtector

        target = args.project or "all"
        if target == "all":
            for name in ALL_PROJECTS:
                RenderEnvProtector(name).snapshot()
        else:
            RenderEnvProtector(target).snapshot()
        return


if __name__ == "__main__":
    main()
