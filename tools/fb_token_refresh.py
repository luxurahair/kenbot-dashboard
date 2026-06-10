#!/usr/bin/env python3
"""
fb_token_refresh.py — Refresh / set le Facebook Page Access Token Luxura sur Render.

USAGE 1 — Tu colles un User Access Token (du Graph Explorer) :
    python3 scripts/fb_token_refresh.py --user-token "EAA..." [--apply]

USAGE 2 — Tu as FB_APP_ID + FB_APP_SECRET + un USER token court :
    python3 scripts/fb_token_refresh.py --user-token "EAA..." \\
        --app-id 1234567 --app-secret SECRET [--apply]

Le script :
  1. Détecte si le token est short-lived ou long-lived
  2. Si short-lived + app credentials fournis → exchange en long-lived (60 jours)
  3. Récupère le Page Access Token PERMANENT pour la page Luxura
  4. (Si --apply) Update les 8 services Render Luxura
  5. (Si --apply) Sauve dans .secrets.env local

Sans --apply : DRY-RUN (affiche le nouveau token sans rien modifier).
"""
import argparse
import os
import sys
import time
from urllib.parse import urlencode
from urllib.request import urlopen, Request
import json

# Page IDs par projet
PAGE_IDS = {
    "luxura": "1838415193042352",  # Luxura Distribution Extension Capillaire
    "kenbot": "693977443463728",   # Kennebec Dodge Chrysler (à confirmer si différent)
}
SERVICE_KEYWORDS = {
    "luxura": ["luxura"],
    "kenbot": ["kenbot", "beauce", "facebook"],
}
ENV_KEY_BY_PROJECT = {
    "luxura": "FB_PAGE_ACCESS_TOKEN",
    "kenbot": "KENBOT_FB_PAGE_ACCESS_TOKEN",
}

# Backward-compat
PAGE_ID_DEFAULT = PAGE_IDS["luxura"]
LUXURA_SERVICES_KEYWORDS = SERVICE_KEYWORDS["luxura"]

GRAPH_BASE = "https://graph.facebook.com/v23.0"


def http_get(url, timeout=15):
    with urlopen(Request(url), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def debug_token(token):
    """Renvoie les métadonnées du token (expiration, scopes, user_id)."""
    try:
        return http_get(f"{GRAPH_BASE}/debug_token?input_token={token}&access_token={token}")
    except Exception as e:
        return {"error": str(e)}


def exchange_long_lived(short_token, app_id, app_secret):
    """Échange short-lived user token → long-lived user token (60 jours)."""
    params = urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": short_token,
    })
    data = http_get(f"{GRAPH_BASE}/oauth/access_token?{params}")
    return data.get("access_token"), data.get("expires_in")


def get_page_access_token(user_token, page_id):
    """Depuis un user token (de préférence long-lived), récupère le Page Access Token.

    Si le user_token est long-lived, le Page Access Token retourné est PERMANENT.
    """
    params = urlencode({"access_token": user_token, "limit": 100})
    data = http_get(f"{GRAPH_BASE}/me/accounts?{params}")
    for page in data.get("data", []):
        if page.get("id") == page_id:
            return page.get("access_token"), page.get("name")
    raise RuntimeError(f"Page {page_id} introuvable parmi les pages de ce user token")


def update_render_services(new_token, service_keywords, env_key):
    """Update env var sur tous les services matching les keywords."""
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "devops"))
    from render_client import RenderClient  # type: ignore
    c = RenderClient()
    updated = []
    for s in c.list_services():
        name = c.get_name(s)
        if not any(k in name.lower() for k in service_keywords):
            continue
        sid = (s.get("service") or s).get("id")
        envs = c.get_env_vars(sid)
        if env_key not in envs:
            continue
        ok = c.set_env_var(sid, env_key, new_token)
        if ok:
            updated.append(name)
            print(f"   ✅ {name}")
        else:
            print(f"   ❌ {name} — échec set_env_var")
        time.sleep(0.4)  # Render API rate limit gentle
    return updated


def verify_page_token(token, expected_page_id):
    """SAFEGUARD: vérifie que le token est bien type=PAGE pour la bonne page."""
    meta = debug_token(token)
    info = meta.get("data", {}) if "data" in meta else {}
    if info.get("type") != "PAGE":
        raise RuntimeError(f"❌ SAFEGUARD: token type={info.get('type')} (attendu PAGE). Refus de propager.")
    if info.get("expires_at", 1) != 0:
        print(f"⚠️  Token n'est pas permanent (expire={info.get('expires_at')})")
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-token", required=True, help="User Access Token depuis Graph Explorer")
    ap.add_argument("--app-id", default=os.environ.get("FB_APP_ID"))
    ap.add_argument("--app-secret", default=os.environ.get("FB_APP_SECRET"))
    ap.add_argument("--project", choices=["luxura", "kenbot"], default="luxura",
                    help="Projet cible (luxura ou kenbot)")
    ap.add_argument("--page-id", default=None, help="Override le page-id par défaut du projet")
    ap.add_argument("--apply", action="store_true", help="Vraiment update Render + .secrets.env")
    args = ap.parse_args()

    # Sélection projet
    page_id = args.page_id or PAGE_IDS[args.project]
    keywords = SERVICE_KEYWORDS[args.project]
    env_key = ENV_KEY_BY_PROJECT[args.project]
    print(f"🎯 Projet={args.project}  page_id={page_id}  env_key={env_key}")

    print(f"🔍 Inspection du token fourni...")
    meta = debug_token(args.user_token)
    if "error" in meta:
        print(f"❌ Token invalide: {meta['error']}")
        sys.exit(1)
    info = meta.get("data", {})
    exp = info.get("expires_at", 0)
    is_long = (exp == 0) or (exp - time.time()) > 60 * 24 * 3600  # >60 jours = long-lived
    print(f"   user_id = {info.get('user_id')}")
    print(f"   type    = {info.get('type')}")
    print(f"   app_id  = {info.get('app_id')}")
    print(f"   scopes  = {info.get('scopes')}")
    print(f"   expire  = {'permanent' if exp == 0 else time.strftime('%Y-%m-%d %H:%M', time.localtime(exp))} ({'long-lived' if is_long else 'short-lived'})")

    user_token = args.user_token

    if not is_long:
        if not (args.app_id and args.app_secret):
            print("\n⚠️  Token short-lived. Fournis --app-id et --app-secret pour exchange.")
            print("   Sinon → utilise Graph API Explorer puis 'Extend Access Token' avant de relancer.")
            sys.exit(2)
        print("\n🔄 Exchange short → long-lived...")
        user_token, expires_in = exchange_long_lived(args.user_token, args.app_id, args.app_secret)
        print(f"   ✅ nouveau user token long-lived (expire dans {expires_in}s = ~{expires_in//86400}j)")

    print(f"\n📘 Récupération du Page Access Token pour la page {page_id}...")
    page_token, page_name = get_page_access_token(user_token, page_id)
    print(f"   ✅ Page: '{page_name}'")
    print(f"   ✅ Token (preview): {page_token[:30]}...")

    # SAFEGUARD: refuse de propager si ce n'est pas un PAGE token
    print(f"\n🛡️  Vérification SAFEGUARD: type doit être PAGE...")
    page_info = verify_page_token(page_token, page_id)
    print(f"   ✅ type={page_info.get('type')}  expires_at={page_info.get('expires_at')} (0=permanent)")

    if not args.apply:
        print("\n=== DRY-RUN — rien n'a été modifié ===")
        print(f"\nNew {env_key}:\n{page_token}\n")
        print("Pour appliquer : ajoute --apply à la commande.")
        return

    print(f"\n📤 Update services Render {args.project} (keywords={keywords})...")
    updated = update_render_services(page_token, keywords, env_key)
    print(f"\n✅ {len(updated)} service(s) mis à jour")

    # Persiste localement — supporte le nouveau path ~/kenbot-dashboard
    candidates = [
        os.path.expanduser("~/kenbot-dashboard/.secrets.env"),
        os.path.expanduser("~/Desktop/kenbot-dashboard/.secrets.env"),
        "/app/.secrets.env",
    ]
    secrets_path = next((p for p in candidates if os.path.exists(p)), None)
    if secrets_path:
        with open(secrets_path, "r") as f:
            lines = f.readlines()
        updated_lines = [l for l in lines if not l.startswith(f"{env_key}=")]
        updated_lines.append(f"{env_key}={page_token}\n")
        with open(secrets_path, "w") as f:
            f.writelines(updated_lines)
        print(f"💾 Sauvé dans {secrets_path}")

    print("\n💡 Redémarre les services pour appliquer (ils prennent les nouvelles vars au prochain run)")
    print("   python3 devops/kenbotctl.py kenbot  # voir l'état actuel")


if __name__ == "__main__":
    main()
