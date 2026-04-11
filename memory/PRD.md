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

### Session 5 - Test Generation IA sur Vrais Vehicules + Integration Runner
- Endpoint /api/generate-text/{stock} recrit avec emergentintegrations (GPT-4o)
- 5 vehicules reels testes avec succes:
  - Ford Mustang GT: V8 Coyote 450HP detecte, ton muscle car
  - Jeep Wrangler Rubicon 4XE: type off_road, hybride rechargeable
  - Chevrolet Malibu LT: type general, ton fiabilite/valeur
  - Honda Civic EX: type general, ton economie
  - Jeep Grand Cherokee Summit: type suv_premium, ton luxe
- Filtre anti-cliches ameliore (ajout "routes de la Beauce" etc.)
- Endpoint /api/test-batch-generate ajoute pour tester le parsing en batch
- **llm_v3 integre dans runner_cron_prod.py**:
  - Priorite 1: generate_smart_text_v3 (nouveau moteur IA)
  - Priorite 2: sticker_to_ad (ancien pipeline Stellantis)
  - Priorite 3: text_engine externe (fallback)
  - Options sticker passees a llm_v3 pour enrichir le texte IA

### Session 6 - Onglet Preview Texte (Dashboard)
- Nouvel onglet "Preview Texte" dans le dashboard
- Liste des vehicules actifs avec recherche (stock, titre, VIN)
- Selection avec surbrillance, header vehicule avec stock/VIN/prix/km
- Panneau Intelligence Vehicule: marque, modele, trim, type, moteur/HP, vibe, km, prix
- Generation IA via GPT-4o (emergentintegrations): affichage texte + chars + style + modele
- Boutons GENERER TEXTE, HUMANISER STICKER (Stellantis), COPIER
- Humanisation sticker Stellantis: intro IA + titre vendeur + options ✅ MAJUSCULES + sous-options ▫️ minuscules + footer intact
- Filtre anti-vulgarite ajoute (prompt + post-process)
- Decodage VIN via NHTSA integre: moteur, HP, transmission, drive, places, securite
  - vin_decoder.py: module de decodage VIN (API NHTSA gratuite, cache memoire)
  - Enrichit automatiquement vehicle_intelligence quand les specs manquent
  - Tags visuels dans le dashboard: 4WD, Automatic, Hybrid, places, securite
- Tests: 27/27 backend + 100% frontend (iteration_3.json)

## Backlog
- P0: Push sur GitHub via "Save to Github" pour deployer llm_v3 sur Render
- P1: Enrichir la base de connaissance (plus de modeles)
- P1: Implementer les 9 variables Render orphelines dans le code (ou les retirer)
- P2: Multi-dealer (Luxura)
- P2: A/B testing des styles d'intro
- P2: Alertes/notifications (token FB expire, echec cron)
- P3: Decouper runner.py en services modulaires
