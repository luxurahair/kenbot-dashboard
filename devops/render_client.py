# devops/render_client.py
import requests
import os
import json

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
        try:
            resp = requests.get(f"{self.base_url}/services?limit=100", headers=self.headers, timeout=15)
            if resp.ok:
                services = resp.json()
                print(f"✅ {len(services)} services trouvés sur Render")
                return services
            else:
                print(f"❌ Erreur API: {resp.status_code} - {resp.text[:200]}")
                return []
        except Exception as e:
            print(f"❌ Erreur connexion: {e}")
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
        
        # Debug : on cherche dans tous les endroits possibles
        candidates = [item, item.get("service", {}), item.get("latestDeploy", {})]
        for data in candidates:
            for key in ["status", "state", "currentStatus"]:
                if key in data and data[key]:
                    return data[key]
        return "unknown"

    def debug_first_service(self):
        services = self.list_services()
        if services:
            print("\n=== DEBUG STRUCTURE PREMIER SERVICE ===")
            print(json.dumps(services[0], indent=2)[:1500])
            print("=== CLÉS PRINCIPALES ===")
            print(list(services[0].keys()))

if __name__ == "__main__":
    client = RenderClient()
    client.debug_first_service()
