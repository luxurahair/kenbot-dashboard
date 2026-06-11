#!/usr/bin/env python3
"""
Kenbot Daemon V3 — Local Mac Agent + AI Mode + Dashboard + Templates + Push
==============================================================================
V3 ajoute (en plus de V2) :
  🔥 ai            : "redémarre le runner" → daemon traduit via Claude → exécute
  📊 GET /         : Dashboard HTML live (status, queue, logs)
  🔔 push notif    : Ntfy.sh (gratuit, pas de compte) + macOS native
  🎯 templates     : commands/templates/*.json rejouables via {"action":"template", "name":"X"}
  📲 Apple Shortcut: voir kenbot-daemon/README.md (section Shortcut iPhone)

Boucles concurrentes (inchangées vs V2) :
  1. queue_loop       → exécute les JSON drop dans commands/inbox/
  2. watchdog_loop    → snapshot toutes les N min + auto-restore vars critiques perdues
  3. http_server      → webhook localhost:7777 (POST /cmd, GET /status, GET /, GET /health)
"""
import json
import logging
import os
import re
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
TEMPLATES = DAEMON_DIR / "commands/templates"
LOG_DIR = DAEMON_DIR / "logs"
HEARTBEAT = DAEMON_DIR / "heartbeat.txt"

QUEUE_POLL_SECONDS = int(os.environ.get("KENBOT_QUEUE_POLL", "10"))
WATCHDOG_INTERVAL_SECONDS = int(os.environ.get("KENBOT_WATCHDOG_INTERVAL", "1800"))
WATCHDOG_PROJECTS = os.environ.get("KENBOT_WATCHDOG_PROJECTS", "kenbot,luxura,calcauto").split(",")
WATCHDOG_ENABLED = os.environ.get("KENBOT_WATCHDOG_ENABLED", "1") == "1"
HTTP_PORT = int(os.environ.get("KENBOT_HTTP_PORT", "7777"))
HTTP_ENABLED = os.environ.get("KENBOT_HTTP_ENABLED", "1") == "1"
HTTP_TOKEN = os.environ.get("KENBOT_DAEMON_TOKEN", "")
ALLOW_SHELL = os.environ.get("KENBOT_ALLOW_SHELL", "0") == "1"
NOTIFY_MACOS = os.environ.get("KENBOT_NOTIFY_MACOS", "1") == "1"

# V3 ajouts
NTFY_TOPIC = os.environ.get("KENBOT_NTFY_TOPIC", "")
NTFY_SERVER = os.environ.get("KENBOT_NTFY_SERVER", "https://ntfy.sh")
SMS_ENABLED = os.environ.get("KENBOT_SMS_ENABLED", "0") == "1"
SMS_PHONE = os.environ.get("KENBOT_SMS_PHONE", "")  # ex: +14182223939
TWILIO_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_TOK = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.environ.get("TWILIO_FROM_NUMBER", "")
AI_ENABLED = os.environ.get("KENBOT_AI_ENABLED", "1") == "1"
AI_PROVIDER = os.environ.get("KENBOT_AI_PROVIDER", "xai")  # xai|openai|emergent
AI_MODEL = os.environ.get("KENBOT_AI_MODEL", "grok-4-fast-non-reasoning")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

for d in (INBOX, PROCESSING, OUTBOX, TEMPLATES, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ─── Logging ──────────────────────────────────────────────────
log = logging.getLogger("kenbot-daemon")
log.setLevel(logging.INFO)
_handler = RotatingFileHandler(LOG_DIR / "daemon.log", maxBytes=2_000_000, backupCount=5)
_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(threadName)s — %(message)s"))
log.addHandler(_handler)
log.addHandler(logging.StreamHandler(sys.stdout))

# ─── Notifications (macOS + Ntfy push iPhone) ─────────────────
def notify_mac(title, message):
    if NOTIFY_MACOS:
        try:
            subprocess.run(
                ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
                check=False, timeout=5,
            )
        except Exception:
            pass
    notify_ntfy(title, message)
    notify_sms(title, message)


def notify_sms(title, message):
    """Envoi SMS Twilio pour alertes critiques uniquement (économise les $$)."""
    if not (SMS_ENABLED and SMS_PHONE and TWILIO_SID and TWILIO_TOK and TWILIO_FROM):
        return
    try:
        from twilio.rest import Client
        tw = Client(TWILIO_SID, TWILIO_TOK)
        body = f"{title}\n{message}"[:300]
        tw.messages.create(from_=TWILIO_FROM, to=SMS_PHONE, body=body)
        log.info(f"📲 SMS Twilio envoyé à …{SMS_PHONE[-4:]}")
    except ImportError:
        log.warning("twilio non installé : pip3 install twilio --user")
    except Exception as e:
        log.warning(f"SMS Twilio échec: {e}")


def notify_ntfy(title, message, priority="default", tags=None):
    """Push notification via ntfy.sh (gratuit, iPhone hors Wi-Fi)."""
    if not NTFY_TOPIC:
        return
    try:
        import urllib.request
        url = f"{NTFY_SERVER.rstrip('/')}/{NTFY_TOPIC}"
        headers = {
            "Title": title.encode("utf-8"),
            "Priority": priority,
        }
        if tags:
            headers["Tags"] = ",".join(tags)
        req = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=5).read()
    except Exception as e:
        log.warning(f"ntfy push échec: {e}")


def write_heartbeat():
    HEARTBEAT.write_text(datetime.now(timezone.utc).isoformat())


def run_kenbotctl(args, timeout=120):
    cmd = ["python3", "devops/kenbotctl.py"] + list(args)
    proc = subprocess.run(cmd, cwd=str(REPO_DIR), capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout, proc.stderr


# ─── AI Mode (langage naturel → JSON command) ─────────────────
AI_SYSTEM_PROMPT = """Tu es un assistant DevOps qui traduit des requêtes en français québécois
(langage naturel, anglicismes acceptés) en une commande JSON unique exécutable par le daemon Kenbot.

ACTIONS DISPONIBLES :
  - {"action":"restart","service":"NOM"}           # redémarre un service Render
  - {"action":"env-set","service":"NOM","key":"K","value":"V"}  # set/update env var
  - {"action":"env-list","service":"NOM"}          # liste env vars
  - {"action":"snapshot","project":"kenbot|luxura|calcauto|all"}
  - {"action":"kenbotctl","args":["sous-cmd","--flag","val"]}   # passe-plat générique
  - {"action":"read_file","path":"/chemin/relatif"}  # lit un fichier dans le repo

SERVICES TYPIQUES :
  kenbot-dashboard-api, kenbot-runner, kenbot-news-publisher, kenbot-beauce-runner,
  kenbot-beauce-purge-cron, kenbot-beauce-audit-cron, kenbot-beauce-price-sync-cron,
  calcauto-aipro, luxura-multi-tape-0730, luxura-multi-itip-2030, luxura-blog-cron,
  luxura-content-scan, luxura-inventory-sync, facebook-educational-posts,
  facebook-weekend-posts, facebook-product-posts

ANGLICISMES À RECONNAÎTRE (ne JAMAIS refuser à cause d'un mot anglais) :
  - "GitHub" / "Git" / "repo" → contexte de code
  - "Render" → plateforme de déploiement (utiliser snapshot ou kenbotctl diagnostic)
  - "status" / "statut" / "état" / "santé" / "health" / "running" / "up" / "down"
    → utiliser kenbotctl diagnostic ou snapshot pour avoir un aperçu
  - "deploy" / "déploiement" / "push" / "release" → restart du service concerné
  - "logs" / "log" → kenbotctl args=["logs","--service","NOM"]
  - "kill" / "tue" / "arrête" → restart (équivalent fonctionnel)
  - "vérifie" / "check" / "test" / "ping" → snapshot du projet pertinent
  - "Render", "GitHub", "Vercel", "Supabase", "Twilio", "Facebook", "FB", "Mac",
    "iMac", "iPhone", "iPad", "iCloud" sont des PROPRE NOUNS reconnus

MAPPING INTELLIGENT (toujours convertir, JAMAIS refuser) :
  - "combien de services" / "combien j'ai de" → {"action":"snapshot","project":"all"}
  - "vérifie Render" / "état Render" / "santé du système" → {"action":"snapshot","project":"all"}
  - "tous mes services" → {"action":"snapshot","project":"all"}
  - "diagnostic kenbot|luxura|calcauto" → {"action":"kenbotctl","args":["diagnostic","--project","NOM"]}
  - "lis le README" / "ouvre le README" → {"action":"read_file","path":"README.md"}
  - "logs de X" → {"action":"kenbotctl","args":["logs","--service","X"]}

DEVINER LE SERVICE QUAND NON SPÉCIFIÉ :
  - "le runner" / "le bot principal" → "kenbot-runner"
  - "l'API" / "le dashboard" / "le backend" → "kenbot-dashboard-api"
  - "le news cron" / "les news" / "KDC News" → "kenbot-news-publisher"
  - "Beauce" / "le publisher Beauce" → "kenbot-beauce-runner"
  - "CalcAuto" / "factures" / "OCR" → "calcauto-aipro"
  - "Luxura" sans précision → "luxura-multi-tape-0730"
  - Si VRAIMENT impossible de deviner ET la phrase mentionne "service" sans nom →
    réponds {"action":"error","message":"Précise quel service (ex: kenbot-runner)"}

RÈGLES STRICTES :
  - Réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans texte autour.
  - Préfère deviner intelligemment plutôt que refuser. L'utilisateur est québécois et mélange français + anglais.
  - Si vraiment impossible (action inexistante), réponds {"action":"error","message":"raison courte et claire"}.
  - Les noms de services Render sont en kebab-case (avec tirets).
"""


def _ai_key_available():
    """Vrai si la clé du provider AI actuel est dispo."""
    if AI_PROVIDER == "xai":
        return bool(os.environ.get("XAI_API_KEY"))
    if AI_PROVIDER == "openai":
        return bool(os.environ.get("OPENAI_API_KEY") or EMERGENT_LLM_KEY)
    if AI_PROVIDER == "emergent":
        return bool(EMERGENT_LLM_KEY)
    return False


def ai_translate(prompt):
    """Traduit une phrase FR en command JSON via le provider AI configuré.

    Providers supportés :
      - xai     : Grok via api.x.ai (clé: XAI_API_KEY)        ← recommandé Kenbot
      - openai  : GPT via api.openai.com (clé: OPENAI_API_KEY ou EMERGENT_LLM_KEY)
      - emergent: via librarie emergentintegrations (proxy Emergent)
    """
    if AI_PROVIDER == "xai":
        return _ai_translate_xai(prompt)
    if AI_PROVIDER == "openai":
        return _ai_translate_openai(prompt)
    if AI_PROVIDER == "emergent":
        return _ai_translate_emergent(prompt)
    return {"action": "error", "message": f"Provider AI inconnu: {AI_PROVIDER}"}


def _extract_json(text):
    """Extrait un objet JSON même si l'IA met du markdown/texte autour."""
    if not text:
        return None
    # Retire ```json ... ``` ou ``` ... ```
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = text.replace("```", "")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _ai_translate_xai(prompt):
    """Appel direct xai/grok via httpx (zéro dépendance lourde)."""
    key = os.environ.get("XAI_API_KEY", "")
    if not key:
        return {"action": "error", "message": "XAI_API_KEY manquante dans l'environnement"}
    try:
        import urllib.request
        body = json.dumps({
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.x.ai/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _extract_json(text)
        if not parsed:
            return {"action": "error", "message": f"Pas de JSON dans la réponse Grok: {text[:200]}"}
        return parsed
    except Exception as e:
        log.exception("xai translate failed")
        return {"action": "error", "message": f"xai échec: {e}"}


def _ai_translate_openai(prompt):
    """Appel direct OpenAI Chat Completion via httpx."""
    key = os.environ.get("OPENAI_API_KEY") or EMERGENT_LLM_KEY
    if not key:
        return {"action": "error", "message": "OPENAI_API_KEY manquante"}
    try:
        import urllib.request
        body = json.dumps({
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": AI_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _extract_json(text)
        if not parsed:
            return {"action": "error", "message": f"Pas de JSON dans la réponse OpenAI: {text[:200]}"}
        return parsed
    except Exception as e:
        log.exception("openai translate failed")
        return {"action": "error", "message": f"openai échec: {e}"}


def _ai_translate_emergent(prompt):
    """Via emergentintegrations (proxy Emergent — Anthropic ne marche pas, openai/gemini OK)."""
    if not EMERGENT_LLM_KEY:
        return {"action": "error", "message": "EMERGENT_LLM_KEY manquante"}
    try:
        import asyncio
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        async def _run():
            chat = LlmChat(
                api_key=EMERGENT_LLM_KEY,
                session_id=f"kenbot-daemon-{uuid.uuid4().hex[:8]}",
                system_message=AI_SYSTEM_PROMPT,
            ).with_model("openai", AI_MODEL)
            return await chat.send_message(UserMessage(text=prompt))

        text = asyncio.run(_run())
        parsed = _extract_json(text)
        if not parsed:
            return {"action": "error", "message": f"Pas de JSON dans la réponse: {text[:200]}"}
        return parsed
    except ImportError:
        return {"action": "error", "message": "emergentintegrations non installé"}
    except Exception as e:
        log.exception("emergent translate failed")
        return {"action": "error", "message": f"emergent échec: {e}"}


# ─── Templates ────────────────────────────────────────────────
def load_template(name, overrides=None):
    """Charge un template JSON et applique des overrides. Supporte {{var}} substitution."""
    path = TEMPLATES / f"{name}.json"
    if not path.exists():
        # Liste les disponibles
        available = sorted(p.stem for p in TEMPLATES.glob("*.json"))
        return {"action": "error", "message": f"Template '{name}' introuvable. Disponibles: {', '.join(available) or '(aucun)'}"}
    raw = path.read_text(encoding="utf-8")
    # Substitution {{var}} depuis overrides
    if overrides:
        for k, v in overrides.items():
            raw = raw.replace(f"{{{{{k}}}}}", str(v))
    try:
        return json.loads(raw)
    except Exception as e:
        return {"action": "error", "message": f"Template JSON invalide: {e}"}


# ─── Executor ─────────────────────────────────────────────────
def execute_command(cmd):
    """Dispatch un dict commande vers l'action correspondante. Retourne dict résultat."""
    action = (cmd.get("action") or "").lower()
    log.info(f"Action={action} payload={ {k:v for k,v in cmd.items() if k != 'value'} }")

    try:
        # V3 : AI mode
        if action == "ai":
            prompt = cmd.get("prompt") or cmd.get("text")
            if not prompt:
                return {"ok": False, "error": "'prompt' requis"}
            if not AI_ENABLED:
                return {"ok": False, "error": "AI désactivé (KENBOT_AI_ENABLED=0)"}
            translated = ai_translate(prompt)
            log.info(f"AI translated '{prompt}' → {translated}")
            if translated.get("action") == "error":
                return {"ok": False, "error": translated.get("message"), "ai_translated": translated}
            # Exécute la commande traduite récursivement
            result = execute_command(translated)
            result["ai_translated"] = translated
            return result

        # V3 : Template mode
        if action == "template":
            name = cmd.get("name")
            if not name:
                return {"ok": False, "error": "'name' requis"}
            overrides = cmd.get("vars") or {}
            loaded = load_template(name, overrides)
            if loaded.get("action") == "error":
                return {"ok": False, "error": loaded.get("message")}
            # Si le template contient une liste d'étapes
            if isinstance(loaded, list) or (isinstance(loaded, dict) and "steps" in loaded):
                steps = loaded if isinstance(loaded, list) else loaded["steps"]
                results = []
                for i, step in enumerate(steps):
                    r = execute_command(step)
                    results.append({"step": i, "cmd": step, "result": r})
                    if not r.get("ok"):
                        return {"ok": False, "error": f"Step {i} failed", "results": results}
                return {"ok": True, "results": results}
            return execute_command(loaded)

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

        # ── V3.1 cloud agent : write_file ──
        if action == "write_file":
            path = cmd.get("path")
            content = cmd.get("content", "")
            if not path:
                return {"ok": False, "error": "path requis"}
            # Sécurité : limite aux dossiers Kenbot uniquement
            ALLOWED_ROOTS = [str(REPO_DIR), str(DAEMON_DIR)]
            real = os.path.realpath(path)
            if not any(real.startswith(r) for r in ALLOWED_ROOTS):
                return {"ok": False, "error": f"path hors zones autorisées ({ALLOWED_ROOTS})"}
            try:
                os.makedirs(os.path.dirname(real), exist_ok=True)
                if cmd.get("append"):
                    with open(real, "a", encoding="utf-8") as f:
                        f.write(content)
                else:
                    with open(real, "w", encoding="utf-8") as f:
                        f.write(content)
                return {"ok": True, "path": real, "bytes": len(content)}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        if action == "read_file":
            path = cmd.get("path")
            if not path:
                return {"ok": False, "error": "path requis"}
            ALLOWED_ROOTS = [str(REPO_DIR), str(DAEMON_DIR)]
            real = os.path.realpath(path)
            if not any(real.startswith(r) for r in ALLOWED_ROOTS):
                return {"ok": False, "error": "path hors zones autorisées"}
            try:
                with open(real, "r", encoding="utf-8") as f:
                    content = f.read()
                return {"ok": True, "path": real, "content": content[-50000:], "bytes": len(content)}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        return {"ok": False, "error": f"action inconnue: {action}"}

    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        log.exception("execute_command failed")
        return {"ok": False, "error": str(e)}


# ─── Queue loop ───────────────────────────────────────────────
def process_one_file(filepath):
    name = filepath.name
    processing_path = PROCESSING / name
    try:
        filepath.rename(processing_path)
    except OSError as e:
        log.warning(f"Race condition sur {name}: {e}")
        return

    correlation_id = str(uuid.uuid4())[:8]
    try:
        cmd = json.loads(processing_path.read_text(encoding="utf-8"))
    except Exception as e:
        result = {"ok": False, "error": f"JSON invalide: {e}", "correlation_id": correlation_id}
    else:
        log.info(f"[{correlation_id}] traitement {name}")
        result = execute_command(cmd)
        result["correlation_id"] = correlation_id
        result["processed_at"] = datetime.now(timezone.utc).isoformat()

    out_path = OUTBOX / f"result_{name}"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    processing_path.unlink(missing_ok=True)

    status = "✅" if result.get("ok") else "❌"
    log.info(f"[{correlation_id}] {status} {name} → {out_path.name}")
    if not result.get("ok"):
        notify_mac("Kenbot Daemon ❌", f"{name}: {result.get('error', 'failed')[:80]}")
    else:
        notify_ntfy("Kenbot Daemon ✅", f"{name} OK", tags=["white_check_mark"])


def queue_loop(stop_event):
    log.info(f"📥 queue_loop démarré (poll={QUEUE_POLL_SECONDS}s)")
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


# ─── Watchdog ─────────────────────────────────────────────────
def _load_last_snapshot(project):
    snap_dir = REPO_DIR / "memory" / "render_snapshots"
    files = sorted(snap_dir.glob(f"{project}_snapshot_*.json"))
    if not files:
        return None
    try:
        return json.loads(files[-1].read_text(encoding="utf-8"))
    except Exception:
        return None


def _watchdog_tick():
    sys.path.insert(0, str(REPO_DIR / "devops"))
    try:
        from contexts import get_context  # type: ignore
        from protect_render_envvars import CRITICAL_VARS, RenderEnvProtector  # type: ignore
        from render_client import RenderClient  # type: ignore
    except Exception:
        log.exception("Imports devops impossibles")
        return

    client = RenderClient()
    for project in WATCHDOG_PROJECTS:
        project = project.strip()
        if not project:
            continue
        try:
            previous = _load_last_snapshot(project)
            RenderEnvProtector(project).snapshot()
        except Exception:
            log.exception(f"snapshot {project} échec")
            continue

        if not previous:
            continue

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
            disparues = {k for k in critical if k in prev_vars and k not in now_vars}
            if not disparues:
                continue
            log.warning(f"⚠️  {project}/{name} a perdu : {', '.join(sorted(disparues))} — auto-restore")
            notify_mac("Kenbot Watchdog ⚠️", f"{name}: restore {len(disparues)} var(s)")
            for key in disparues:
                try:
                    ok = client.set_env_var(sid, key, prev_vars[key])
                    log.info(f"   restore {key} → {'OK' if ok else 'FAIL'}")
                except Exception:
                    log.exception(f"restore {key} échec")


def watchdog_loop(stop_event):
    log.info(f"🛡️  watchdog_loop démarré (interval={WATCHDOG_INTERVAL_SECONDS}s)")
    while not stop_event.is_set():
        try:
            _watchdog_tick()
            write_heartbeat()
        except Exception:
            log.exception("watchdog_tick failed")
        stop_event.wait(WATCHDOG_INTERVAL_SECONDS)
    log.info("🛡️  watchdog_loop arrêté")


# ─── HTTP webhook + Dashboard ─────────────────────────────────
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><title>Kenbot Daemon</title>
<meta http-equiv="refresh" content="10">
<style>
  body{margin:0;background:#0b0f0c;color:#e6f0ea;font-family:-apple-system,BlinkMacSystemFont,Roboto,sans-serif;}
  .wrap{max-width:980px;margin:0 auto;padding:24px 18px;}
  h1{margin:0 0 18px;color:#22c55e;font-weight:800;letter-spacing:-0.01em;font-size:28px;}
  .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px;margin-bottom:22px;}
  .card{border:1px solid rgba(34,197,94,0.25);background:rgba(34,197,94,0.05);border-radius:10px;padding:14px 16px;}
  .card .label{font-size:11px;color:#22c55e;text-transform:uppercase;letter-spacing:0.08em;font-weight:800;margin-bottom:6px;}
  .card .val{font-size:24px;font-weight:800;color:#fff;}
  .card.warn{border-color:#ef4444;background:rgba(239,68,68,0.06);}
  .card.warn .label{color:#ef4444;}
  pre{background:#000;border:1px solid #222;border-radius:8px;padding:12px;overflow:auto;max-height:300px;font-size:12px;color:#9ca3af;}
  .row{display:flex;justify-content:space-between;border-bottom:1px solid rgba(34,197,94,0.12);padding:8px 0;}
  .ok{color:#22c55e;}.ko{color:#ef4444;}
  small{color:#666;}
  h2{color:#22c55e;font-size:16px;margin-top:24px;border-bottom:1px solid rgba(34,197,94,0.2);padding-bottom:6px;}
</style></head><body><div class="wrap">
<h1>🛡️ Kenbot Daemon — Dashboard</h1>
<div class="grid">__CARDS__</div>
<h2>📥 Dernières commandes (outbox)</h2>
__OUTBOX__
<h2>📜 Log (50 dernières lignes)</h2>
<pre>__LOG__</pre>
<small>Auto-refresh toutes les 10s · <a href="/health" style="color:#22c55e;">/health</a></small>
</div></body></html>"""


def render_dashboard():
    # Status cards
    hb_age = "—"
    if HEARTBEAT.exists():
        try:
            hb_dt = datetime.fromisoformat(HEARTBEAT.read_text().strip())
            age_s = (datetime.now(timezone.utc) - hb_dt).total_seconds()
            hb_age = f"{int(age_s)}s"
        except Exception:
            pass

    pending = len(list(INBOX.glob("*.json")))
    processing = len(list(PROCESSING.glob("*.json")))
    done = len(list(OUTBOX.glob("*.json")))
    cards = [
        ("Heartbeat", hb_age, ""),
        ("Inbox", str(pending), "warn" if pending > 5 else ""),
        ("Processing", str(processing), "warn" if processing > 0 else ""),
        ("Outbox total", str(done), ""),
        ("Watchdog", "ON" if WATCHDOG_ENABLED else "OFF", "" if WATCHDOG_ENABLED else "warn"),
        ("AI mode", "ON" if (AI_ENABLED and EMERGENT_LLM_KEY) else "OFF", ""),
    ]
    cards_html = "".join(
        f'<div class="card {cls}"><div class="label">{lbl}</div><div class="val">{val}</div></div>'
        for lbl, val, cls in cards
    )

    # Outbox récent (10 derniers)
    outs = sorted(OUTBOX.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:10]
    out_rows = []
    for f in outs:
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            ok = d.get("ok", False)
            badge = '<span class="ok">✅</span>' if ok else '<span class="ko">❌</span>'
            name = f.name.replace("result_", "")
            ts = d.get("processed_at", "")[:19].replace("T", " ")
            out_rows.append(f'<div class="row"><span>{badge} {name}</span><span>{ts}</span></div>')
        except Exception:
            continue
    out_html = "".join(out_rows) or '<div class="row"><span>(aucun résultat)</span></div>'

    # Log tail
    log_path = LOG_DIR / "daemon.log"
    log_tail = ""
    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()[-50:]
                log_tail = "".join(lines).replace("<", "&lt;").replace(">", "&gt;")
        except Exception:
            log_tail = "(log unavailable)"

    return DASHBOARD_HTML.replace("__CARDS__", cards_html).replace("__OUTBOX__", out_html).replace("__LOG__", log_tail)


class WebhookHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, status, html):
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        log.info("HTTP " + (fmt % args))

    def _auth_ok(self):
        if not HTTP_TOKEN:
            return False
        # Token via header OU query param ?t=... (utile pour Apple Shortcut simple)
        if self.headers.get("X-Daemon-Token") == HTTP_TOKEN:
            return True
        if f"t={HTTP_TOKEN}" in (self.path or ""):
            return True
        return False

    def do_GET(self):
        # Dashboard HTML — auth via query param ?t=TOKEN
        if self.path.startswith("/") and (self.path == "/" or self.path.startswith("/?")):
            if not self._auth_ok():
                self._send_html(401, "<h1>401 — Ajoute ?t=TOKEN à l'URL</h1>")
                return
            self._send_html(200, render_dashboard())
            return
        if self.path in ("/health", "/healthz"):
            self._send_json(200, {"ok": True, "ts": datetime.now(timezone.utc).isoformat()})
            return
        if self.path.startswith("/status"):
            if not self._auth_ok():
                self._send_json(401, {"ok": False, "error": "unauthorized"})
                return
            self._send_json(200, {
                "ok": True,
                "heartbeat": HEARTBEAT.read_text() if HEARTBEAT.exists() else None,
                "inbox_pending": len(list(INBOX.glob("*.json"))),
                "outbox_results": len(list(OUTBOX.glob("*.json"))),
                "watchdog_enabled": WATCHDOG_ENABLED,
                "ai_enabled": AI_ENABLED and _ai_key_available(),
                "templates": sorted(p.stem for p in TEMPLATES.glob("*.json")),
            })
            return
        self._send_json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        if self.path != "/cmd" and not self.path.startswith("/cmd?"):
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
        # 2026-06-09: déclenche aussi les notifs sur erreur via webhook HTTP (pas seulement queue)
        if not result.get("ok"):
            notify_mac("Kenbot Daemon ❌", str(result.get("error") or "failed")[:120])
        self._send_json(200 if result.get("ok") else 500, result)


def http_loop(stop_event):
    if not HTTP_ENABLED:
        return
    if not HTTP_TOKEN:
        log.warning("🌐 KENBOT_DAEMON_TOKEN vide → refuse toutes les requêtes")
    server = ThreadingHTTPServer(("127.0.0.1", HTTP_PORT), WebhookHandler)
    log.info(f"🌐 http server localhost:{HTTP_PORT} — / (dashboard), POST /cmd, GET /status, GET /health")

    def _shutdown():
        stop_event.wait()
        server.shutdown()
    threading.Thread(target=_shutdown, daemon=True, name="http-shutdown").start()
    try:
        server.serve_forever()
    finally:
        server.server_close()


# ─── Main ────────────────────────────────────────────────────
def main():
    stop_event = threading.Event()

    def _sig(signum, _frame):
        log.info(f"signal {signum} reçu — arrêt propre")
        stop_event.set()

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    log.info("🚀 Kenbot Daemon V3 démarré")
    log.info(f"   DAEMON_DIR={DAEMON_DIR}")
    log.info(f"   REPO_DIR={REPO_DIR}")
    log.info(f"   AI={'ON' if (AI_ENABLED and _ai_key_available()) else 'OFF'} ({AI_PROVIDER}/{AI_MODEL})")
    log.info(f"   NTFY topic={'set' if NTFY_TOPIC else '(empty)'}")
    log.info(f"   SMS Twilio={'ON' if (SMS_ENABLED and SMS_PHONE) else 'OFF'} (→ …{SMS_PHONE[-4:] if SMS_PHONE else ''})")
    write_heartbeat()
    notify_mac("Kenbot Daemon", "🚀 V3 démarré")

    threads = [threading.Thread(target=queue_loop, args=(stop_event,), daemon=True, name="queue")]
    if WATCHDOG_ENABLED:
        threads.append(threading.Thread(target=watchdog_loop, args=(stop_event,), daemon=True, name="watchdog"))
    if HTTP_ENABLED:
        threads.append(threading.Thread(target=http_loop, args=(stop_event,), daemon=True, name="http"))
    # V3.1 supabase poll (cloud agent → mon Mac)
    try:
        import sys as _sys
        _sys.path.insert(0, str(DAEMON_DIR))
        from supabase_queue import poll_loop as _supa_poll
        threads.append(threading.Thread(target=_supa_poll, args=(stop_event, execute_command), daemon=True, name="supabase"))
    except Exception as _e:
        log.warning(f"supabase_queue import skipped: {_e}")

    for t in threads:
        t.start()

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
