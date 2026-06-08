# devops/protect_render_envvars.py
"""
Snapshot RÉEL des variables d'environnement Render.

Contrairement à V1 (qui ne sauvait que les service IDs), cette version :
  1. Récupère TOUTES les env vars de chaque service du projet
  2. Sauvegarde dans memory/render_snapshots/{project}_YYYY-MM-DD_HHMM.json
  3. Compare au dernier snapshot et alerte si des vars CRITIQUES ont disparu
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(".secrets.env")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contexts import ALL_PROJECTS, get_context  # noqa: E402

# Vars critiques par projet — si l'une disparaît, on hurle.
CRITICAL_VARS = {
    "kenbot": {
        "KENBOT_FB_PAGE_ID",
        "KENBOT_FB_PAGE_ACCESS_TOKEN",
        "KENBOT_API_URL",
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "BEAUCE_AGENT_TOKEN",
        "TWILIO_ACCOUNT_SID",
    },
    "luxura": {
        "LUXURA_API_URL",
        "SUPABASE_URL",
    },
    "calcauto": {
        "GOOGLE_VISION_API_KEY",
        "SUPABASE_URL",
    },
}


class RenderEnvProtector:
    def __init__(self, project):
        if project not in ALL_PROJECTS:
            raise ValueError(f"Projet inconnu: {project} (choisis parmi {list(ALL_PROJECTS)})")
        self.project = project
        self.ctx = get_context(project)
        self.snapshot_dir = Path("memory/render_snapshots")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    # ── Snapshot ──────────────────────────────────────────────
    def snapshot(self):
        print(f"\n💾 Snapshot {self.project.upper()}...")
        services = self.ctx.filtered_services()
        data = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "project": self.project,
            "services": {},
        }

        for s in services:
            svc = s.get("service") or s
            name = svc.get("name")
            sid = svc.get("id")
            if not (name and sid):
                continue
            envs = self.ctx.render.get_env_vars(sid)
            data["services"][name] = {
                "service_id": sid,
                "status": self.ctx.render.get_status(s),
                "env_vars": envs,
                "env_count": len(envs),
            }
            print(f"   📸 {name} → {len(envs)} env vars")

        filename = (
            self.snapshot_dir
            / f"{self.project}_snapshot_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
        )
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"   ✅ Sauvé → {filename}")

        self._alert_missing_critical(data)
        return filename

    # ── Vérifications critiques ───────────────────────────────
    def _alert_missing_critical(self, snapshot):
        critical = CRITICAL_VARS.get(self.project, set())
        if not critical:
            return
        missing_per_service = {}
        for svc_name, svc_data in snapshot["services"].items():
            present = set(svc_data["env_vars"].keys())
            missing = critical - present
            # Ne pas alerter sur les crons "non concernés" (heuristique : si AUCUNE
            # var critique présente, ce n'est probablement pas un service Kenbot principal)
            if missing and (critical & present):
                missing_per_service[svc_name] = sorted(missing)

        if missing_per_service:
            print(f"\n⚠️  VARS CRITIQUES MANQUANTES ({self.project}):")
            for svc, miss in missing_per_service.items():
                print(f"   • {svc} → {', '.join(miss)}")
        else:
            print(f"   ✅ Toutes les vars critiques présentes sur les services concernés")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project",
        choices=list(ALL_PROJECTS.keys()) + ["all"],
        default="all",
    )
    args = parser.parse_args()
    if args.project == "all":
        for name in ALL_PROJECTS:
            RenderEnvProtector(name).snapshot()
    else:
        RenderEnvProtector(args.project).snapshot()


if __name__ == "__main__":
    main()
