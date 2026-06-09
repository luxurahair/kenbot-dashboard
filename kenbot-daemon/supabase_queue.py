"""
Supabase poll loop pour daemon V3 — pull commandes depuis agent_queue.

Active via env vars :
  KENBOT_SUPABASE_ENABLED=1
  SUPABASE_URL=https://...
  SUPABASE_SERVICE_ROLE_KEY=...
  KENBOT_AGENT_HMAC_SECRET=  # secret partagé pour signer les commandes
"""
import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone

log = logging.getLogger("kenbot-daemon")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_ENABLED = os.environ.get("KENBOT_SUPABASE_ENABLED", "0") == "1"
HMAC_SECRET = os.environ.get("KENBOT_AGENT_HMAC_SECRET", "")
POLL_INTERVAL = int(os.environ.get("KENBOT_SUPABASE_POLL", "10"))


def _verify_signature(command_dict, signature):
    """HMAC SHA256 sur le JSON canonical de la commande."""
    if not HMAC_SECRET or not signature:
        return False
    canonical = json.dumps(command_dict, sort_keys=True, separators=(",", ":")).encode()
    expected = hmac.new(HMAC_SECRET.encode(), canonical, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _supa_request(method, path, **kwargs):
    import urllib.request
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    headers.update(kwargs.pop("headers", {}))
    data = kwargs.pop("json", None)
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1{path}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8")) if resp.length else None


def poll_loop(stop_event, execute_fn):
    if not SUPABASE_ENABLED or not (SUPABASE_URL and SUPABASE_KEY):
        log.info("🛰️  supabase_poll désactivé (vars manquantes)")
        return
    log.info(f"🛰️  supabase_poll démarré (interval={POLL_INTERVAL}s, HMAC={'ON' if HMAC_SECRET else 'OFF'})")
    while not stop_event.is_set():
        try:
            # Pull la plus vieille commande pending
            rows = _supa_request(
                "GET",
                "/agent_queue?status=eq.pending&target=eq.mac_daemon&order=created_at.asc&limit=1",
            )
            if rows:
                row = rows[0]
                cmd_id = row["id"]
                command = row["command"]
                signature = row.get("signature", "")

                # Vérif HMAC (si configuré)
                if HMAC_SECRET:
                    if not _verify_signature(command, signature):
                        log.warning(f"🛰️  cmd {cmd_id[:8]} REJET — signature invalide")
                        _supa_request("PATCH", f"/agent_queue?id=eq.{cmd_id}",
                                      json={"status": "failed", "result": {"error": "bad_signature"},
                                            "finished_at": datetime.now(timezone.utc).isoformat()})
                        continue

                # Mark running
                _supa_request("PATCH", f"/agent_queue?id=eq.{cmd_id}",
                              json={"status": "running",
                                    "started_at": datetime.now(timezone.utc).isoformat()})
                log.info(f"🛰️  cmd {cmd_id[:8]} → {command.get('action')}")

                # Exécute
                try:
                    result = execute_fn(command)
                except Exception as e:
                    result = {"ok": False, "error": str(e)}

                # Push résultat
                _supa_request("PATCH", f"/agent_queue?id=eq.{cmd_id}",
                              json={"status": "done" if result.get("ok") else "failed",
                                    "result": result,
                                    "finished_at": datetime.now(timezone.utc).isoformat()})
                log.info(f"🛰️  cmd {cmd_id[:8]} {'✅' if result.get('ok') else '❌'}")
        except Exception:
            log.exception("supabase_poll iteration failed")
        stop_event.wait(POLL_INTERVAL)
    log.info("🛰️  supabase_poll arrêté")
