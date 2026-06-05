# devops/render_client.py
import requests
import os
from typing import List, Dict

class RenderClient:
    def __init__(self):
        self.api_key = os.getenv("RENDER_API_KEY")
        if not self.api_key:
            print("❌ RENDER_API_KEY non trouvée dans .secrets.env")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self.base_url = "https://api.render.com/v1"

    def list_services(self) -> List[Dict]:
        """Liste tous les services Render"""
        try:
            resp = requests.get(f"{self.base_url}/services", headers=self.headers, timeout=10)
            if resp.ok:
                services = resp.json()
                print(f"✅ {len(services)} services trouvés sur Render")
                return services
            else:
                print(f"❌ Erreur Render API: {resp.status_code}")
                return []
        except Exception as e:
            print(f"❌ Erreur connexion Render: {e}")
            return []

    def restart_service(self, service_id: str):
        """Redémarre un service"""
        try:
            resp = requests.post(f"{self.base_url}/services/{service_id}/restart", headers=self.headers)
            if resp.ok:
                print(f"✅ Redémarrage demandé pour {service_id}")
                return True
            else:
                print(f"❌ Échec redémarrage: {resp.status_code}")
                return False
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return False
