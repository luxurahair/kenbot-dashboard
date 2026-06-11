# 🎙️ Apple Shortcut Voice Grok — Guide d'installation iPhone

## Vue d'ensemble

Permet de piloter Kenbot par la voix depuis n'importe où dans le monde via Siri.

```
Toi → "Dis Siri, Kenbot, redémarre kenbot-runner"
 → POST https://kenbot-dashboard-api.onrender.com/api/grok/voice
 → Supabase agent_queue
 → Mac Daemon V3 + Grok
 → Siri lit la réponse
```

## Configuration du Shortcut iOS

### 4 actions à créer dans l'app Raccourcis :

#### 1. Dicter du texte
- **Langue** : Français (Canada)
- **Arrêter l'écoute** : Au toucher

#### 2. Obtenir le contenu de l'URL
- **URL** : `https://kenbot-dashboard-api.onrender.com/api/grok/voice`
- **Méthode** : POST
- **En-têtes** :
  - `Content-Type` = `application/json`
  - `X-Voice-Token` = `<ton GROK_VOICE_TOKEN>`
- **Demander le corps** : JSON
  - `prompt` = variable magique `Texte dicté`

#### 3. Obtenir la valeur du dictionnaire
- **Obtenir** : Valeur
- **Pour** : `speech`
- **Dans** : variable magique `Contenu de l'URL`

#### 4. Énoncer le texte
- **Texte** : variable magique `Valeur du dictionnaire`
- **Voix** : Amélie ou Thomas (Français Canada)
- **Attendre la fin** : Activé

### Ajouter à Siri
Tape sur le nom du Shortcut → **Ajouter à Siri** → enregistre la phrase d'activation (ex: "Kenbot").

## Activation token

Le `GROK_VOICE_TOKEN` est généré côté serveur et stocké dans Render env vars du service `kenbot-dashboard-api`.

Pour le récupérer/régénérer :
```bash
# Via Render API
curl -H "Authorization: Bearer $RENDER_API_KEY" \
  "https://api.render.com/v1/services/srv-d7da02tckfvc73en2g9g/env-vars?limit=100" \
  | grep GROK_VOICE_TOKEN
```

## Exemples de phrases qui marchent

| Tu dis | Action générée |
|---|---|
| Redémarre **kenbot-runner** | restart |
| Combien j'ai de variables sur **kenbot-dashboard-api** | env-list |
| Vérifie l'état de Render | snapshot project=all |
| Fais un snapshot | snapshot project=all |
| Diagnostic du projet kenbot | kenbotctl diagnostic |
| Lis-moi le README | read_file |
| Mets TEST_VAR à bonjour sur kenbot-runner | env-set |
