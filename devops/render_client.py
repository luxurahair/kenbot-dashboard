# devops/render_client.py
"""Client Render API — list services, env vars, restart."""
import requests
import os


class RenderClient:
    def __init__(self):
        self.api_key = os.getenv("RENDER_API_KEY")
        if not self.api_key:
            raise ValueError("❌ RENDER_API_KEY manquante dans .secrets.env")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self.base_url = "https://api.render.com/v1"

    # ── Services ──────────────────────────────────────────────
    def list_services(self):
        try:
            resp = requests.get(
                f"{self.base_url}/services?limit=100", headers=self.headers, timeout=15
            )
            if resp.ok:
                services = resp.json()
                print(f"✅ {len(services)} services trouvés sur Render")
                return services
            print(f"❌ Erreur API: {resp.status_code}")
            return []
        except Exception as e:
            print(f"❌ Erreur connexion: {e}")
            return []

    def find_service_by_name(self, name):
        for s in self.list_services():
            if self.get_name(s).lower() == name.lower():
                return s.get("service") or s
        return None

    def get_name(self, item):
        if not isinstance(item, dict):
            return "N/A"
        service = item.get("service") or item
        return service.get("name") or item.get("name") or "N/A"

    def get_status(self, item):
        if not isinstance(item, dict):
            return "unknown"
        service = item.get("service") or item
        if service.get("suspended") == "not_suspended":
            return "active"
        if service.get("suspended") == "suspended":
            return "suspended"
        return (
            service.get("status")
            or service.get("state")
            or service.get("currentStatus")
            or "unknown"
        )

    # ── Env Vars ──────────────────────────────────────────────
    def get_env_vars(self, service_id):
        """Retourne {key: value} pour un service Render."""
        try:
            resp = requests.get(
                f"{self.base_url}/services/{service_id}/env-vars?limit=100",
                headers=self.headers,
                timeout=15,
            )
            if not resp.ok:
                print(f"   ❌ env-vars {service_id}: HTTP {resp.status_code}")
                return {}
            envs = {}
            for item in resp.json():
                ev = item.get("envVar") or item
                key = ev.get("key")
                if key:
                    envs[key] = ev.get("value", "")
            return envs
        except Exception as e:
            print(f"   ❌ Erreur env-vars: {e}")
            return {}

    # ── Restart / Deploy ──────────────────────────────────────
    def restart_service(self, service_id):
        """Déclenche un redéploiement (= restart) sur Render."""
        try:
            resp = requests.post(
                f"{self.base_url}/services/{service_id}/deploys",
                headers=self.headers,
                json={"clearCache": "do_not_clear"},
                timeout=15,
            )
            if resp.ok:
                deploy_id = (resp.json() or {}).get("id", "?")
                print(f"   ✅ Redémarrage déclenché — deploy={deploy_id}")
                return True
            print(f"   ❌ HTTP {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as e:
            print(f"   ❌ Erreur restart: {e}")
            return False
