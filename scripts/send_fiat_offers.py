#!/usr/bin/env python3
"""
send_fiat_offers.py — Envoi automatique d'offres Fiat 500 2026 par SMS via Twilio.

USAGE:
  Dry-run (par défaut) — affiche les messages sans envoyer:
    python3 scripts/send_fiat_offers.py

  Envoi réel:
    python3 scripts/send_fiat_offers.py --send

  Test sur ton propre numéro uniquement:
    python3 scripts/send_fiat_offers.py --send --test-phone 418-222-3939

ENV REQUIRED:
  TWILIO_ACCOUNT_SID
  TWILIO_AUTH_TOKEN
  TWILIO_FROM_NUMBER  (numéro approuvé pour B2C)

Source list: liste manuscrite Fiat 2026 (Stéphane Quirion - Kennebec Dodge Chrysler).
"""
import os
import re
import sys
import time
import argparse
from pathlib import Path

# === LISTE DES CLIENTS (extracted from image) ===
OFFERS = [
    {"name": "Ronald Roy",         "phone": "418-222-7091"},
    {"name": "Claudette Morin",    "phone": "418-227-5006", "note": "10t/15"},
    {"name": "Vianney Giguère",    "phone": "581-305-3538"},
    {"name": "Ghyslain Bédard",    "phone": "418-225-6172"},
    {"name": "Chantal Hood",       "phone": "418-957-6399"},
    {"name": "Eric Turcotte",      "phone": "418-226-7704"},
    {"name": "Carl Paquet",        "phone": "",            "note": "voir texto (pas de # dans liste)"},
    {"name": "Simon",              "phone": "",            "note": "voir FB Messenger (pas de # dans liste)"},
    {"name": "Réjean Gaudet",      "phone": "418-625-0000", "note": "# à vérifier — semble fictif"},
    {"name": "Joël Bessette",      "phone": "450-543-3337"},
    {"name": "Diane Nadeau",       "phone": "418-427-3226"},
    {"name": "Louis Cyr",          "phone": "418-956-1350"},
    {"name": "Carmen Poulin",      "phone": "418-313-2100"},
    {"name": "Mathieu Simoneau",   "phone": "418-221-4389"},
    {"name": "Jonathan Campeau",   "phone": "581-372-1995"},
]

# === MESSAGE TEMPLATE ===
MESSAGE_TEMPLATE = """Bonjour {first_name},

Suite à votre demande, voici l'offre sur la FIAT 500 2026:

📍 Location 48 mois
📍 12 000 km/an inclus
📍 69,95$/sem + taxes

✅ Véhicule neuf
✅ Inspection complète
✅ Livraison rapide à Saint-Georges

Pour réserver ou questions:
Stéphane Quirion - Directeur des ventes
Kennebec Dodge Chrysler
📞 418-228-5575

STOP = désinscription"""


def normalize_phone(phone: str) -> str:
    """Convertit '418-222-7091' en E.164 '+14182227091'. Retourne '' si invalide."""
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    return ""


def generate_message(name: str) -> str:
    first_name = name.split()[0]
    return MESSAGE_TEMPLATE.format(first_name=first_name)


def send_sms_twilio(to_phone_e164: str, body: str) -> dict:
    """Envoie via Twilio REST API. Retourne {ok, sid, error}."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
    token = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
    from_ = os.environ.get("TWILIO_FROM_NUMBER", "").strip()
    if not (sid and token and from_):
        return {"ok": False, "error": "Twilio env vars manquantes (SID/TOKEN/FROM)"}

    import urllib.request
    import urllib.parse
    import base64

    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    data = urllib.parse.urlencode({"To": to_phone_e164, "From": from_, "Body": body}).encode()
    auth = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req = urllib.request.Request(url, data=data, method="POST",
                                  headers={"Authorization": f"Basic {auth}"})
    try:
        import json as _json
        with urllib.request.urlopen(req, timeout=20) as r:
            d = _json.loads(r.read())
            return {"ok": True, "sid": d.get("sid", ""), "status": d.get("status", "")}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            import json as _json
            err = _json.loads(body)
            return {"ok": False, "error": err.get("message", body)[:200], "code": err.get("code")}
        except Exception:
            return {"ok": False, "error": body[:200]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="Envoyer réellement (sinon dry-run)")
    ap.add_argument("--test-phone", help="N'envoyer qu'à ce numéro (pour test)")
    ap.add_argument("--delay", type=float, default=2.0, help="Délai entre envois (s)")
    args = ap.parse_args()

    mode = "🔴 ENVOI RÉEL" if args.send else "🟡 DRY-RUN (aucun envoi)"
    print(f"\n{'='*60}\n{mode} — Offre Fiat 500 2026\n{'='*60}\n")

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

    print(f"📋 {len(valid)} numéros valides | {len(skipped)} skipped\n")

    results = {"sent": 0, "failed": 0, "errors": []}
    for i, client in enumerate(valid, 1):
        msg = generate_message(client["name"])
        print(f"\n[{i}/{len(valid)}] 📱 {client['name']:25} → {client['phone_e164']}")
        print("-" * 60)
        print(msg)
        print("-" * 60)

        if args.send:
            r = send_sms_twilio(client["phone_e164"], msg)
            if r.get("ok"):
                print(f"   ✅ Envoyé (SID={r.get('sid','')[:20]}, status={r.get('status','')})")
                results["sent"] += 1
            else:
                err = r.get("error", "?")
                code = r.get("code", "")
                print(f"   ❌ ÉCHEC: [{code}] {err}")
                results["failed"] += 1
                results["errors"].append({"name": client["name"], "error": err, "code": code})
            time.sleep(args.delay)
        else:
            print("   🟡 DRY-RUN — non envoyé")

    if skipped:
        print(f"\n⚠️  {len(skipped)} clients sans numéro valide (à traiter à la main):")
        for s in skipped:
            print(f"   - {s['name']:25} ({s.get('note', 'pas de #')})")

    if args.send:
        print(f"\n{'='*60}")
        print(f"📊 RÉSUMÉ: {results['sent']} envoyés | {results['failed']} échecs")
        if results["errors"]:
            print(f"\nErreurs:")
            for e in results["errors"]:
                print(f"   - {e['name']}: [{e['code']}] {e['error']}")
        print('='*60)


if __name__ == "__main__":
    main()
