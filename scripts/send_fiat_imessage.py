#!/usr/bin/env python3
"""
send_fiat_imessage.py — Envoi PERSONNALISÉ d'offres Fiat via Messages.app (iMessage/SMS).

Différence vs send_fiat_offers.py (Twilio):
  - Envoie depuis TON numéro de cellulaire personnel via iMessage
  - Bulle bleue si client a un iPhone, verte sinon (Continuity SMS via iPhone)
  - Pas de coût Twilio, pas d'A2P 10DLC ni Toll-Free verification
  - 100% personnalisé — le client voit un texto de Daniel Giroux

PRÉREQUIS :
  1. macOS Messages.app signé dans iCloud avec ton Apple ID
  2. iPhone : Réglages → Messages → Transfert SMS → Mac activé
  3. Mac : Préférences → Confidentialité → Automation → autoriser Terminal/Python pour Messages

USAGE :
  Dry-run (par défaut, aucun envoi) :
    python3 scripts/send_fiat_imessage.py

  Test sur 1 numéro :
    python3 scripts/send_fiat_imessage.py --send --test-phone 418-222-3939

  Envoi RÉEL aux 13 clients :
    python3 scripts/send_fiat_imessage.py --send

  Trigger Apple Shortcut iPhone (POST sur webhook daemon localhost:7777) :
    Voir scripts/iphone_shortcut_fiat_trigger.md
"""
import os
import re
import sys
import time
import argparse
import subprocess
from pathlib import Path

# === LISTE DES CLIENTS ===
OFFERS = [
    {"name": "Ronald Roy",         "phone": "418-222-7091"},
    {"name": "Claudette Morin",    "phone": "418-227-5006"},
    {"name": "Vianney Giguère",    "phone": "581-305-3538"},
    {"name": "Ghyslain Bédard",    "phone": "418-225-6172"},
    {"name": "Chantal Hood",       "phone": "418-957-6399"},
    {"name": "Eric Turcotte",      "phone": "418-226-7704"},
    {"name": "Carl Paquet",        "phone": "",            "note": "voir texto"},
    {"name": "Simon",              "phone": "",            "note": "voir FB Messenger"},
    {"name": "Réjean Gaudet",      "phone": "418-625-0000", "note": "# à vérifier"},
    {"name": "Joël Bessette",      "phone": "450-543-3337"},
    {"name": "Diane Nadeau",       "phone": "418-427-3226"},
    {"name": "Louis Cyr",          "phone": "418-956-1350"},
    {"name": "Carmen Poulin",      "phone": "418-313-2100"},
    {"name": "Mathieu Simoneau",   "phone": "418-221-4389"},
    {"name": "Jonathan Campeau",   "phone": "581-372-1995"},
]

# === MESSAGE PERSONNALISÉ (plus court, ton casual — vient de TON cell) ===
MESSAGE_TEMPLATE = """Salut {first_name}! Daniel Giroux de Kennebec Dodge ici 👋

Comme demandé, voici l'offre Fiat 500 2026:

🚗 Location 48 mois
🚗 12 000 km/an
🚗 69,95$/sem + tx

Véhicule neuf, livraison rapide à St-Georges.

Tu veux qu'on se voit ou plus d'infos? Stéphane Quirion (directeur ventes) au 418-228-5575 ou simplement répondre ici 📱"""


def normalize_phone(phone: str) -> str:
    """Convertit '418-222-7091' en E.164 '+14182227091'."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return ""


def generate_message(name: str) -> str:
    return MESSAGE_TEMPLATE.format(first_name=name.split()[0])


def send_imessage(phone_e164: str, body: str) -> dict:
    """Envoie via Messages.app sur macOS en utilisant osascript."""
    # Escape pour AppleScript (double-quotes + backslashes)
    safe_body = body.replace("\\", "\\\\").replace('"', '\\"')
    # AppleScript: essaie iMessage d'abord, fallback SMS si pas iMessage
    script = f'''
on run
    tell application "Messages"
        set targetService to missing value
        try
            set targetService to 1st service whose service type = iMessage
        end try
        if targetService is missing value then
            try
                set targetService to 1st service whose service type = SMS
            end try
        end if
        if targetService is missing value then
            return "ERROR:no_service"
        end if
        set targetBuddy to participant "{phone_e164}" of targetService
        send "{safe_body}" to targetBuddy
        return "OK:" & (service type of targetService as string)
    end tell
end run
'''
    try:
        r = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=15
        )
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if out.startswith("OK:"):
            return {"ok": True, "service": out.split(":", 1)[1]}
        return {"ok": False, "error": err or out or "unknown"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "osascript timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="Envoyer réellement (sinon dry-run)")
    ap.add_argument("--test-phone", help="N'envoyer qu'à ce numéro (pour test)")
    ap.add_argument("--delay", type=float, default=3.0, help="Délai entre envois (s)")
    args = ap.parse_args()

    if sys.platform != "darwin":
        print("⚠️  Ce script doit tourner sur macOS (utilise Messages.app)")
        sys.exit(1)

    mode = "🔴 ENVOI RÉEL via iMessage/Messages.app" if args.send else "🟡 DRY-RUN (aucun envoi)"
    print(f"\n{'='*60}\n{mode}\nFiat 500 2026 — Campagne perso depuis ton cell\n{'='*60}\n")

    valid = []
    skipped = []
    for client in OFFERS:
        phone_e164 = normalize_phone(client["phone"])
        if not phone_e164:
            skipped.append(client)
            continue
        if args.test_phone and normalize_phone(args.test_phone) != phone_e164:
            continue
        valid.append({**client, "phone_e164": phone_e164})

    print(f"📋 {len(valid)} numéros valides | {len(skipped)} skipped (à traiter manuellement)\n")

    results = {"sent": 0, "failed": 0, "errors": []}
    for i, client in enumerate(valid, 1):
        msg = generate_message(client["name"])
        print(f"\n[{i}/{len(valid)}] 📱 {client['name']:25} → {client['phone_e164']}")
        print("-" * 60)
        print(msg)
        print("-" * 60)

        if args.send:
            r = send_imessage(client["phone_e164"], msg)
            if r.get("ok"):
                print(f"   ✅ Envoyé via {r.get('service', '?')}")
                results["sent"] += 1
            else:
                print(f"   ❌ ÉCHEC: {r.get('error', '?')}")
                results["failed"] += 1
                results["errors"].append({"name": client["name"], "error": r.get("error")})
            time.sleep(args.delay)
        else:
            print("   🟡 DRY-RUN — non envoyé")

    if skipped:
        print(f"\n⚠️  {len(skipped)} clients à traiter manuellement:")
        for s in skipped:
            print(f"   - {s['name']:25} ({s.get('note', 'pas de #')})")

    if args.send:
        print(f"\n{'='*60}")
        print(f"📊 RÉSUMÉ: {results['sent']} envoyés | {results['failed']} échecs")
        if results["errors"]:
            for e in results["errors"]:
                print(f"   ❌ {e['name']}: {e['error']}")
        print('='*60)


if __name__ == "__main__":
    main()
