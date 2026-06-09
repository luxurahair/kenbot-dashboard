"""
push_cmd_to_mac.py — Côté cloud (moi). Push une commande à exécuter sur le Mac.

Usage côté cloud (dans /app) :
    from tools.push_cmd_to_mac import push_command, wait_result
    cmd_id = push_command({"action": "write_file", "path": "/Users/danielgiroux/...", "content": "..."})
    result = wait_result(cmd_id, timeout=30)
"""
import hashlib
import hmac
import json
import os
import time
import urllib.request

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
HMAC_SECRET = os.environ.get("KENBOT_AGENT_HMAC_SECRET", "")


def _sign(command_dict):
    if not HMAC_SECRET:
        return ""
    canonical = json.dumps(command_dict, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(HMAC_SECRET.encode(), canonical, hashlib.sha256).hexdigest()


def _supa(method, path, data=None):
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1{path}", data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as r:
        txt = r.read().decode()
        return json.loads(txt) if txt else None


def push_command(command):
    """Insert une commande dans agent_queue. Retourne le id (uuid)."""
    payload = {
        "target": "mac_daemon",
        "command": command,
        "signature": _sign(command),
        "created_by": "cloud_agent",
    }
    rows = _supa("POST", "/agent_queue", payload)
    return rows[0]["id"]


def wait_result(cmd_id, timeout=30, poll=2):
    """Attend que la commande soit traitée."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        rows = _supa("GET", f"/agent_queue?id=eq.{cmd_id}&select=status,result")
        if rows and rows[0]["status"] in ("done", "failed"):
            return rows[0]
        time.sleep(poll)
    return {"status": "timeout", "result": None}


if __name__ == "__main__":
    import sys
    cmd = json.loads(sys.argv[1])
    cid = push_command(cmd)
    print(f"Pushed cmd {cid}")
    r = wait_result(cid)
    print(json.dumps(r, indent=2, ensure_ascii=False))
