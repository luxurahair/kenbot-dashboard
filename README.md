# kenbot-runner

Runner Render (cron 60 min) :
- scrape 3 pages Kennebec
- diff NEW/SOLD/PRICE_CHANGED
- appelle kenbot-text-engine pour générer texte FB
- publie sur Facebook (10 photos + 5 extra best-effort)
- persiste dans Supabase (inventory/posts/events)

Env vars (Render):
- KENBOT_FB_PAGE_ID
- KENBOT_FB_ACCESS_TOKEN
- KENBOT_TEXT_ENGINE_URL=https://kenbot-text-engine.onrender.com
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY
- KENBOT_BASE_URL=https://www.kennebecdodge.ca
- KENBOT_INVENTORY_PATH=/fr/inventaire-occasion/
