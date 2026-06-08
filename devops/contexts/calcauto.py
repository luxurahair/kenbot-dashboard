# devops/contexts/calcauto.py
import os
from render_client import RenderClient

class CalcautoContext:
    def __init__(self):
        self.render = RenderClient()
        self.project = "calcauto"

    def list_render_services(self):
        services = self.render.list_services()
        print(f"\n🔄 Services Render ({self.project}):")
        for s in services:
            name = s.get('name', 'N/A')
            status = s.get('status', 'N/A')
            print(f"  • {name} → {status}")

    def list_env_vars(self, service_name):
        print(f"Liste des variables pour {service_name} (calcauto) → à implémenter")

    def run_diagnostic(self):
        print(f"Diagnostic CalcAuto AiPro en cours...")
        self.list_render_services()

    def protect_envvars(self):
        print("Protection env vars CalcAuto → à implémenter")

    def restart_service(self, service_name):
        print(f"Redémarrage {service_name} (calcauto) → à implémenter")
