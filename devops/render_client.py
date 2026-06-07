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
                print(f"✅ {len(services)} services trouvés sur Render\n")
                return services
            else:
                print(f"❌ Erreur API: {resp.status_code}")
                return []
        except Exception as e:
            print(f"❌ Erreur connexion: {e}")
            return []

    def get_service_name(self, s):
        if not isinstance(s, dict):
            return str(s)[:30]
        
        # Essayer tous les chemins possibles dans la structure Render
        candidates = [
            s.get('name'),
            s.get('service', {}).get('name'),
            s.get('displayName'),
            s.get('id')
        ]
        for name in candidates:
            if name:
                return str(name)
        return "N/A"

    def get_service_status(self, s):
        if not isinstance(s, dict):
            return "unknown"
        return (s.get('status') or 
                s.get('state') or 
                s.get('service', {}).get('status') or 
                "unknown")


# === DEBUG TEMPORAIRE ===
if __name__ == "__main__":
    client = RenderClient()
    services = client.list_services()
    if services and len(services) > 0:
        print("--- DEBUG STRUCTURE DU PREMIER SERVICE ---")
        print(json.dumps(services[0], indent=2)[:1200])
