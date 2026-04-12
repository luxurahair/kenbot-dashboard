from fastapi import FastAPI, APIRouter
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import logging
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
import uuid
from datetime import datetime, timezone
from supabase import create_client as sb_create_client

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env', override=False)

# Supabase (for kenbot real data)
SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')
sb = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        sb = sb_create_client(SUPABASE_URL, SUPABASE_KEY)
        print(f"[STARTUP] Supabase connected to {SUPABASE_URL[:40]}...")
    except Exception as e:
        print(f"[STARTUP] Supabase connection failed: {e}")
else:
    print("[STARTUP] Supabase credentials not set - running without data")

app = FastAPI(title="Kenbot Dashboard API")

# CORS - must be before router
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")

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
        "version": "4.0.0",
        "date": "2026-04-12",
        "type": "feature",
        "title": "Refonte detection par STOCK + UNSOLD + SEO + Cleanup",
        "changes": [
            {"severity": "critical", "description": "Toutes les comparaisons (SOLD, PRICE_CHANGED, PHOTOS_ADDED) utilisent maintenant le STOCK comme cle primaire au lieu du slug", "file": "runner_cron_prod.py"},
            {"severity": "critical", "description": "Nouveau event UNSOLD: restaure automatiquement les posts marques VENDU par erreur si le stock est encore sur Kennebec", "file": "runner_cron_prod.py"},
            {"severity": "critical", "description": "Detection NO_PHOTO par comparaison FB vs Kennebec (fb_photos <= 1 ET kennebec > 1)", "file": "runner_cron_prod.py"},
            {"severity": "critical", "description": "FIX publish_with_photos inexistant — remplace par publish_photos_unpublished + create_post_with_attached_media", "file": "runner_cron_prod.py"},
            {"severity": "critical", "description": "FIX double footer — ad_builder.py ne rajoute plus les echanges, footer_utils.py est l'unique source", "file": "ad_builder.py"},
            {"severity": "medium", "description": "Cleanup automatique: a chaque cron, corrige les posts FB existants avec double footer (max 10/run)", "file": "runner_cron_prod.py"},
            {"severity": "medium", "description": "Hashtags SEO dynamiques par vehicule (#DodgeHornet2024 #Beauce #SaintGeorges #Pickup etc.)", "file": "runner_cron_prod.py"},
            {"severity": "medium", "description": "Intro PRICE_CHANGED amelioree: affiche le montant du rabais (ex: 2 000 $ DE RABAIS)", "file": "runner_cron_prod.py"},
            {"severity": "medium", "description": "Prix fallback depuis inventory DB si le scrape ne trouve pas le prix", "file": "runner_cron_prod.py"},
            {"severity": "low", "description": "Protection anti-boucle SOLD: cooldown 3 jours, verification par stock", "file": "runner_cron_prod.py"},
        ]
    },
    {
        "version": "3.5.0",
        "date": "2026-04-12",
        "type": "feature",
        "title": "Pre-cache PDFs Stellantis 2018+ + VIN strict 17 chars",
        "changes": [
            {"severity": "critical", "description": "Pre-cache obligatoire: au debut du cron, telecharge/verifie les PDFs sticker pour TOUS les Stellantis 2018+", "file": "runner_cron_prod.py"},
            {"severity": "medium", "description": "ensure_sticker_cached retourne pdf_bytes directement (plus de double telechargement)", "file": "runner_cron_prod.py"},
            {"severity": "medium", "description": "upsert_sticker_pdf isole dans try/except (FK ne casse plus le return)", "file": "runner_cron_prod.py"},
            {"severity": "medium", "description": "upsert_scrape_run() execute AVANT le pre-cache (corrige FK sticker_pdfs_run_id_fkey)", "file": "runner_cron_prod.py"},
            {"severity": "low", "description": "VIN decode strictement 17 caracteres (plus de faux positifs)", "file": "vin_decoder.py"},
        ]
    },
    {
        "version": "3.2.0",
        "date": "2026-04-12",
        "type": "bugfix",
        "title": "FIX upsert_post duplicate key + suppression photos commentaires",
        "changes": [
            {"severity": "critical", "description": "upsert_post: on_conflict passe de 'stock' a 'slug' (PK) avec fallback update 3 niveaux", "file": "supabase_db.py"},
            {"severity": "critical", "description": "publish_photos_as_comment_batch supprime (causait 403 FB). Max 10 photos par post, pas de commentaires.", "file": "runner_cron_prod.py"},
            {"severity": "medium", "description": "Double appel _build_ad_text dans PHOTOS_ADDED corrige: reutilise msg deja genere", "file": "runner_cron_prod.py"},
        ]
    },
    {
        "version": "3.0.0",
        "date": "2026-04-11",
        "type": "feature",
        "title": "AI v3.0 — Generation intelligente par vehicule",
        "changes": [
            {"severity": "critical", "description": "Nouveau moteur de texte llm_v3.py: prompts adaptes par type de vehicule (muscle_car, off_road, suv_premium, pickup, etc.)", "file": "llm_v3.py"},
            {"severity": "critical", "description": "Module vehicle_intelligence.py: parsing titre, detection marque/modele/trim, specs moteur (HP, engine), base 27 marques, 43 modeles, 194 trims", "file": "vehicle_intelligence.py"},
            {"severity": "critical", "description": "Decodage VIN via NHTSA API (vin_decoder.py): moteur, HP, transmission, 4WD, places, securite", "file": "vin_decoder.py"},
            {"severity": "medium", "description": "Humanisation sticker Stellantis: intro AI + options ✅ MAJUSCULES / ▫️ minuscules preservees", "file": "runner_cron_prod.py"},
            {"severity": "medium", "description": "Detection et marquage SOLD sur Facebook (🚨 VENDU 🚨)", "file": "runner_cron_prod.py"},
        ]
    },
]

# ─── Architecture ───
ARCHITECTURE = {
    "components": [
        {"id": "website", "name": "Site Kennebec", "type": "external", "description": "kennebecdodge.ca — Source inventaire (3 pages scrappees)"},
        {"id": "scraper", "name": "kennebec_scrape.py", "type": "module", "description": "Scraping HTML + extraction VIN + photos + prix"},
        {"id": "runner", "name": "runner_cron_prod.py", "type": "core", "description": "Orchestrateur cron — Detection par STOCK: NEW / SOLD / UNSOLD / PRICE_CHANGED / PHOTOS_ADDED / CLEANUP"},
        {"id": "supabase", "name": "Supabase PostgreSQL", "type": "storage", "description": "Tables: inventory, posts, events, scrape_runs, sticker_pdfs + Storage (PDFs, photos)"},
        {"id": "vin_decoder", "name": "vin_decoder.py", "type": "module", "description": "Decodage VIN 17 chars via NHTSA API — moteur, HP, transmission, 4WD, places"},
        {"id": "vehicle_intel", "name": "vehicle_intelligence.py", "type": "module", "description": "Base de connaissance: 27 marques, 43 modeles, 194 trims avec specs, vibe, ton marketing"},
        {"id": "sticker", "name": "sticker_to_ad.py + ad_builder.py", "type": "module", "description": "Extraction PDF Window Sticker (Stellantis 2018+) → options ✅/▫️ structurees"},
        {"id": "llm_v3", "name": "llm_v3.py", "type": "module", "description": "Generation IA GPT-4o — prompts adaptes par type vehicule, 5 styles d'intro, anti-cliches"},
        {"id": "footer", "name": "footer_utils.py", "type": "module", "description": "Footer unique Daniel Giroux — echanges, telephone, hashtags SEO dynamiques"},
        {"id": "facebook", "name": "fb_api.py", "type": "external", "description": "Facebook Graph API — publish, update, delete, fetch feed (max 10 photos/post)"},
        {"id": "meta_feed", "name": "meta_compare_supabase.py", "type": "output", "description": "Rapport CSV: comparaison Meta FB vs site Kennebec"},
        {"id": "dashboard", "name": "kenbot-dashboard", "type": "webapp", "description": "Dashboard React + FastAPI — Cockpit, Preview, Inventaire (Vercel + Render)"},
    ],
    "flows": [
        {"from": "website", "to": "scraper", "label": "HTML 3 pages"},
        {"from": "scraper", "to": "runner", "label": "47 vehicules + VIN + photos"},
        {"from": "runner", "to": "supabase", "label": "Upsert inventory, posts, events"},
        {"from": "runner", "to": "vin_decoder", "label": "VIN → NHTSA specs"},
        {"from": "runner", "to": "vehicle_intel", "label": "Titre → marque/modele/trim"},
        {"from": "runner", "to": "sticker", "label": "PDF Stellantis 2018+ → options"},
        {"from": "runner", "to": "llm_v3", "label": "Specs + options → texte IA"},
        {"from": "runner", "to": "footer", "label": "Texte → footer + hashtags SEO"},
        {"from": "runner", "to": "facebook", "label": "Publish / Update / Delete"},
        {"from": "runner", "to": "meta_feed", "label": "CSV meta_vs_site.csv"},
        {"from": "supabase", "to": "dashboard", "label": "Live data"},
    ],
    "states": ["NEW", "SOLD", "UNSOLD", "PRICE_CHANGED", "PHOTOS_ADDED", "CLEANUP"],
    "pipeline": {
        "order": "UNSOLD → PHOTOS_ADDED → PRICE_CHANGED → NEW → SOLD → CLEANUP",
        "comparison_key": "STOCK (pas slug)",
        "sold_protection": "3 jours cooldown + verification stock Kennebec",
        "sticker_precache": "38 Stellantis 2018+ au debut de chaque run",
    }
}

# ─── Routes ───

@api_router.get("/")
async def root():
    return {"message": "Kenbot Dashboard API", "version": "4.0.0", "supabase_connected": sb is not None}

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


@api_router.get("/vehicles/compare")
async def get_vehicles_compare():
    """
    Comparaison Kennebec (inventaire) vs Facebook (posts).
    Retourne chaque véhicule avec son statut sur les deux plateformes.
    """
    if not sb:
        return {"vehicles": [], "stats": {}}

    try:
        inv_result = sb.table("inventory").select("slug,stock,title,vin,price_int,km_int,status,updated_at").order("updated_at", desc=True).limit(500).execute()
        posts_result = sb.table("posts").select("slug,stock,post_id,status,base_text,no_photo,photo_count,published_at,last_updated_at,sold_at").limit(500).execute()

        inv_data = inv_result.data or []
        posts_data = posts_result.data or []

        # Index posts par stock
        posts_by_stock = {}
        for p in posts_data:
            st = (p.get("stock") or "").strip().upper()
            if st:
                posts_by_stock[st] = p

        vehicles = []
        for inv in inv_data:
            stock = (inv.get("stock") or "").strip().upper()
            if not stock:
                continue

            post = posts_by_stock.get(stock)
            inv_status = (inv.get("status") or "").upper()

            # Déterminer le statut FB
            fb_status = "AUCUN POST"
            fb_post_id = ""
            fb_photos = 0
            fb_published = ""
            fb_updated = ""
            fb_no_photo = False

            if post:
                fb_status = (post.get("status") or "INCONNU").upper()
                fb_post_id = post.get("post_id") or ""
                fb_photos = post.get("photo_count") or 0
                fb_published = post.get("published_at") or ""
                fb_updated = post.get("last_updated_at") or ""
                fb_no_photo = post.get("no_photo") is True

                # Détecter no_photo depuis le texte
                if not fb_no_photo and fb_photos <= 1:
                    bt = (post.get("base_text") or "").lower()
                    fb_no_photo = any(h in bt for h in ["photos suivront", "sans photo", "photo non disponible"])

            # Problème détecté?
            problem = ""
            if inv_status == "ACTIVE" and fb_status == "SOLD":
                problem = "FAUX VENDU"
            elif inv_status == "ACTIVE" and fb_status == "AUCUN POST":
                problem = "PAS SUR FB"
            elif inv_status == "ACTIVE" and fb_no_photo:
                problem = "SANS PHOTO"
            elif inv_status == "SOLD" and fb_status == "ACTIVE":
                problem = "FB PAS MAJ"

            vehicles.append({
                "stock": stock,
                "title": inv.get("title") or "",
                "price": inv.get("price_int"),
                "km": inv.get("km_int"),
                "vin": inv.get("vin") or "",
                "kennebec_status": inv_status,
                "fb_status": fb_status,
                "fb_post_id": fb_post_id,
                "fb_photos": fb_photos,
                "fb_no_photo": fb_no_photo,
                "fb_published": fb_published,
                "fb_updated": fb_updated,
                "problem": problem,
                "updated_at": inv.get("updated_at") or "",
            })

        # Stats
        total = len(vehicles)
        on_kennebec = sum(1 for v in vehicles if v["kennebec_status"] == "ACTIVE")
        on_fb_active = sum(1 for v in vehicles if v["fb_status"] == "ACTIVE")
        on_fb_sold = sum(1 for v in vehicles if v["fb_status"] == "SOLD")
        no_fb = sum(1 for v in vehicles if v["fb_status"] == "AUCUN POST" and v["kennebec_status"] == "ACTIVE")
        faux_vendu = sum(1 for v in vehicles if v["problem"] == "FAUX VENDU")
        sans_photo = sum(1 for v in vehicles if v["problem"] == "SANS PHOTO")
        problems = sum(1 for v in vehicles if v["problem"])

        return {
            "vehicles": vehicles,
            "stats": {
                "total": total,
                "kennebec_active": on_kennebec,
                "fb_active": on_fb_active,
                "fb_sold": on_fb_sold,
                "no_fb_post": no_fb,
                "faux_vendu": faux_vendu,
                "sans_photo": sans_photo,
                "problems": problems,
            }
        }
    except Exception as e:
        logging.error(f"Compare error: {e}")
        return {"vehicles": [], "stats": {}, "error": str(e)}

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
        from openai import AsyncOpenAI

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
            "muscle_sedan": "puissance et style 4 portes",
            "pickup": "robustesse et capacite",
            "pickup_hd": "robustesse et capacite",
            "off_road": "aventure et liberte",
            "suv_premium": "confort et raffinement",
            "citadine": "style et economie",
            "suv_compact": "style et economie",
            "exotique": "exclusivite et reve",
            "collector": "exclusivite et reve",
            "berline": "confort et fiabilite au quotidien",
            "minivan": "espace familial et polyvalence",
            "commercial": "efficacite et espace de travail",
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

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return {"ok": False, "error": "OPENAI_API_KEY non configure", "intelligence": ctx}

        chat = AsyncOpenAI(api_key=api_key)
        _resp = await chat.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": user_prompt}],
            temperature=0.85, max_tokens=1500,
        )
        response = _resp.choices[0].message.content.strip()
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
        from openai import AsyncOpenAI

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

        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return {"ok": False, "error": "OPENAI_API_KEY non configure"}

        chat = AsyncOpenAI(api_key=api_key)
        _resp = await chat.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
            temperature=0.8, max_tokens=2000,
        )
        response = _resp.choices[0].message.content.strip()

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

# ═══════════════════════════════════════════════════
# COCKPIT — Simulation Dry Run + VIN Decode batch
# ═══════════════════════════════════════════════════

@api_router.get("/cockpit/decode-vin/{stock}")
async def cockpit_decode_vin(stock: str):
    """Decode le VIN d'un vehicule et retourne les specs NHTSA."""
    if not sb:
        return {"ok": False, "error": "Supabase non connecte"}
    try:
        from vin_decoder import decode_vin, format_specs_for_prompt, format_engine_line
        result = sb.table("inventory").select("stock,title,vin,price_int,km_int").eq("stock", stock.upper()).limit(1).execute()
        if not result.data:
            return {"ok": False, "error": f"Vehicule {stock} non trouve"}
        v = result.data[0]
        vin_val = (v.get("vin") or "").strip()
        if len(vin_val) < 11:
            return {"ok": False, "error": "VIN trop court ou absent", "vehicle": v}
        specs = decode_vin(vin_val)
        if not specs:
            return {"ok": False, "error": "NHTSA n'a pas retourne de donnees", "vehicle": v}
        return {
            "ok": True,
            "vehicle": v,
            "specs": specs,
            "engine_line": format_engine_line(specs),
            "specs_text": format_specs_for_prompt(specs),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

@api_router.post("/cockpit/simulate")
async def cockpit_simulate(max_targets: int = 4, force_stock: Optional[str] = None):
    """Simule un dry run du cron: detecte les cibles et genere les textes SANS publier."""
    if not sb:
        return {"ok": False, "error": "Supabase non connecte"}

    from vehicle_intelligence import build_vehicle_context
    from openai import AsyncOpenAI
    import time as _time

    start = _time.time()
    results = []

    try:
        # Get active inventory
        inv_data = sb.table("inventory").select("*").eq("status", "ACTIVE").order("updated_at", desc=True).limit(200).execute()
        inventory = {v.get("stock", "").upper(): v for v in (inv_data.data or []) if v.get("stock")}

        # Get active posts
        posts_data = sb.table("posts").select("stock,post_id,base_text,published_at,no_photo,status").eq("status", "ACTIVE").limit(500).execute()
        posts_map = {(p.get("stock") or "").upper(): p for p in (posts_data.data or []) if p.get("stock")}

        # If force_stock, just simulate for that one
        if force_stock:
            stock = force_stock.strip().upper()
            if stock in inventory:
                v = inventory[stock]
                has_post = stock in posts_map
                event = "NEW" if not has_post else "UPDATE"
                res = await _simulate_one_vehicle(v, event, posts_map.get(stock))
                results.append(res)
            else:
                results.append({"stock": stock, "error": "Stock non trouve dans l'inventaire actif"})
        else:
            # Detect targets: vehicles without posts (NEW) or candidates for update
            new_targets = []
            for stock, v in inventory.items():
                if stock not in posts_map:
                    new_targets.append((stock, v, "NEW"))

            # Take top targets
            targets = new_targets[:max_targets]

            # If not enough new, pick some existing for preview
            if len(targets) < max_targets:
                existing = [(s, v, "PREVIEW") for s, v in list(inventory.items())[:max_targets * 2] if s in posts_map]
                targets.extend(existing[:max_targets - len(targets)])

            for stock, v, event in targets[:max_targets]:
                res = await _simulate_one_vehicle(v, event, posts_map.get(stock))
                results.append(res)

    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "traceback": traceback.format_exc()}

    elapsed = round(_time.time() - start, 1)
    return {
        "ok": True,
        "count": len(results),
        "elapsed_seconds": elapsed,
        "inventory_active": len(inventory) if 'inventory' in dir() else 0,
        "posts_active": len(posts_map) if 'posts_map' in dir() else 0,
        "results": results,
    }


async def _simulate_one_vehicle(v: Dict[str, Any], event: str, existing_post: Optional[Dict] = None) -> Dict[str, Any]:
    """Simule la generation de texte pour un vehicule."""
    from vehicle_intelligence import build_vehicle_context
    from openai import AsyncOpenAI
    import time as _time

    stock = (v.get("stock") or "").strip().upper()
    vin_val = (v.get("vin") or "").strip().upper()
    title = v.get("title", "")
    start = _time.time()

    result = {
        "stock": stock,
        "title": title,
        "vin": vin_val,
        "price": v.get("price_int"),
        "km": v.get("km_int"),
        "event": event,
        "has_existing_post": existing_post is not None,
        "generation_method": None,
        "text": None,
        "chars": 0,
        "vin_decoded": False,
        "vin_specs": None,
        "intelligence": None,
        "is_sticker": False,
        "error": None,
    }

    # 1. Vehicle Intelligence
    try:
        ctx = build_vehicle_context(v)
        result["intelligence"] = {
            "brand": ctx.get("brand"),
            "model": ctx.get("model"),
            "trim": ctx.get("trim"),
            "type": ctx.get("vehicle_type"),
            "hp": ctx.get("hp"),
            "engine": ctx.get("engine"),
            "vibe": ctx.get("trim_vibe"),
        }
    except Exception:
        ctx = {}

    # 2. VIN Decode
    vin_specs_text = ""
    if len(vin_val) >= 11:
        try:
            from vin_decoder import decode_vin, format_specs_for_prompt, format_engine_line
            specs = decode_vin(vin_val)
            if specs:
                result["vin_decoded"] = True
                result["vin_specs"] = {
                    "engine": format_engine_line(specs),
                    "drive": specs.get("drive_type", ""),
                    "transmission": specs.get("transmission", ""),
                    "fuel": specs.get("fuel_primary", ""),
                    "electrification": specs.get("electrification", ""),
                    "seats": specs.get("seats", ""),
                    "country": specs.get("plant_country", ""),
                }
                vin_specs_text = format_specs_for_prompt(specs)
                if not ctx.get("hp") and specs.get("engine_hp"):
                    result["intelligence"]["hp"] = specs["engine_hp"]
                    result["intelligence"]["engine"] = format_engine_line(specs).replace(f" — {specs['engine_hp']} HP", "")
        except Exception:
            pass

    # 3. Check if sticker post exists
    has_sticker = False
    sticker_text = ""
    if existing_post and existing_post.get("base_text"):
        bt = existing_post["base_text"]
        has_sticker = "ACCESSOIRES" in bt or "Window Sticker" in bt
        if has_sticker:
            sticker_text = bt
            result["is_sticker"] = True

    # 4. Generate text
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        result["error"] = "OPENAI_API_KEY manquant"
        return result

    try:
        if has_sticker and sticker_text:
            # Stellantis sticker humanization
            result["generation_method"] = "STICKER+AI"
            text = await _cockpit_humanize_sticker(api_key, sticker_text, v, ctx, vin_specs_text)
        else:
            # Standard generation with VIN
            result["generation_method"] = "LLM_V3+VIN" if vin_specs_text else "LLM_V3"
            text = await _cockpit_generate_text(api_key, v, ctx, vin_specs_text)

        if text:
            result["text"] = text
            result["chars"] = len(text)
        else:
            result["error"] = "Generation retourne vide"
    except Exception as e:
        result["error"] = str(e)

    result["elapsed"] = round(_time.time() - start, 1)
    return result


async def _cockpit_generate_text(api_key: str, v: Dict, ctx: Dict, vin_specs_text: str) -> str:
    """Genere un texte via OpenAI (meme prompts que generate-text endpoint)."""
    from openai import AsyncOpenAI
    from vehicle_intelligence import humanize_options
    import random

    vtype = ctx.get("vehicle_type", "general")
    tone_map = {
        "muscle_car": "adrenaline et son du moteur", "pickup": "robustesse et capacite",
        "pickup_hd": "robustesse et capacite", "off_road": "aventure et liberte",
        "suv_premium": "confort et raffinement", "citadine": "style et economie",
        "suv_compact": "style et economie", "exotique": "exclusivite et reve",
    }
    tone = tone_map.get(vtype, "polyvalence et fiabilite")
    style = random.choice(["direct", "storytelling", "question", "expertise", "opportunite"])

    specs_info = []
    if not vin_specs_text:
        if ctx.get("hp"):
            specs_info.append(f"Moteur: {ctx['engine']} — {ctx['hp']} chevaux")
    if ctx.get("trim_vibe"):
        specs_info.append(f"Ce trim: {ctx['trim_vibe']}")
    if ctx.get("model_known_for"):
        specs_info.append(f"Ce modele: {ctx['model_known_for']}")

    system_msg = "Tu es Daniel Giroux, vendeur passionne chez Kennebec Dodge Chrysler a Saint-Georges.\nREGLES: Francais quebecois naturel. Passionne mais professionnel. AUCUN mot vulgaire. JAMAIS mentionner la Beauce. Max 3-4 phrases d'intro. Pas de cliches."

    price = v.get("price_int", 0)
    km = v.get("km_int", 0)
    prompt = f"""Ecris une annonce Facebook:
VEHICULE: {v.get('title','')}
PRIX: {f'{price:,}'.replace(',', ' ')} $ | KM: {f'{km:,}'.replace(',', ' ')} km
STOCK: {v.get('stock','')}
TYPE: {vtype} | TON: {tone} | STYLE: {style}
{chr(10).join(specs_info) if specs_info else ''}
{f'SPECS VIN:{chr(10)}{vin_specs_text}' if vin_specs_text else ''}
Intro 3-4 phrases + corps structure + Daniel Giroux 418-222-3939"""

    client = AsyncOpenAI(api_key=api_key)
    _resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
        temperature=0.85, max_tokens=1500,
    )
    return _resp.choices[0].message.content.strip()


async def _cockpit_humanize_sticker(api_key: str, sticker_text: str, v: Dict, ctx: Dict, vin_specs_text: str) -> str:
    """Humanise un texte sticker via OpenAI."""
    from openai import AsyncOpenAI

    system_msg = (
        "Tu es Daniel Giroux, vendeur passionne chez Kennebec Dodge Chrysler.\n"
        "Humanise cette annonce sticker:\n"
        "1. INTRO 3-4 phrases passionnees. AUCUN mot vulgaire. JAMAIS 'Beauce'.\n"
        "2. TITRE vendeur au lieu du titre brut.\n"
        "3. OPTIONS: ✅ MAJUSCULES humanisees, ▫️ minuscules. NE SUPPRIME AUCUNE LIGNE.\n"
        "4. Apres le lien sticker: COPIE EXACTE du footer.\n"
        "NE RAJOUTE RIEN a la fin."
    )
    prompt = f"Humanise:\n\n{sticker_text}"
    if vin_specs_text:
        prompt += f"\n\nSPECS VIN:\n{vin_specs_text}"

    client = AsyncOpenAI(api_key=api_key)
    _resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": system_msg}, {"role": "user", "content": prompt}],
        temperature=0.8, max_tokens=2000,
    )
    resp = _resp.choices[0].message.content.strip()

    # Couper après les hashtags
    lines = resp.split("\n")
    output = []
    for line in lines:
        output.append(line)
        if line.strip().startswith("#") and "DanielGiroux" in line:
            break
    return "\n".join(output).strip()


@api_router.get("/cockpit/recent-logs")
async def cockpit_recent_logs(limit: int = 30):
    """Retourne les events recents groupes par run."""
    if not sb:
        return {"ok": False, "error": "Supabase non connecte"}
    events = sb_query("events", "*", order="created_at", limit=limit)
    runs = sb_query("scrape_runs", "*", order="created_at", limit=5)
    return {
        "ok": True,
        "events": events["data"],
        "runs": runs["data"],
    }

app.include_router(api_router)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup():
    if sb:
        logger.info(f"Supabase connected to {SUPABASE_URL}")
    else:
        logger.warning("Supabase NOT connected - dashboard will show no data")
