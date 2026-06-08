# devops/render_client.py
import requests
import os
import json

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
                print(f"✅ {len(services)} services trouvés sur Render\n")
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
        
        # Toutes les possibilités connues de Render API
        possible = [
            item.get("name"),
            item.get("service", {}).get("name"),
            item.get("displayName"),
            item.get("hostname"),
            item.get("id")
        ]
        for name in possible:
            if name and str(name).strip():
                return str(name)
        return "N/A"

# Debug
if __name__ == "__main__":
    client = RenderClient()
    services = client.list_services()
    print("\n=== DEBUG - PREMIER SERVICE (RAW) ===")
    if services:
        print(json.dumps(services[0], indent=2)[:2000])
    print("\n=== LISTE DES SERVICES ===")
    for s in services:
        name = client.get_name(s)
        print(f"  • {name}")
