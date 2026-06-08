#!/usr/bin/env python3
"""
Kenbot Daemon V2 — Mini Emergent Local Agent
=============================================
3 boucles concurrentes :
  1. queue_loop       → exécute les commandes JSON drop dans commands/inbox/
  2. watchdog_loop    → snapshot toutes les N min + auto-restore vars critiques perdues
  3. http_server      → webhook localhost:7777 (POST /cmd, GET /status, GET /health)

Toutes les commandes acceptent les actions suivantes (champ "action") :
  - "kenbotctl"  : args=["env-set", "--service", "...", ...]   (passe-plat)
  - "restart"    : service="kenbot-runner"
  - "env-set"    : service, key, value
  - "env-list"   : service
  - "snapshot"   : project (kenbot|luxura|calcauto|all)
  - "shell"      : cmd="ls -la"   (UNIQUEMENT si ALLOW_SHELL=1 dans env)

Sécurité :
  - subprocess avec args list (pas de shell injection)
  - secret partagé X-Daemon-Token pour le webhook HTTP
  - listen sur 127.0.0.1 uniquement
"""
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────
DAEMON_DIR = Path(os.environ.get("KENBOT_DAEMON_DIR", "~/Desktop/kenbot-dashboard/kenbot-daemon")).expanduser()
REPO_DIR = Path(os.environ.get("KENBOT_REPO_DIR", "~/Desktop/kenbot-dashboard")).expanduser()
INBOX = DAEMON_DIR / "commands/inbox"
PROCESSING = DAEMON_DIR / "commands/processing"
OUTBOX = DAEMON_DIR / "commands/outbox"
LOG_DIR = DAEMON_DIR / "logs"
HEARTBEAT = DAEMON_DIR / "heartbeat.txt"

QUEUE_POLL_SECONDS = int(os.environ.get("KENBOT_QUEUE_POLL", "10"))
WATCHDOG_INTERVAL_SECONDS = int(os.environ.get("KENBOT_WATCHDOG_INTERVAL", "1800"))  # 30 min
WATCHDOG_PROJECTS = os.environ.get("KENBOT_WATCHDOG_PROJECTS", "kenbot,luxura,calcauto").split(",")
WATCHDOG_ENABLED = os.environ.get("KENBOT_WATCHDOG_ENABLED", "1") == "1"
HTTP_PORT = int(os.environ.get("KENBOT_HTTP_PORT", "7777"))
HTTP_ENABLED = os.environ.get("KENBOT_HTTP_ENABLED", "1") == "1"
HTTP_TOKEN = os.environ.get("KENBOT_DAEMON_TOKEN", "")  # vide → webhook rejette tout
ALLOW_SHELL = os.environ.get("KENBOT_ALLOW_SHELL", "0") == "1"
NOTIFY_MACOS = os.environ.get("KENBOT_NOTIFY_MACOS", "1") == "1"

for d in (INBOX, PROCESSING, OUTBOX, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────
log = logging.getLogger("kenbot-daemon")
log.setLevel(logging.INFO)
_handler = RotatingFileHandler(LOG_DIR / "daemon.log", maxBytes=2_000_000, backupCount=5)
_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(threadName)s — %(message)s"))
log.addHandler(_handler)
log.addHandler(logging.StreamHandler(sys.stdout))

# ─── Utils ────────────────────────────────────────────────────
def notify_mac(title, message):
    if not NOTIFY_MACOS:
        return
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            check=False, timeout=5,
        )
    except Exception:
        pass


def write_heartbeat():
    HEARTBEAT.write_text(datetime.now(timezone.utc).isoformat())


def run_kenbotctl(args, timeout=120):
    """Exécute python3 devops/kenbotctl.py <args> dans le repo, retourne (rc, stdout, stderr)."""
    cmd = ["python3", "devops/kenbotctl.py"] + list(args)
    proc = subprocess.run(
        cmd, cwd=str(REPO_DIR),
        capture_output=True, text=True, timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


# ─── Executor ─────────────────────────────────────────────────
def execute_command(cmd):
    """Dispatch un dict commande vers l'action correspondante. Retourne dict résultat."""
    action = (cmd.get("action") or "").lower()
    log.info(f"Action={action} payload={ {k:v for k,v in cmd.items() if k != 'value'} }")

    try:
        if action == "kenbotctl":
            args = cmd.get("args") or []
            if not isinstance(args, list):
                return {"ok": False, "error": "'args' doit être une liste"}
            rc, out, err = run_kenbotctl(args)
            return {"ok": rc == 0, "rc": rc, "stdout": out[-2000:], "stderr": err[-1000:]}

        if action == "restart":
            svc = cmd.get("service")
            if not svc:
                return {"ok": False, "error": "service requis"}
            rc, out, err = run_kenbotctl(["restart", "--service", svc])
            return {"ok": rc == 0, "rc": rc, "stdout": out[-2000:], "stderr": err[-500:]}

        if action == "env-set":
            svc, key, value = cmd.get("service"), cmd.get("key"), cmd.get("value")
            if not (svc and key and value is not None):
                return {"ok": False, "error": "service/key/value requis"}
            rc, out, err = run_kenbotctl(["env-set", "--service", svc, "--key", key, "--value", value])
            return {"ok": rc == 0, "rc": rc, "stdout": out[-2000:], "stderr": err[-500:]}

        if action == "env-list":
            svc = cmd.get("service")
            if not svc:
                return {"ok": False, "error": "service requis"}
            rc, out, err = run_kenbotctl(["env-list", "--service", svc])
            return {"ok": rc == 0, "rc": rc, "stdout": out[-5000:], "stderr": err[-500:]}

        if action == "snapshot":
            project = cmd.get("project", "all")
            rc, out, err = run_kenbotctl(["snapshot", "--project", project])
            return {"ok": rc == 0, "rc": rc, "stdout": out[-3000:], "stderr": err[-500:]}

        if action == "shell":
            if not ALLOW_SHELL:
                return {"ok": False, "error": "shell désactivé (KENBOT_ALLOW_SHELL=1 pour activer)"}
            shell_cmd = cmd.get("cmd")
            if not shell_cmd:
                return {"ok": False, "error": "cmd requis"}
            proc = subprocess.run(shell_cmd, shell=True, capture_output=True, text=True, timeout=120, cwd=str(REPO_DIR))
            return {"ok": proc.returncode == 0, "rc": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-500:]}

        return {"ok": False, "error": f"action inconnue: {action}"}

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        log.exception("execute_command failed")
        return {"ok": False, "error": str(e)}


# ─── Queue loop (inbox/processing/outbox) ─────────────────────
def process_one_file(filepath):
    """Move filepath → processing → execute → write outbox → delete processing."""
    name = filepath.name
    processing_path = PROCESSING / name
    try:
        filepath.rename(processing_path)
    except OSError as e:
        log.warning(f"Race condition (déjà déplacé) sur {name}: {e}")
        return

    correlation_id = str(uuid.uuid4())[:8]
    try:
        cmd = json.loads(processing_path.read_text())
    except Exception as e:
        result = {"ok": False, "error": f"JSON invalide: {e}", "correlation_id": correlation_id}
    else:
        log.info(f"[{correlation_id}] traitement {name}")
        result = execute_command(cmd)
        result["correlation_id"] = correlation_id
        result["processed_at"] = datetime.now(timezone.utc).isoformat()

    out_path = OUTBOX / f"result_{name}"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    processing_path.unlink(missing_ok=True)

    status = "✅" if result.get("ok") else "❌"
    log.info(f"[{correlation_id}] {status} {name} → {out_path.name}")
    if not result.get("ok"):
        notify_mac("Kenbot Daemon ❌", f"{name}: {result.get('error', 'failed')[:80]}")


def queue_loop(stop_event):
    log.info(f"📥 queue_loop démarré (poll={QUEUE_POLL_SECONDS}s, inbox={INBOX})")
    while not stop_event.is_set():
        try:
            for f in sorted(INBOX.glob("*.json")):
                if stop_event.is_set():
                    break
                process_one_file(f)
            write_heartbeat()
        except Exception:
            log.exception("queue_loop iteration failed")
        stop_event.wait(QUEUE_POLL_SECONDS)
    log.info("📥 queue_loop arrêté")


# ─── Watchdog loop (snapshot + auto-restore) ──────────────────
def _load_last_snapshot(project):
    """Retourne le snapshot le plus récent pour un projet (dict) ou None."""
    snap_dir = REPO_DIR / "memory" / "render_snapshots"
    files = sorted(snap_dir.glob(f"{project}_snapshot_*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text())
    except Exception:
        return None


def _watchdog_tick():
    """1 tick : snapshot chaque projet + auto-restore si vars critiques manquent depuis le dernier snapshot."""
    from sys import path as syspath
    syspath.insert(0, str(REPO_DIR / "devops"))
    try:
        from contexts import get_context  # type: ignore
        from protect_render_envvars import CRITICAL_VARS, RenderEnvProtector  # type: ignore
        from render_client import RenderClient  # type: ignore
    except Exception:
        log.exception("Imports devops impossibles — vérifie KENBOT_REPO_DIR")
        return

    client = RenderClient()
    for project in WATCHDOG_PROJECTS:
        project = project.strip()
        if not project:
            continue
        # 1. Snapshot frais
        try:
            previous = _load_last_snapshot(project)
            RenderEnvProtector(project).snapshot()
        except Exception:
            log.exception(f"snapshot {project} échec")
            continue

        if not previous:
            log.info(f"watchdog {project} : pas d'historique, rien à comparer")
            continue

        # 2. Auto-restore : pour chaque service, comparer aux vars critiques
        critical = CRITICAL_VARS.get(project, set())
        if not critical:
            continue

        ctx = get_context(project)
        for svc in ctx.filtered_services():
            svc_obj = svc.get("service") or svc
            name = svc_obj.get("name")
            sid = svc_obj.get("id")
            if not (name and sid):
                continue
            now_vars = client.get_env_vars(sid)
            prev_data = previous.get("services", {}).get(name, {})
            prev_vars = prev_data.get("env_vars", {})

            # Vars critiques que l'on avait AVANT et qu'on n'a PLUS maintenant → restore
            disparues = {
                k for k in critical
                if k in prev_vars and k not in now_vars
            }
            if not disparues:
                continue
            log.warning(f"⚠️  {project}/{name} a perdu : {', '.join(sorted(disparues))} — auto-restore")
            notify_mac(
                "Kenbot Watchdog ⚠️",
                f"{name} a perdu {len(disparues)} var(s) critique(s) — restauration auto",
            )
            for key in disparues:
                value = prev_vars[key]
                try:
                    ok = client.set_env_var(sid, key, value)
                    log.info(f"   restore {key} → {'OK' if ok else 'FAIL'}")
                except Exception:
                    log.exception(f"restore {key} échec")


def watchdog_loop(stop_event):
    log.info(f"🛡️  watchdog_loop démarré (interval={WATCHDOG_INTERVAL_SECONDS}s, projects={WATCHDOG_PROJECTS})")
    while not stop_event.is_set():
        try:
            _watchdog_tick()
            write_heartbeat()
        except Exception:
            log.exception("watchdog_tick failed")
        stop_event.wait(WATCHDOG_INTERVAL_SECONDS)
    log.info("🛡️  watchdog_loop arrêté")


# ─── HTTP webhook (localhost:7777) ────────────────────────────
class WebhookHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # silence default stderr
        log.info("HTTP " + (fmt % args))

    def _auth_ok(self):
        if not HTTP_TOKEN:  # daemon refuse tout si token vide
            return False
        return self.headers.get("X-Daemon-Token") == HTTP_TOKEN

    def do_GET(self):
        if self.path in ("/health", "/healthz"):
            self._send_json(200, {"ok": True, "ts": datetime.now(timezone.utc).isoformat()})
            return
        if self.path == "/status":
            if not self._auth_ok():
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return
            self._send_json(200, {
                "ok": True,
                "heartbeat": HEARTBEAT.read_text() if HEARTBEAT.exists() else None,
                "inbox_pending": len(list(INBOX.glob("*.json"))),
                "outbox_results": len(list(OUTBOX.glob("*.json"))),
                "watchdog_enabled": WATCHDOG_ENABLED,
            })
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/cmd":
            self._send_json(404, {"ok": False, "error": "not found"})
            return
        if not self._auth_ok():
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"ok": False, "error": f"bad json: {e}"})
            return
        result = execute_command(payload)
        self._send_json(200 if result.get("ok") else 500, result)


def http_loop(stop_event):
    if not HTTP_ENABLED:
        log.info("🌐 http server désactivé")
        return
    if not HTTP_TOKEN:
        log.warning("🌐 KENBOT_DAEMON_TOKEN vide → http server démarre mais refuse toutes les requêtes")
    server = ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), WebhookHandler)
    log.info(f"🌐 http server localhost:{HTTP_PORT} (POST /cmd, GET /status, GET /health)")

    def _shutdown_watcher():
        stop_event.wait()
        server.shutdown()

    threading.Thread(target=_shutdown_watcher, daemon=True, name="http-shutdown").start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        log.info("🌐 http server arrêté")


# ─── Main ────────────────────────────────────────────────────
def main():
    stop_event = threading.Event()

    def _sig(signum, _frame):
        log.info(f"signal {signum} reçu — arrêt propre")
        stop_event.set()

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    log.info("🚀 Kenbot Daemon V2 démarré")
    log.info(f"   DAEMON_DIR={DAEMON_DIR}")
    log.info(f"   REPO_DIR={REPO_DIR}")
    write_heartbeat()
    notify_mac("Kenbot Daemon", "🚀 Démarré")

    threads = [
        threading.Thread(target=queue_loop, args=(stop_event,), daemon=True, name="queue"),
    ]
    if WATCHDOG_ENABLED:
        threads.append(threading.Thread(target=watchdog_loop, args=(stop_event,), daemon=True, name="watchdog"))
    if HTTP_ENABLED:
        threads.append(threading.Thread(target=http_loop, args=(stop_event,), daemon=True, name="http"))

    for t in threads:
        t.start()

    # main thread = heartbeat tick toutes les 30s + monitor des threads
    try:
        while not stop_event.is_set():
            write_heartbeat()
            for t in threads:
                if not t.is_alive():
                    log.error(f"thread {t.name} mort — arrêt du daemon")
                    stop_event.set()
                    break
            stop_event.wait(30)
    finally:
        log.info("👋 Kenbot Daemon arrêté")
        notify_mac("Kenbot Daemon", "👋 Arrêté")


if __name__ == "__main__":
    main()
