# devops/render_client.py
import requests
import os
import logging

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class RenderClient:
    def __init__(self):
        self.api_key = os.getenv("RENDER_API_KEY")
        if not self.api_key:
            log.error("❌ RENDER_API_KEY manquante dans .secrets.env")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.base_url = "https://api.render.com/v1"

    def list_services(self):
        """Liste tous les services Render (avec pagination si besoin)"""
        try:
            resp = requests.get(
                f"{self.base_url}/services?limit=100",
                headers=self.headers,
                timeout=15
            )
            resp.raise_for_status()
            services = resp.json()
            print(f"✅ {len(services)} services trouvés sur Render")
            return services
        except Exception as e:
            log.error(f"Erreur Render API: {e}")
            return []

    def get_name(self, item):
        """Extraction robuste du nom"""
        if not isinstance(item, dict):
            return "N/A"
        return (item.get("name") or 
                item.get("service", {}).get("name") or 
                item.get("displayName") or 
                item.get("id") or "N/A")

    def get_status(self, item):
        """Extraction robuste du statut"""
        if not isinstance(item, dict):
            return "unknown"
        return (item.get("status") or 
                item.get("state") or 
                item.get("service", {}).get("status") or 
                "unknown")


# Test rapide si exécuté directement
if __name__ == "__main__":
    client = RenderClient()
    services = client.list_services()
    for s in services:
        print(f"  • {client.get_name(s):40s} → {client.get_status(s)}")
