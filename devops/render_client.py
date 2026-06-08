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
            print(f"Status code: {resp.status_code}")
            if resp.ok:
                services = resp.json()
                print(f"✅ {len(services)} services trouvés")
                return services
            else:
                print(f"❌ Erreur: {resp.text[:500]}")
                return []
        except Exception as e:
            print(f"❌ Exception: {e}")
            return []

# Debug complet
if __name__ == "__main__":
    client = RenderClient()
    services = client.list_services()
    if services:
        print("\n=== DEBUG STRUCTURE DU PREMIER SERVICE (RAW) ===")
        print(json.dumps(services[0], indent=2))
        print("\n=== NOMS DES CLÉS DISPONIBLES ===")
        print(list(services[0].keys()))
