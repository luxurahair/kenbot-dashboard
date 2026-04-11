from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import sys
from pathlib import Path as _Path

# Add parent dir to path for kenbot modules
sys.path.insert(0, str(_Path(__file__).parent.parent))
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
from supabase import create_client as sb_create_client

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB (for dashboard state)
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Supabase (for kenbot real data)
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
sb = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        sb = sb_create_client(SUPABASE_URL, SUPABASE_KEY)
        logging.info("Supabase connected!")
    except Exception as e:
        logging.error(f"Supabase connection failed: {e}")

app = FastAPI()
api_router = APIRouter(prefix="/api")

# ─── Models ───
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

# ─── Supabase helpers ───
def sb_query(table, select="*", filters=None, order=None, limit=None, count=False):
    if not sb:
        return {"data": [], "count": 0}
    try:
        q = sb.table(table).select(select, count="exact" if count else "planned")
        if filters:
            for key, val in filters.items():
                q = q.eq(key, val)
        if order:
            q = q.order(order, desc=True)
        if limit:
            q = q.limit(limit)
        result = q.execute()
        return {"data": result.data or [], "count": result.count if count else len(result.data or [])}
    except Exception as e:
        logging.error(f"Supabase query error on {table}: {e}")
        return {"data": [], "count": 0}

# ─── Changelog ───
CHANGELOG = [
    {
        "version": "3.0.0",
        "date": "2026-04-11",
        "type": "feature",
        "title": "AI v3.0 — Generation intelligente par vehicule",
        "changes": [
            {"severity": "critical", "description": "Nouveau moteur de texte llm_v3.py: prompts adaptes par type de vehicule (muscle_car, off_road, suv_premium, pickup, etc.)", "file": "llm_v3.py"},
            {"severity": "critical", "description": "Module vehicle_intelligence.py: parsing titre, detection marque/modele/trim, specs moteur (HP, engine), base 20+ marques", "file": "vehicle_intelligence.py"},
            {"severity": "medium", "description": "5 styles d'intro aleatoires (direct, storytelling, question, expertise, opportunite)", "file": "llm_v3.py"},
            {"severity": "medium", "description": "Filtre anti-cliches ameliore: 'routes de la Beauce', 'paysages beauceron' etc.", "file": "llm_v3.py"},
            {"severity": "low", "description": "Teste avec succes sur 5 vrais vehicules: Mustang GT (V8 450HP), Wrangler Rubicon 4XE, Malibu LT, Civic EX, Grand Cherokee Summit", "file": "server.py"},
            {"severity": "critical", "description": "llm_v3 integre dans runner_cron_prod.py: Priorite 1 = llm_v3, Priorite 2 = sticker_to_ad, Priorite 3 = text_engine", "file": "runner_cron_prod.py"},
        ]
    },
    {
        "version": "2.2.0",
        "date": "2026-04-11",
        "type": "feature",
        "title": "Audit Variables Environnement Render vs Code",
        "changes": [
            {"severity": "medium", "description": "30 variables Render correctement mappees au code", "file": "AUDIT_ENV_VARIABLES.md"},
            {"severity": "medium", "description": "9 variables Render orphelines identifiees (jamais lues par le code)", "file": "AUDIT_ENV_VARIABLES.md"},
            {"severity": "low", "description": "~20 variables du code absentes de Render (avec bons defaults)", "file": "AUDIT_ENV_VARIABLES.md"},
        ]
    },
    {
        "version": "2.1.0",
        "date": "2026-04-11",
        "type": "bugfix",
        "title": "FIX PHOTOS_ADDED - 3 bugs corriges",
        "changes": [
            {"severity": "critical", "description": "Flag no_photo jamais mis a True lors de la creation d'un post NEW avec fallback NO_PHOTO", "fix": "Nouvelle fonction _is_no_photo_fallback() + no_photo=True / photo_count=0 quand fallback utilise", "file": "runner_cron_prod.py", "line": "~380"},
            {"severity": "critical", "description": "Mauvais ordre d'arguments _build_ad_text(sb, v, 'NEW', run_id) dans PHOTOS_ADDED", "fix": "Corrige en _build_ad_text(sb, run_id, slug, v, 'NEW')", "file": "runner_cron_prod.py", "line": "~310"},
            {"severity": "medium", "description": "Detection 'no photo' trop restrictive - mots-cles manquants dans base_text", "fix": "Ajout de mots-cles: 'sans photo', 'photo a venir', 'photos a venir', 'no_photo'", "file": "runner_cron_prod.py", "line": "~250"},
        ]
    },
    {
        "version": "2.0.0",
        "date": "2026-04-08",
        "type": "feature",
        "title": "AI v2.0 + Fix double footer + Cliches interdits",
        "changes": [
            {"severity": "medium", "description": "Textes plus longs (400 chars au lieu de 220)", "file": "llm.py"},
            {"severity": "medium", "description": "Liste de cliches INTERDITS (sillonner la Beauce, etc.)", "file": "llm.py"},
            {"severity": "low", "description": "Footer centralise via footer_utils.py", "file": "footer_utils.py"},
        ]
    },
]

# ─── Architecture ───
ARCHITECTURE = {
    "components": [
        {"id": "website", "name": "Site Kennebec", "type": "external", "description": "kennebecdodge.ca - Source inventaire"},
        {"id": "scraper", "name": "kennebec_scrape.py", "type": "module", "description": "Scraping HTML + parsing vehicules"},
        {"id": "runner", "name": "runner_cron_prod.py", "type": "core", "description": "Chef d'orchestre - Pipeline principal"},
        {"id": "supabase", "name": "Supabase", "type": "storage", "description": "Tables: inventory, posts, events + Storage"},
        {"id": "text_engine", "name": "Text Engine", "type": "service", "description": "Generation textes FB (externe + AI)"},
        {"id": "sticker", "name": "sticker_to_ad.py", "type": "module", "description": "Extraction PDF Window Sticker"},
        {"id": "llm", "name": "llm.py", "type": "module", "description": "AI OpenAI - Intros humanisees"},
        {"id": "facebook", "name": "fb_api.py", "type": "external", "description": "Facebook Graph API - Publication"},
        {"id": "meta_feed", "name": "Meta Feed", "type": "output", "description": "CSV feed pour Meta Ads"},
    ],
    "flows": [
        {"from": "website", "to": "scraper", "label": "HTML pages"},
        {"from": "scraper", "to": "runner", "label": "Vehicules normalises"},
        {"from": "runner", "to": "supabase", "label": "State management"},
        {"from": "runner", "to": "text_engine", "label": "Generation texte"},
        {"from": "runner", "to": "sticker", "label": "PDF Stellantis"},
        {"from": "sticker", "to": "runner", "label": "Options extraites"},
        {"from": "llm", "to": "runner", "label": "Intro AI"},
        {"from": "runner", "to": "facebook", "label": "Publish/Update"},
        {"from": "runner", "to": "meta_feed", "label": "CSV export"},
    ],
    "states": ["NEW", "SOLD", "RESTORE", "PRICE_CHANGED", "PHOTOS_ADDED"]
}

# ─── Routes ───

@api_router.get("/")
async def root():
    return {"message": "Kenbot Dashboard API", "version": "2.1.0", "supabase_connected": sb is not None}

@api_router.get("/system/status")
async def get_system_status():
    if sb:
        inv_total = sb_query("inventory", "status", count=True)
        inv_active = sb_query("inventory", "status", filters={"status": "ACTIVE"}, count=True)
        inv_sold = sb_query("inventory", "status", filters={"status": "SOLD"}, count=True)
        posts_total = sb_query("posts", "status", count=True)
        posts_active = sb_query("posts", "status", filters={"status": "ACTIVE"}, count=True)
        events_total = sb_query("events", "id", count=True)
        
        # Check no_photo posts via base_text hints
        all_active_posts = sb_query("posts", "slug,base_text,stock", filters={"status": "ACTIVE"}, limit=500)
        no_photo_count = 0
        for p in all_active_posts["data"]:
            bt = (p.get("base_text") or "").lower()
            has_no_photo = p.get("no_photo")
            if has_no_photo is True or "photos suivront" in bt or "photo non disponible" in bt or "sans photo" in bt or "photo a venir" in bt:
                no_photo_count += 1

        # Last events
        last_events = sb_query("events", "*", order="created_at", limit=1)
        last_event = last_events["data"][0] if last_events["data"] else None

        return {
            "version": "2.1.0",
            "supabase_connected": True,
            "stats": {
                "inventory": {"total": inv_total["count"], "active": inv_active["count"], "sold": inv_sold["count"]},
                "posts": {"total": posts_total["count"], "active": posts_active["count"], "no_photo": no_photo_count, "with_photos": posts_active["count"] - no_photo_count},
                "events": {"total": events_total["count"]},
            },
            "last_event": {
                "slug": last_event.get("slug", ""),
                "type": last_event.get("type", ""),
                "timestamp": last_event.get("created_at", ""),
            } if last_event else None,
        }
    
    return {"version": "2.1.0", "supabase_connected": False, "stats": {}}

@api_router.get("/inventory")
async def get_inventory(status: Optional[str] = None, limit: int = 200):
    filters = {}
    if status:
        filters["status"] = status.upper()
    result = sb_query("inventory", "*", filters=filters, order="updated_at", limit=limit)
    return result["data"]

@api_router.get("/inventory/stats")
async def get_inventory_stats():
    total = sb_query("inventory", "status", count=True)
    active = sb_query("inventory", "status", filters={"status": "ACTIVE"}, count=True)
    sold = sb_query("inventory", "status", filters={"status": "SOLD"}, count=True)
    return {"total": total["count"], "active": active["count"], "sold": sold["count"]}

@api_router.get("/posts")
async def get_posts(status: Optional[str] = None, limit: int = 200):
    filters = {}
    if status:
        filters["status"] = status.upper()
    result = sb_query("posts", "*", filters=filters, order="published_at", limit=limit)
    
    # Detect no_photo from base_text hints if column doesn't exist
    for p in result["data"]:
        if "no_photo" not in p or p.get("no_photo") is None:
            bt = (p.get("base_text") or "").lower()
            p["no_photo"] = (
                "photos suivront" in bt or
                "photo non disponible" in bt or
                "sans photo" in bt or
                "photo a venir" in bt or
                "photos a venir" in bt or
                "nouveau vehicule en inventaire" in bt
            )
        if "photo_count" not in p or p.get("photo_count") is None:
            p["photo_count"] = 0 if p.get("no_photo") else -1
    
    return result["data"]

@api_router.get("/posts/stats")
async def get_posts_stats():
    total = sb_query("posts", "status", count=True)
    active = sb_query("posts", "status", filters={"status": "ACTIVE"}, count=True)
    sold = sb_query("posts", "status", filters={"status": "SOLD"}, count=True)
    
    all_active = sb_query("posts", "slug,base_text,stock", filters={"status": "ACTIVE"}, limit=500)
    no_photo = 0
    for p in all_active["data"]:
        bt = (p.get("base_text") or "").lower()
        has_flag = p.get("no_photo")
        if has_flag is True or "photos suivront" in bt or "photo non disponible" in bt or "sans photo" in bt:
            no_photo += 1
    
    return {"total": total["count"], "active": active["count"], "sold": sold["count"], "no_photo": no_photo, "with_photos": active["count"] - no_photo}

@api_router.get("/events")
async def get_events(limit: int = 50):
    result = sb_query("events", "*", order="created_at", limit=limit)
    return result["data"]

@api_router.get("/events/recent")
async def get_recent_events(limit: int = 20):
    result = sb_query("events", "*", order="created_at", limit=limit)
    # Group by type
    type_counts = {}
    for e in result["data"]:
        t = e.get("type", "UNKNOWN")
        type_counts[t] = type_counts.get(t, 0) + 1
    return {"events": result["data"], "type_counts": type_counts}

@api_router.get("/scrape-runs")
async def get_scrape_runs(limit: int = 20):
    result = sb_query("scrape_runs", "*", order="created_at", limit=limit)
    return result["data"]

@api_router.get("/sticker-pdfs")
async def get_sticker_pdfs(limit: int = 50):
    result = sb_query("sticker_pdfs", "*", order="created_at", limit=limit)
    return result["data"]

class RunOptions(BaseModel):
    model_config = ConfigDict(extra="ignore")
    dry_run: bool = False
    max_targets: int = 4
    force_stock: Optional[str] = None

@api_router.post("/trigger/run")
async def trigger_run(options: RunOptions = RunOptions()):
    if not sb:
        return {"ok": False, "message": "Supabase non connecte"}
    try:
        payload = {
            "dry_run": options.dry_run,
            "max_targets": options.max_targets,
            "force_stock": options.force_stock,
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": "kenbot-dashboard",
        }
        sb.table("events").insert({
            "slug": "BOOT",
            "type": "RUN_REQUESTED",
            "payload": payload,
        }).execute()
        return {"ok": True, "message": "Run demande! Le prochain cron va l'executer.", "payload": payload}
    except Exception as e:
        return {"ok": False, "message": str(e)}

@api_router.post("/trigger/force-stock")
async def trigger_force_stock(stock: str):
    if not sb:
        return {"ok": False, "message": "Supabase non connecte"}
    try:
        payload = {
            "force_stock": stock.strip().upper(),
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": "kenbot-dashboard",
        }
        sb.table("events").insert({
            "slug": "BOOT",
            "type": "FORCE_STOCK_REQUESTED",
            "payload": payload,
        }).execute()
        return {"ok": True, "message": f"Force stock {stock} demande!", "payload": payload}
    except Exception as e:
        return {"ok": False, "message": str(e)}

@api_router.get("/changelog")
async def get_changelog():
    return CHANGELOG

@api_router.get("/vehicle-intelligence/{stock}")
async def get_vehicle_intelligence(stock: str):
    """Retourne le profil intelligent d'un véhicule par stock."""
    if not sb:
        return {"error": "Supabase non connecte"}
    try:
        from vehicle_intelligence import build_vehicle_context
        result = sb.table("inventory").select("*").eq("stock", stock.upper()).limit(1).execute()
        if not result.data:
            return {"error": f"Vehicule {stock} non trouve"}
        vehicle = result.data[0]
        ctx = build_vehicle_context(vehicle)
        return {"vehicle": vehicle, "intelligence": ctx}
    except Exception as e:
        return {"error": str(e)}

@api_router.post("/generate-text/{stock}")
async def generate_text_for_vehicle(stock: str, event: str = "NEW"):
    """Génère un texte Facebook intelligent pour un véhicule via Emergent LLM."""
    if not sb:
        return {"ok": False, "error": "Supabase non connecte"}
    try:
        from vehicle_intelligence import build_vehicle_context, humanize_options
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        result = sb.table("inventory").select("*").eq("stock", stock.upper()).limit(1).execute()
        if not result.data:
            return {"ok": False, "error": f"Vehicule {stock} non trouve"}
        vehicle = result.data[0]
        ctx = build_vehicle_context(vehicle)

        # Decode VIN via NHTSA pour enrichir les specs
        vin_specs = None
        vin_specs_text = ""
        vin_val = (vehicle.get("vin") or "").strip()
        if len(vin_val) >= 11:
            try:
                from vin_decoder import decode_vin, format_specs_for_prompt, format_engine_line
                vin_specs = decode_vin(vin_val)
                if vin_specs:
                    vin_specs_text = format_specs_for_prompt(vin_specs)
                    # Enrichir le ctx avec les specs NHTSA si vehicle_intelligence n'a pas trouve
                    if not ctx.get("hp") and vin_specs.get("engine_hp"):
                        ctx["hp"] = vin_specs["engine_hp"]
                        eng = format_engine_line(vin_specs)
                        # Eviter "340 HP" en double dans l'affichage
                        ctx["engine"] = eng.replace(f" — {vin_specs['engine_hp']} HP", "")
            except Exception as e:
                print(f"[VIN_DECODE] {vin_val}: {e}")

        # Get sticker options if available
        options_text = ""
        post_result = sb.table("posts").select("base_text").eq("stock", stock.upper()).limit(1).execute()
        if post_result.data and post_result.data[0].get("base_text"):
            bt = post_result.data[0]["base_text"]
            if "ACCESSOIRES" in bt or "QUIPEMENTS" in bt:
                options_text = bt

        human_options = humanize_options(options_text) if options_text else []

        # Build specs info (avoid duplication with vin_specs_text)
        specs_info = []
        if not vin_specs_text:
            # Only add from vehicle_intelligence if we don't have NHTSA data
            if ctx.get("hp"):
                specs_info.append(f"Moteur: {ctx['engine']} — {ctx['hp']} chevaux")
            elif ctx.get("engine"):
                specs_info.append(f"Moteur: {ctx['engine']}")
        if ctx.get("trim_vibe"):
            specs_info.append(f"Ce trim: {ctx['trim_vibe']}")
        if ctx.get("model_known_for"):
            specs_info.append(f"Ce modele est connu pour: {ctx['model_known_for']}")
        if ctx.get("brand_identity"):
            specs_info.append(f"La marque {ctx['brand'].capitalize()}: {ctx['brand_identity']}")

        vtype = ctx.get("vehicle_type", "general")
        tone_map = {
            "muscle_car": "adrenaline et son du moteur",
            "pickup": "robustesse et capacite",
            "pickup_hd": "robustesse et capacite",
            "off_road": "aventure et liberte",
            "suv_premium": "confort et raffinement",
            "citadine": "style et economie",
            "suv_compact": "style et economie",
            "exotique": "exclusivite et reve",
            "collector": "exclusivite et reve",
        }
        tone = tone_map.get(vtype, "polyvalence et fiabilite")

        import random
        styles = ["direct", "storytelling", "question", "expertise", "opportunite"]
        style = random.choice(styles)

        system_msg = """Tu es Daniel Giroux, vendeur passionne chez Kennebec Dodge Chrysler a Saint-Georges en Beauce.
Tu ecris des annonces Facebook pour des vehicules d'occasion.

REGLES ABSOLUES:
- Tu ecris en francais quebecois naturel. Pas de francais de France. Pas de robot.
- Tu parles comme un VRAI vendeur qui connait ses chars. Pas de phrases generiques.
- JAMAIS de "Pret a dominer les routes" ou "faire tourner les tetes" — c'est cliche.
- JAMAIS de "sillonner la Beauce" ou "conquerir les chemins" — c'est du robot.
- JAMAIS mentionner "la Beauce", "routes de la Beauce" ou "paysages beauceron". On vend des chars, pas du tourisme.
- ABSOLUMENT AUCUN mot vulgaire, grossier ou a caractere sexuel. Pas de "couilles", "balls", "badass", "bitch", "cul", "merde" ou tout autre sacre/juron. C'est une page PROFESSIONNELLE d'un concessionnaire. Le ton est passionne mais TOUJOURS respectueux et professionnel.
- Chaque texte doit etre UNIQUE. Si tu vends un Challenger, parle du V8. Si c'est un Wrangler, parle du off-road.
- Le ton est direct, authentique, passionne. Comme si tu parlais a un client au showroom.
- Tu CONNAIS les vehicules. Tu sais ce qui rend chaque modele special.
- Maximum 3-4 phrases pour l'intro. Pas de roman.
- Pas de hashtags dans l'intro.
- Pas d'emojis dans l'intro (ils viennent apres dans le corps de l'annonce)."""

        user_prompt = f"""Ecris une annonce Facebook pour ce vehicule:

VEHICULE: {ctx.get('title', '')}
PRIX: {ctx.get('price_formatted', '')}
KILOMETRAGE: {ctx.get('km_formatted', '')} ({ctx.get('km_description', '')})
POSITIONNEMENT PRIX: {ctx.get('price_description', '')}
TYPE: {vtype}

CONNAISSANCES SPECIFIQUES:
{chr(10).join(specs_info) if specs_info else "Aucune info specifique disponible."}

{f"SPECS DECODEES DU VIN (NHTSA):{chr(10)}{vin_specs_text}" if vin_specs_text else ""}

OPTIONS/EQUIPEMENTS CONFIRMES:
{chr(10).join(f"- {o}" for o in human_options) if human_options else "Aucune option confirmee."}

ANGLES DE VENTE SUGGERES: {', '.join(ctx.get('brand_angles', ['qualite', 'valeur', 'confiance'])[:3])}

INSTRUCTIONS:
1. Ecris une INTRO de 3-4 phrases maximum. Naturelle, directe, passionnee.
   - Mentionne ce qui rend CE vehicule special (pas une intro generique)
   - Si tu connais le moteur/HP, mentionne-le naturellement
   - Adapte le ton au type: {tone}

2. Puis le CORPS structure:
   - Titre avec le nom complet et l'annee
   - Prix
   - Kilometrage
   - Stock: {ctx.get('stock', '')}
   - 5-8 equipements/caracteristiques en points
   - Si c'est un Stellantis avec sticker: mention "Window Sticker verifie"

3. FERME avec: le nom Daniel Giroux et le numero 418-222-3939.
   Ne mets PAS "Kennebec Dodge" dans le footer (il est ajoute automatiquement).

FORMAT DE SORTIE: Texte pret a copier-coller sur Facebook. Utilise des emojis avec parcimonie dans le corps (pas dans l'intro).

STYLE D'INTRO: {style}"""

        api_key = os.environ.get("EMERGENT_LLM_KEY", "")
        if not api_key:
            return {"ok": False, "error": "EMERGENT_LLM_KEY non configure", "intelligence": ctx}

        chat = LlmChat(
            api_key=api_key,
            session_id=f"kenbot-gen-{stock}-{uuid.uuid4().hex[:8]}",
            system_message=system_msg,
        )
        chat.with_model("openai", "gpt-4o")

        response = await chat.send_message(UserMessage(text=user_prompt))
        text = response.strip().strip('"').strip("'")

        # Post-process: remove cliches
        cliches = ["pret a dominer", "faire tourner les tetes", "sillonner la beauce",
                    "conquerir les chemins", "dominer les routes", "parcourir les routes de beauce",
                    "arpenter les routes", "routes de la beauce", "routes de beauce",
                    "chemins de la beauce", "paysages de la beauce"]
        for c in cliches:
            if c in text.lower():
                lines = text.split("\n")
                text = "\n".join(l for l in lines if c not in l.lower())

        # Post-process: remove vulgar/sexual words
        vulgar = ["couilles", "balls", "badass", "bitch", "cul ", "merde", "crisse", "tabarnac",
                  "calisse", "ostie", "fuck", "shit", "damn", "ass ", "sexy"]
        for v in vulgar:
            if v in text.lower():
                lines = text.split("\n")
                text = "\n".join(l for l in lines if v not in l.lower())

        return {
            "ok": True,
            "text": text.strip(),
            "intelligence": ctx,
            "vin_specs": vin_specs,
            "chars": len(text),
            "style": style,
            "model": "gpt-4o",
        }
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}

@api_router.post("/humanize-sticker/{stock}")
async def humanize_sticker_text(stock: str):
    """Humanise une annonce Stellantis existante (sticker_to_ad) avec l'IA."""
    if not sb:
        return {"ok": False, "error": "Supabase non connecte"}
    try:
        from vehicle_intelligence import build_vehicle_context
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        # Get vehicle info
        inv_result = sb.table("inventory").select("*").eq("stock", stock.upper()).limit(1).execute()
        vehicle = inv_result.data[0] if inv_result.data else {}
        ctx = build_vehicle_context(vehicle) if vehicle else {}

        # Get existing post with sticker text
        post_result = sb.table("posts").select("base_text,post_id").eq("stock", stock.upper()).limit(1).execute()
        if not post_result.data or not post_result.data[0].get("base_text"):
            return {"ok": False, "error": f"Aucun post avec sticker trouve pour {stock}"}

        base_text = post_result.data[0]["base_text"]
        has_sticker = "ACCESSOIRES" in base_text or "Window Sticker" in base_text
        if not has_sticker:
            return {"ok": False, "error": "Ce post ne contient pas de donnees Window Sticker", "is_sticker": False}

        title = vehicle.get("title", "") if vehicle else ""
        price = vehicle.get("price_int", 0) if vehicle else 0
        km = vehicle.get("km_int", 0) if vehicle else 0
        price_fmt = f"{price:,}".replace(",", " ") + " $" if price else ""
        km_fmt = f"{km:,}".replace(",", " ") + " km" if km else ""

        brand_identity = ctx.get("brand_identity", "") if ctx else ""
        model_known_for = ctx.get("model_known_for", "") if ctx else ""
        vtype = ctx.get("vehicle_type", "general") if ctx else "general"

        system_msg = """Tu es Daniel Giroux, vendeur passionne chez Kennebec Dodge Chrysler a Saint-Georges.
Tu recois une annonce Facebook generee a partir du Window Sticker d'un vehicule Stellantis.

TON TRAVAIL — Humaniser cette annonce en respectant ces regles STRICTES:

1. INTRO (3-4 phrases au debut):
   Ajoute une intro percutante, quebecoise, passionnee, specifique au vehicule.
   Pas de cliches, pas de vulgarite. Professionnel mais passionne.
   ABSOLUMENT AUCUN mot vulgaire, grossier ou a caractere sexuel.
   JAMAIS de "sillonner", "dominer", "Beauce", "routes de la Beauce" dans l'intro.

2. TITRE:
   Remplace SEULEMENT la premiere ligne (titre entre emojis) par un titre plus vendeur et humain.

3. OPTIONS — Structure STRICTE:
   ✅ = OPTIONS PRINCIPALES en MAJUSCULES humanisees (noms techniques traduits en francais lisible)
   ▫️ = sous-options en minuscules, plus discrets, en retrait
   
   IMPORTANT: 
   - NE SUPPRIME AUCUNE LIGNE. Chaque ✅ et ▫️ doit rester.
   - Les ✅ restent en MAJUSCULES. Noms humanises.
   - Les ▫️ sont en minuscules. Noms humanises.
   
   Exemples:
   - "COUCHE NACREE CRISTAL NOIR ETINCEL" → "PEINTURE NOIR CRISTAL NACREE"
   - "BANQ AVANT 40–20–40 TISSU CAT SUP" → "BANQUETTE AVANT 40/20/40 TISSU PREMIUM"
   - "SIEGE CONDUCT 10 REGL ELECT A/LOMB" → "siege conducteur 10 reglages electriques avec lombaire"
   - "SYST ELECTRO ANTIDERAPAGE" → "SYSTEME ANTIPATINAGE ELECTRONIQUE"
   - "TAPIS PROTECT AVANT/ARR T/S MOPARMD" → "TAPIS PROTECTEURS MOPAR AVANT/ARRIERE"
   - "ESSIEU ARR A/DIFFERENTIEL AUTOBLOQ" → "ESSIEU ARRIERE DIFFERENTIEL AUTOBLOQUANT"
   - "PLAQUE PROTECTION BOITE TRANSFERT" → "plaque de protection boite de transfert"

4. TOUT apres le lien sticker (footer echanges, Daniel Giroux, hashtags) = COPIE EXACTE, ne change RIEN.

NE RAJOUTE RIEN a la fin. Pas de commentaire, pas de "INFOS"."""

        prompt = f"""Humanise cette annonce:

{base_text}

INFOS: {title} | {price_fmt} | {km_fmt} | {vtype}
{f'Marque: {brand_identity}' if brand_identity else ''}
{f'Modele: {model_known_for}' if model_known_for else ''}"""

        api_key = os.environ.get("EMERGENT_LLM_KEY", "")
        if not api_key:
            return {"ok": False, "error": "EMERGENT_LLM_KEY non configure"}

        chat = LlmChat(
            api_key=api_key,
            session_id=f"kenbot-sticker-{stock}-{uuid.uuid4().hex[:8]}",
            system_message=system_msg,
        )
        chat.with_model("openai", "gpt-4o")
        response = await chat.send_message(UserMessage(text=prompt))

        # Couper tout apres les hashtags
        lines = response.split("\n")
        output = []
        for line in lines:
            output.append(line)
            if line.strip().startswith("#") and "DanielGiroux" in line:
                break
        text = "\n".join(output).strip()

        # Filtre vulgarite
        vulgar = ["couilles", "balls", "badass", "bitch", "cul ", "merde", "crisse",
                  "tabarnac", "calisse", "ostie", "fuck", "shit", "damn", "ass ", "sexy"]
        for v in vulgar:
            if v in text.lower():
                text_lines = text.split("\n")
                text = "\n".join(l for l in text_lines if v not in l.lower())

        return {
            "ok": True,
            "text": text,
            "original": base_text,
            "intelligence": ctx,
            "chars": len(text),
            "is_sticker": True,
            "model": "gpt-4o",
        }
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}

@api_router.get("/test-batch-generate")
async def test_batch_generate(limit: int = 3):
    """Teste la generation sur plusieurs vehicules actifs."""
    if not sb:
        return {"ok": False, "error": "Supabase non connecte"}
    inv = sb.table("inventory").select("stock,title,price_int,km_int").eq("status", "ACTIVE").order("updated_at", desc=True).limit(limit).execute()
    if not inv.data:
        return {"ok": False, "error": "Aucun vehicule actif"}
    results = []
    for v in inv.data:
        stock = v.get("stock", "")
        try:
            from vehicle_intelligence import build_vehicle_context
            ctx = build_vehicle_context(v)
            results.append({
                "stock": stock,
                "title": v.get("title", ""),
                "parsing": {
                    "brand": ctx["brand"],
                    "model": ctx["model"],
                    "trim": ctx["trim"],
                    "type": ctx["vehicle_type"],
                    "hp": ctx["hp"],
                    "engine": ctx["engine"],
                    "vibe": ctx["trim_vibe"],
                    "km_desc": ctx["km_description"],
                    "price_desc": ctx["price_description"],
                },
            })
        except Exception as e:
            results.append({"stock": stock, "error": str(e)})
    return {"ok": True, "count": len(results), "vehicles": results}

@api_router.get("/architecture")
async def get_architecture():
    return ARCHITECTURE

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    return status_checks

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup():
    if sb:
        logger.info(f"Supabase connected to {SUPABASE_URL}")
    else:
        logger.warning("Supabase NOT connected - dashboard will show no data")
