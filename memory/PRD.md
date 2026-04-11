# PRD — Kenbot Dashboard + Fix + Intelligence Vehicule

## Date: 2026-04-11

## Ce qui a ete fait

### Session 1 - Fix PHOTOS_ADDED
- 3 bugs corriges dans runner_cron_prod.py (pousse sur GitHub)
- Dashboard admin cree avec React + FastAPI

### Session 2 - Dashboard Supabase Live
- Dashboard connecte aux vraies donnees Supabase
- 6 onglets: Dashboard, Inventaire, Posts FB, Events, Architecture, Changelog
- Bouton "Run Cron" avec options (Dry Run, Max targets, Force stock)
- Colonnes no_photo et photo_count ajoutees dans Supabase

### Session 3 - Intelligence Vehicule (EN COURS)
- Module vehicle_intelligence.py cree avec:
  - Base de connaissance 20+ marques (Dodge, Jeep, Ram, Ford, Toyota, etc.)
  - Specs par modele (Challenger, Wrangler, Ram 1500, Mustang, etc.)
  - Specs par trim (Scat Pack=485HP, Rubicon=off-road, GT=V8 Coyote, etc.)
  - Parse automatique du titre -> brand/model/trim/year
  - Description intelligente KM et prix
- Module llm_v3.py cree avec:
  - System prompt Daniel Giroux (vendeur quebecois authentique)
  - Prompts specifiques par type de vehicule
  - 5 styles d'intro aleatoires (direct, storytelling, question, expertise, opportunite)
  - Filtre anti-cliches post-generation
  - Options du sticker humanisees
- API endpoints: /vehicle-intelligence/{stock} et /generate-text/{stock}

## Fichiers crees
- /app/vehicle_intelligence.py - Base de connaissance vehicule
- /app/llm_v3.py - Generation texte v3 (OpenAI)
- /app/kenbot-runner-fix/ - Fichiers corriges originaux

### Session 4 - Audit Variables d'Environnement
- Extraction des variables Render depuis 5 screenshots -> RENDER_ENV_REFERENCE.md
- Audit complet: 30 variables mappees, 9 orphelines, ~20 absentes de Render (avec defaults), 4 divergences non bloquantes
- Rapport detaille genere -> AUDIT_ENV_VARIABLES.md

## Backlog
- P0: Integrer llm_v3 dans runner_cron_prod.py (remplacer l'ancien llm.py)
- P0: Tester la generation avec la cle OpenAI sur les vrais vehicules
- P1: Ajouter un onglet "Preview Texte" dans le dashboard
- P1: Enrichir la base de connaissance (plus de modeles)
- P1: Implementer les 9 variables Render orphelines dans le code (ou les retirer)
- P2: Multi-dealer (Luxura)
- P2: A/B testing des styles d'intro
- P2: Alertes/notifications (token FB expire, echec cron)
- P3: Decouper runner.py en services modulaires
