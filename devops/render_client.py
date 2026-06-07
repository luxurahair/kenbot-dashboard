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
            resp = requests.get(f"{self.base_url}/services", headers=self.headers, timeout=20)
            if resp.ok:
                services = resp.json()
                print(f"✅ {len(services)} services trouvés sur Render\n")
                return services
            else:
                print(f"❌ Erreur API: {resp.status_code} - {resp.text[:200]}")
                return []
        except Exception as e:
            print(f"❌ Erreur connexion: {e}")
            return []

    def get_service_name(self, s):
        if not isinstance(s, dict):
            return "N/A"
        
        # Essayer tous les chemins possibles
        for key in ['name', 'service.name', 'displayName', 'hostname']:
            if '.' in key:
                val = s
                for k in key.split('.'):
                    val = val.get(k) if isinstance(val, dict) else None
                    if val is None:
                        break
                if val:
                    return str(val)
            elif s.get(key):
                return str(s.get(key))
        
        return s.get('id', 'N/A')[:30]

    def get_service_status(self, s):
        if not isinstance(s, dict):
            return "unknown"
        return s.get('status') or s.get('state') or "unknown"


# Debug
if __name__ == "__main__":
    client = RenderClient()
    services = client.list_services()
    if services:
        print("--- DEBUG Premier service ---")
        print(json.dumps(services[0], indent=2)[:1500])
