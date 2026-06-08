# devops/render_client.py
import requests
import os

class RenderClient:
    def __init__(self):
        self.api_key = os.getenv("RENDER_API_KEY")
        if not self.api_key:
            raise ValueError("❌ RENDER_API_KEY manquante dans .secrets.env")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.base_url = "https://api.render.com/v1"

    def list_services(self):
        resp = requests.get(f"{self.base_url}/services?limit=100", headers=self.headers, timeout=15)
        if resp.ok:
            return resp.json()
        else:
            print(f"❌ Erreur API: {resp.status_code}")
            return []

    def get_name(self, item):
        if not isinstance(item, dict):
            return "N/A"
        return (item.get("name") or 
                item.get("service", {}).get("name") or 
                item.get("displayName") or "N/A")

    def get_status(self, item):
        if not isinstance(item, dict):
            return "unknown"
        # Meilleure extraction du statut Render
        for data in [item, item.get("service", {}), item.get("latestDeploy", {})]:
            for key in ["status", "state", "currentStatus", "status"]:
                if data.get(key):
                    return data.get(key)
        return "unknown"
