# devops/protect_render_envvars.py
"""
Snapshot & Protection des variables d'environnement Render
Inspiré du système d'Emergent
"""

import os
import json
from datetime import datetime
from pathlib import Path
from render_client import RenderClient

class RenderEnvProtector:
    def __init__(self, project="kenbot"):
        self.project = project
        self.render = RenderClient()
        self.snapshot_dir = Path("memory/render_snapshots")
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def snapshot(self):
        """Fait un snapshot complet des variables Render"""
        print(f"🔄 Création du snapshot pour {self.project}...")

        services = self.render.list_services()
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "project": self.project,
            "services": {}
        }

        for service in services:
            name = service.get("name")
            service_id = service.get("id")
            if name and service_id:
                # Pour l'instant on liste seulement (sécurité)
                snapshot["services"][name] = {
                    "service_id": service_id,
                    "status": service.get("status")
                }
                print(f"   📸 {name} sauvegardé")

        filename = self.snapshot_dir / f"{self.project}_snapshot_{datetime.now().strftime('%Y-%m-%d_%H%M')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)

        print(f"\n✅ Snapshot créé : {filename}")
        return filename

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", choices=["kenbot", "luxura", "calcauto"], default="kenbot")
    args = parser.parse_args()

    protector = RenderEnvProtector(args.project)
    protector.snapshot()

if __name__ == "__main__":
    main()
