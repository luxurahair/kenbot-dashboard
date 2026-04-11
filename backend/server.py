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
async def generate_text_for_vehicle(stock: str):
    """Génère un texte Facebook intelligent pour un véhicule."""
    if not sb:
        return {"ok": False, "error": "Supabase non connecte"}
    try:
        from vehicle_intelligence import build_vehicle_context
        from llm_v3 import generate_smart_text

        result = sb.table("inventory").select("*").eq("stock", stock.upper()).limit(1).execute()
        if not result.data:
            return {"ok": False, "error": f"Vehicule {stock} non trouve"}
        vehicle = result.data[0]

        # Get sticker options if available
        options_text = ""
        post = sb.table("posts").select("base_text").eq("stock", stock.upper()).limit(1).execute()
        if post.data and post.data[0].get("base_text"):
            bt = post.data[0]["base_text"]
            # Extraire la section options du texte existant
            if "ACCESSOIRES" in bt or "QUIPEMENTS" in bt:
                options_text = bt

        text = generate_smart_text(vehicle, event="NEW", options_text=options_text)
        ctx = build_vehicle_context(vehicle)

        if text:
            return {"ok": True, "text": text, "intelligence": ctx, "chars": len(text)}
        else:
            return {"ok": False, "error": "Generation echouee - verifiez OPENAI_API_KEY", "intelligence": ctx}
    except Exception as e:
        return {"ok": False, "error": str(e)}

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
