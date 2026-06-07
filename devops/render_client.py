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
            resp = requests.get(f"{self.base_url}/services", headers=self.headers, timeout=15)
            if resp.ok:
                services = resp.json()
                print(f"✅ {len(services)} services trouvés sur Render")
                return services
            else:
                print(f"❌ Erreur API: {resp.status_code} - {resp.text[:300]}")
                return []
        except Exception as e:
            print(f"❌ Erreur connexion: {e}")
            return []

    def get_service_name(self, service):
        if not isinstance(service, dict):
            return str(service)[:50]
        
        # Essayer plusieurs chemins possibles
        for key in ['name', 'service.name', 'displayName']:
            if '.' in key:
                parts = key.split('.')
                val = service
                for p in parts:
                    val = val.get(p) if isinstance(val, dict) else None
                    if val is None:
                        break
                if val:
                    return val
            elif service.get(key):
                return service.get(key)
        
        return service.get('id', 'N/A')[:20]

    def get_service_status(self, service):
        if not isinstance(service, dict):
            return "unknown"
        return service.get('status') or service.get('state') or "unknown"


# Pour debug : afficher la structure une fois
if __name__ == "__main__":
    client = RenderClient()
    services = client.list_services()
    if services:
        print("\n--- Structure du premier service (debug) ---")
        print(json.dumps(services[0], indent=2)[:800] + "...")
