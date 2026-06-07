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
            resp = requests.get(f"{self.base_url}/services", headers=self.headers, timeout=15)
            if resp.ok:
                services = resp.json()
                print(f"✅ {len(services)} services trouvés sur Render")
                return services
            else:
                print(f"❌ Erreur API Render: {resp.status_code}")
                return []
        except Exception as e:
            print(f"❌ Erreur connexion: {e}")
            return []

    def get_service_name(self, service):
        """Extraction robuste du nom"""
        if not isinstance(service, dict):
            return "N/A"
        
        # Différentes structures possibles de l'API Render
        name = service.get('name')
        if name:
            return name
        
        service_obj = service.get('service') or {}
        return service_obj.get('name') or service.get('id') or "N/A"

    def get_service_status(self, service):
        """Extraction robuste du statut"""
        if not isinstance(service, dict):
            return "unknown"
        
        return (service.get('status') or 
                service.get('state') or 
                service.get('service', {}).get('status') or 
                "unknown")
