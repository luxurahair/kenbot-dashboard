# devops/render_client.py
import requests
import os

class RenderClient:
    def __init__(self):
        self.api_key = os.getenv("RENDER_API_KEY")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.base_url = "https://api.render.com/v1"

    def list_services(self):
        try:
            resp = requests.get(f"{self.base_url}/services?limit=100", headers=self.headers, timeout=15)
            if resp.ok:
                services = resp.json()
                print(f"✅ {len(services)} services trouvés sur Render")
                return services
            else:
                print(f"❌ Erreur API: {resp.status_code}")
                return []
        except Exception as e:
            print(f"❌ Erreur connexion: {e}")
            return []

    def get_name(self, item):
        if not isinstance(item, dict):
            return "N/A"
        return (item.get("name") or 
                item.get("service", {}).get("name") or 
                item.get("displayName") or 
                item.get("id") or "N/A")

    def get_status(self, item):
        if not isinstance(item, dict):
            return "unknown"
        return (item.get("status") or 
                item.get("state") or 
                item.get("service", {}).get("status") or 
                "unknown")
