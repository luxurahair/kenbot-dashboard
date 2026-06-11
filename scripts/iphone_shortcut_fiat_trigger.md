# 🔴 Apple Shortcut "Campagne Fiat" — Big Red Button

Permet de déclencher l'envoi de toute la campagne Fiat depuis ton iPhone (1 tap ou par Siri).

## Architecture

```
iPhone "Campagne Fiat" tap
   ↓ POST kenbot-dashboard-api.onrender.com/api/grok/voice
     {"prompt": "lance la campagne fiat 500"}
   ↓ Supabase agent_queue (action=ai)
   ↓ Daemon V3 Mac → Grok traduit
   ↓ kenbotctl OU exécution directe du script
   ↓ Messages.app envoie iMessage à chaque client
   ↓ Siri lit le résumé: "13 SMS envoyés avec succès"
```

## Création du Shortcut iPhone (60 secondes)

App **Raccourcis** → **+** → Nomme-le `Campagne Fiat`

### 4 actions à ajouter :

#### 1. Obtenir le contenu de l'URL
- **URL** : `https://kenbot-dashboard-api.onrender.com/api/grok/voice`
- **Méthode** : POST
- **En-têtes** :
  - `Content-Type` = `application/json`
  - `X-Voice-Token` = `<ton GROK_VOICE_TOKEN>`
- **Corps** : JSON
  - `prompt` = (texte fixe) `lance la campagne fiat 500 en mode envoi reel`

#### 2. Obtenir la valeur du dictionnaire
- **Obtenir** : Valeur
- **Pour** : `speech`
- **Dans** : variable magique `Contenu de l'URL`

#### 3. Énoncer le texte
- **Texte** : variable magique `Valeur du dictionnaire`
- **Voix** : Amélie (Français Canada)

#### 4. Afficher la notification (optionnel)
- **Titre** : "Campagne Fiat"
- **Corps** : variable magique `Valeur du dictionnaire`

### Activation Siri

Tape **⌄** en haut → **Ajouter à Siri** → enregistre la phrase :
- *"Campagne Fiat"* ou
- *"Envoie les offres"* ou
- *"Big Red Button"*

## Usage

### Mode 1 — Bouton physique iPhone
Tape sur le widget Raccourci sur ton écran d'accueil → ça envoie aux 13 clients automatiquement.

### Mode 2 — Vocal Siri
*"Dis Siri, Campagne Fiat"* → ça part tout seul.

## Sécurité

- Le `GROK_VOICE_TOKEN` est requis dans le header — sans ce token, l'endpoint refuse 401
- Le daemon V3 vérifie la signature HMAC avant d'exécuter
- Tu peux ajouter dans le Shortcut un **"Demander confirmation"** avant le POST pour éviter les déclenchements accidentels

## Pour préparer le déclencheur côté daemon Mac

Le AI_SYSTEM_PROMPT doit comprendre "lance la campagne fiat 500" → traduire en exécution du script.

Quand `KENBOT_ALLOW_SHELL=1`, Grok peut emit :
```json
{"action": "shell",
 "cmd": "cd ~/kenbot-dashboard && python3 scripts/send_fiat_imessage.py --send",
 "timeout": 300}
```

Sinon (mode sécurisé actuel), Daniel doit lancer manuellement :
```bash
cd ~/kenbot-dashboard
python3 scripts/send_fiat_imessage.py --send
```

## Test recommandé AVANT lancement réel

```bash
# 1. Test avec UN seul SMS sur ton propre numéro
python3 scripts/send_fiat_imessage.py --send --test-phone 418-222-3939

# 2. Vérifie que tu reçois le iMessage sur ton iPhone

# 3. Lance l'envoi RÉEL aux 13 clients
python3 scripts/send_fiat_imessage.py --send
```
