# devops/diagnostic.py
from render_client import RenderClient
import os

class Diagnostic:
    def __init__(self, project="kenbot"):
        self.project = project
        self.render = RenderClient()

    def run_full_diagnostic(self):
        print(f"\n🔍 DIAGNOSTIC COMPLET - {self.project.upper()}\n")
        
        print("1. Services Render :")
        services = self.render.list_services()
        
        print("\n2. Vérification variables essentielles :")
        important_vars = ["RENDER_API_KEY", "SUPABASE_URL", "TWILIO_ACCOUNT_SID"]
        for var in important_vars:
            value = os.getenv(var)
            status = "✅ Présente" if value else "❌ Manquante"
            print(f"   {var}: {status}")

        print("\n✅ Diagnostic terminé.")
