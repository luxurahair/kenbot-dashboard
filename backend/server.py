from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

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

class SystemConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key: str
    value: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CronRun(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    status: str
    inv_count: int = 0
    new_count: int = 0
    sold_count: int = 0
    price_changed: int = 0
    photos_added: int = 0
    posted: int = 0
    updated: int = 0
    skipped: int = 0
    errors: List[str] = []
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class InventoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    slug: str
    stock: str
    title: str
    price: Optional[str] = None
    price_int: Optional[int] = None
    mileage: Optional[str] = None
    km_int: Optional[int] = None
    vin: Optional[str] = None
    url: Optional[str] = None
    photo_count: int = 0
    status: str = "ACTIVE"
    last_seen: Optional[str] = None

class PostItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    slug: str
    stock: str
    post_id: Optional[str] = None
    status: str = "ACTIVE"
    no_photo: bool = False
    photo_count: int = 0
    published_at: Optional[str] = None
    last_updated_at: Optional[str] = None

# ─── Changelog data ───
CHANGELOG = [
    {
        "version": "2.1.0",
        "date": "2026-04-10",
        "type": "bugfix",
        "title": "FIX PHOTOS_ADDED - 3 bugs corrigés",
        "changes": [
            {
                "severity": "critical",
                "description": "Flag no_photo jamais mis à True lors de la création d'un post NEW avec fallback NO_PHOTO",
                "fix": "Nouvelle fonction _is_no_photo_fallback() + no_photo=True / photo_count=0 quand fallback utilisé",
                "file": "runner_cron_prod.py",
                "line": "~380"
            },
            {
                "severity": "critical", 
                "description": "Mauvais ordre d'arguments _build_ad_text(sb, v, 'NEW', run_id) dans PHOTOS_ADDED",
                "fix": "Corrigé en _build_ad_text(sb, run_id, slug, v, 'NEW')",
                "file": "runner_cron_prod.py",
                "line": "~310"
            },
            {
                "severity": "medium",
                "description": "Détection 'no photo' trop restrictive - mots-clés manquants dans base_text",
                "fix": "Ajout de mots-clés: 'sans photo', 'photo à venir', 'photos à venir', 'no_photo'",
                "file": "runner_cron_prod.py",
                "line": "~250"
            }
        ]
    },
    {
        "version": "2.0.0",
        "date": "2026-04-08",
        "type": "feature",
        "title": "AI v2.0 + Fix double footer + Clichés interdits",
        "changes": [
            {"severity": "medium", "description": "Textes plus longs (400 chars au lieu de 220)", "file": "llm.py"},
            {"severity": "medium", "description": "Liste de clichés INTERDITS (sillonner la Beauce, etc.)", "file": "llm.py"},
            {"severity": "low", "description": "Footer centralisé via footer_utils.py", "file": "footer_utils.py"},
        ]
    },
    {
        "version": "1.9.0",
        "date": "2026-04-08",
        "type": "feature",
        "title": "PHOTOS_ADDED v2: Supprimer + Recréer le post",
        "changes": [
            {"severity": "medium", "description": "Supprime l'ancien post NO_PHOTO et crée un nouveau avec vraies photos", "file": "runner_cron_prod.py"},
            {"severity": "low", "description": "Nouvelle fonction delete_post() dans fb_api.py", "file": "fb_api.py"},
        ]
    }
]

# ─── Architecture data ───
ARCHITECTURE = {
    "components": [
        {"id": "website", "name": "Site Kennebec", "type": "external", "description": "kennebecdodge.ca - Source inventaire"},
        {"id": "scraper", "name": "kennebec_scrape.py", "type": "module", "description": "Scraping HTML + parsing véhicules"},
        {"id": "runner", "name": "runner_cron_prod.py", "type": "core", "description": "Chef d'orchestre - Pipeline principal"},
        {"id": "supabase", "name": "Supabase", "type": "storage", "description": "Tables: inventory, posts, events + Storage"},
        {"id": "text_engine", "name": "Text Engine", "type": "service", "description": "Génération textes FB (externe + AI)"},
        {"id": "sticker", "name": "sticker_to_ad.py", "type": "module", "description": "Extraction PDF Window Sticker"},
        {"id": "llm", "name": "llm.py", "type": "module", "description": "AI OpenAI - Intros humanisées"},
        {"id": "facebook", "name": "fb_api.py", "type": "external", "description": "Facebook Graph API - Publication"},
        {"id": "meta_feed", "name": "Meta Feed", "type": "output", "description": "CSV feed pour Meta Ads"},
    ],
    "flows": [
        {"from": "website", "to": "scraper", "label": "HTML pages"},
        {"from": "scraper", "to": "runner", "label": "Véhicules normalisés"},
        {"from": "runner", "to": "supabase", "label": "State management"},
        {"from": "runner", "to": "text_engine", "label": "Génération texte"},
        {"from": "runner", "to": "sticker", "label": "PDF Stellantis"},
        {"from": "sticker", "to": "runner", "label": "Options extraites"},
        {"from": "llm", "to": "runner", "label": "Intro AI"},
        {"from": "runner", "to": "facebook", "label": "Publish/Update"},
        {"from": "runner", "to": "meta_feed", "label": "CSV export"},
    ],
    "states": ["NEW", "SOLD", "RESTORE", "PRICE_CHANGED", "PHOTOS_ADDED"]
}

# ─── System status (in-memory for demo, MongoDB for persistence) ───
SYSTEM_STATUS = {
    "supabase": {"connected": False, "url": ""},
    "facebook": {"connected": False, "page_id": ""},
    "text_engine": {"connected": False, "url": ""},
    "openai": {"connected": False},
    "last_run": None,
    "version": "2.1.0",
}

# ─── Seed demo data ───
async def seed_demo_data():
    # Seed demo cron runs
    count = await db.cron_runs.count_documents({})
    if count == 0:
        demo_runs = [
            {"id": str(uuid.uuid4()), "run_id": "20260410_140000", "status": "OK", "inv_count": 47, "new_count": 2, "sold_count": 1, "price_changed": 1, "photos_added": 0, "posted": 2, "updated": 1, "skipped": 0, "errors": [], "timestamp": "2026-04-10T14:00:00Z"},
            {"id": str(uuid.uuid4()), "run_id": "20260410_130000", "status": "OK", "inv_count": 46, "new_count": 0, "sold_count": 0, "price_changed": 0, "photos_added": 1, "posted": 0, "updated": 1, "skipped": 0, "errors": [], "timestamp": "2026-04-10T13:00:00Z"},
            {"id": str(uuid.uuid4()), "run_id": "20260410_120000", "status": "OK", "inv_count": 46, "new_count": 1, "sold_count": 2, "price_changed": 0, "photos_added": 0, "posted": 1, "updated": 0, "skipped": 1, "errors": [], "timestamp": "2026-04-10T12:00:00Z"},
            {"id": str(uuid.uuid4()), "run_id": "20260410_110000", "status": "ERROR", "inv_count": 0, "new_count": 0, "sold_count": 0, "price_changed": 0, "photos_added": 0, "posted": 0, "updated": 0, "skipped": 0, "errors": ["FB token expired"], "timestamp": "2026-04-10T11:00:00Z"},
            {"id": str(uuid.uuid4()), "run_id": "20260410_100000", "status": "OK", "inv_count": 48, "new_count": 3, "sold_count": 0, "price_changed": 2, "photos_added": 2, "posted": 3, "updated": 2, "skipped": 0, "errors": [], "timestamp": "2026-04-10T10:00:00Z"},
        ]
        await db.cron_runs.insert_many(demo_runs)

    inv_count = await db.inventory.count_documents({})
    if inv_count == 0:
        demo_inv = [
            {"slug": "ram-1500-big-horn-2022-06300", "stock": "06300", "title": "RAM 1500 Big Horn 2022", "price": "42 995 $", "price_int": 42995, "mileage": "35 000 km", "km_int": 35000, "vin": "1C6SRFFT5NN123456", "photo_count": 12, "status": "ACTIVE", "no_photo": False},
            {"slug": "jeep-wrangler-sahara-2023-06410", "stock": "06410", "title": "Jeep Wrangler Sahara 2023", "price": "52 995 $", "price_int": 52995, "mileage": "18 000 km", "km_int": 18000, "vin": "1C4HJXEN5PW654321", "photo_count": 15, "status": "ACTIVE", "no_photo": False},
            {"slug": "dodge-challenger-scat-pack-2021-06215", "stock": "06215", "title": "Dodge Challenger Scat Pack 2021", "price": "54 500 $", "price_int": 54500, "mileage": "11 500 km", "km_int": 11500, "vin": "2C3CDZFJ8MH987654", "photo_count": 0, "status": "ACTIVE", "no_photo": True},
            {"slug": "toyota-rav4-xle-2022-06380", "stock": "06380", "title": "Toyota RAV4 XLE 2022", "price": "36 995 $", "price_int": 36995, "mileage": "42 000 km", "km_int": 42000, "vin": "", "photo_count": 8, "status": "ACTIVE", "no_photo": False},
            {"slug": "dodge-hornet-rt-2024-06500", "stock": "06500", "title": "Dodge Hornet R/T 2024", "price": "44 995 $", "price_int": 44995, "mileage": "5 200 km", "km_int": 5200, "vin": "ZACNRFBV1R1234567", "photo_count": 0, "status": "ACTIVE", "no_photo": True},
            {"slug": "ram-2500-laramie-2020-06120", "stock": "06120", "title": "RAM 2500 Laramie 2020", "price": "59 995 $", "price_int": 59995, "mileage": "65 000 km", "km_int": 65000, "vin": "3C6UR5NL7LG112233", "photo_count": 10, "status": "SOLD"},
        ]
        await db.inventory.insert_many(demo_inv)

    posts_count = await db.posts.count_documents({})
    if posts_count == 0:
        demo_posts = [
            {"slug": "ram-1500-big-horn-2022-06300", "stock": "06300", "post_id": "pfbid02abc123", "status": "ACTIVE", "no_photo": False, "photo_count": 12, "published_at": "2026-04-09T10:00:00Z"},
            {"slug": "jeep-wrangler-sahara-2023-06410", "stock": "06410", "post_id": "pfbid02def456", "status": "ACTIVE", "no_photo": False, "photo_count": 15, "published_at": "2026-04-08T14:30:00Z"},
            {"slug": "dodge-challenger-scat-pack-2021-06215", "stock": "06215", "post_id": "pfbid02ghi789", "status": "ACTIVE", "no_photo": True, "photo_count": 0, "published_at": "2026-04-10T09:00:00Z"},
            {"slug": "toyota-rav4-xle-2022-06380", "stock": "06380", "post_id": "pfbid02jkl012", "status": "ACTIVE", "no_photo": False, "photo_count": 8, "published_at": "2026-04-07T16:00:00Z"},
            {"slug": "dodge-hornet-rt-2024-06500", "stock": "06500", "post_id": "pfbid02mno345", "status": "ACTIVE", "no_photo": True, "photo_count": 0, "published_at": "2026-04-10T11:00:00Z"},
            {"slug": "ram-2500-laramie-2020-06120", "stock": "06120", "post_id": "pfbid02pqr678", "status": "SOLD", "no_photo": False, "photo_count": 10, "published_at": "2026-04-05T08:00:00Z"},
        ]
        await db.posts.insert_many(demo_posts)

# ─── Routes ───

@api_router.get("/")
async def root():
    return {"message": "Kenbot Dashboard API", "version": SYSTEM_STATUS["version"]}

@api_router.get("/system/status")
async def get_system_status():
    total_inv = await db.inventory.count_documents({})
    active_inv = await db.inventory.count_documents({"status": "ACTIVE"})
    sold_inv = await db.inventory.count_documents({"status": "SOLD"})
    total_posts = await db.posts.count_documents({})
    active_posts = await db.posts.count_documents({"status": "ACTIVE"})
    no_photo_posts = await db.posts.count_documents({"no_photo": True})
    last_run = await db.cron_runs.find_one(sort=[("timestamp", -1)], projection={"_id": 0})
    
    return {
        "version": SYSTEM_STATUS["version"],
        "services": SYSTEM_STATUS,
        "stats": {
            "inventory": {"total": total_inv, "active": active_inv, "sold": sold_inv},
            "posts": {"total": total_posts, "active": active_posts, "no_photo": no_photo_posts, "with_photos": active_posts - no_photo_posts},
        },
        "last_run": last_run,
    }

@api_router.get("/cron/runs")
async def get_cron_runs(limit: int = 20):
    runs = await db.cron_runs.find({}, {"_id": 0}).sort("timestamp", -1).to_list(limit)
    return runs

@api_router.get("/inventory")
async def get_inventory(status: Optional[str] = None, limit: int = 100):
    query = {}
    if status:
        query["status"] = status.upper()
    items = await db.inventory.find(query, {"_id": 0}).to_list(limit)
    return items

@api_router.get("/inventory/stats")
async def get_inventory_stats():
    total = await db.inventory.count_documents({})
    active = await db.inventory.count_documents({"status": "ACTIVE"})
    sold = await db.inventory.count_documents({"status": "SOLD"})
    no_photo = await db.inventory.count_documents({"no_photo": True})
    with_photos = await db.inventory.count_documents({"no_photo": {"$ne": True}, "photo_count": {"$gt": 0}})
    return {"total": total, "active": active, "sold": sold, "no_photo": no_photo, "with_photos": with_photos}

@api_router.get("/posts")
async def get_posts(status: Optional[str] = None, no_photo: Optional[bool] = None, limit: int = 100):
    query = {}
    if status:
        query["status"] = status.upper()
    if no_photo is not None:
        query["no_photo"] = no_photo
    posts = await db.posts.find(query, {"_id": 0}).to_list(limit)
    return posts

@api_router.get("/posts/stats")
async def get_posts_stats():
    total = await db.posts.count_documents({})
    active = await db.posts.count_documents({"status": "ACTIVE"})
    sold = await db.posts.count_documents({"status": "SOLD"})
    no_photo = await db.posts.count_documents({"no_photo": True})
    with_photos = active - no_photo
    return {"total": total, "active": active, "sold": sold, "no_photo": no_photo, "with_photos": with_photos}

@api_router.get("/changelog")
async def get_changelog():
    return CHANGELOG

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
    await seed_demo_data()

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
