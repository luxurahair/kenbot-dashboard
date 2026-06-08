# devops/contexts/base.py
"""Classe parente — un seul code pour Kenbot/Luxura/CalcAuto."""
from render_client import RenderClient


class BaseContext:
    """
    Représente un projet logique (kenbot, luxura, calcauto).
    Filtre les services Render par mots-clés + exclusions.
    """

    def __init__(self, project, keywords, exclude=None):
        self.project = project
        self.keywords = [k.lower() for k in keywords]
        self.exclude = [k.lower() for k in (exclude or [])]
        self.render = RenderClient()

    # ── Filtrage ──────────────────────────────────────────────
    def belongs(self, name):
        n = (name or "").lower()
        if self.exclude and any(x in n for x in self.exclude):
            return False
        return any(k in n for k in self.keywords)

    def filtered_services(self, services=None):
        services = services if services is not None else self.render.list_services()
        return [s for s in services if self.belongs(self.render.get_name(s))]

    # ── Actions ───────────────────────────────────────────────
    def list_render_services(self):
        print(f"\n🔄 Services Render ({self.project}):")
        for s in self.filtered_services():
            name = self.render.get_name(s)
            status = self.render.get_status(s)
            print(f"  • {name} → {status}")

    def run_diagnostic(self):
        print(f"\n🔍 DIAGNOSTIC — {self.project.upper()}")
        services = self.filtered_services()
        active = sum(1 for s in services if self.render.get_status(s) == "active")
        print(f"   • Total services: {len(services)} (actifs: {active})")
        for s in services:
            svc = s.get("service") or s
            print(f"   • {svc.get('name')} → {self.render.get_status(s)}")
