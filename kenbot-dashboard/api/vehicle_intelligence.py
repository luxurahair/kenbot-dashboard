"""
vehicle_intelligence.py

Module de connaissance véhicule pour générer des textes Facebook
intelligents et humains. Parse le titre, identifie marque/modèle/trim,
et fournit des angles de vente spécifiques à chaque véhicule.
"""

import re
from typing import Dict, Any, Optional, List, Tuple


# ─── Base de connaissance : Marques ───
BRAND_PROFILES = {
    "ram": {
        "tone": "puissance",
        "emoji": "💪",
        "identity": "le truck qui travaille aussi fort que toi",
        "angles": ["capacité de remorquage", "robustesse", "confort de cabine", "moteur Cummins/HEMI"],
    },
    "dodge": {
        "tone": "performance",
        "emoji": "🏁",
        "identity": "la performance américaine pure",
        "angles": ["puissance brute", "son du moteur", "look agressif", "adrénaline"],
    },
    "jeep": {
        "tone": "aventure",
        "emoji": "🏔️",
        "identity": "la liberté de rouler partout",
        "angles": ["capacité hors route", "polyvalence", "look iconique", "4x4"],
    },
    "chrysler": {
        "tone": "confort",
        "emoji": "✨",
        "identity": "le confort familial raffiné",
        "angles": ["espace intérieur", "technologie", "confort", "sécurité"],
    },
    "fiat": {
        "tone": "urbain",
        "emoji": "⚡",
        "identity": "le style européen électrique",
        "angles": ["économie", "style", "format compact", "zéro émission"],
    },
    "ford": {
        "tone": "polyvalent",
        "emoji": "🔥",
        "identity": "l'icône américaine",
        "angles": ["fiabilité", "performance", "polyvalence", "tradition"],
    },
    "chevrolet": {
        "tone": "polyvalent",
        "emoji": "🔥",
        "identity": "la fiabilité américaine",
        "angles": ["rapport qualité-prix", "fiabilité", "performance", "polyvalence"],
    },
    "toyota": {
        "tone": "fiabilité",
        "emoji": "🛡️",
        "identity": "la fiabilité légendaire",
        "angles": ["durabilité", "revente", "économie de carburant", "fiabilité prouvée"],
    },
    "honda": {
        "tone": "fiabilité",
        "emoji": "🛡️",
        "identity": "l'ingénierie japonaise",
        "angles": ["fiabilité", "économie", "conduite agréable", "valeur de revente"],
    },
    "hyundai": {
        "tone": "moderne",
        "emoji": "🚀",
        "identity": "la technologie accessible",
        "angles": ["garantie", "technologie", "design moderne", "rapport qualité-prix"],
    },
    "kia": {
        "tone": "moderne",
        "emoji": "🚀",
        "identity": "le design qui surprend",
        "angles": ["design", "garantie", "technologie", "valeur"],
    },
    "mazda": {
        "tone": "plaisir",
        "emoji": "🎯",
        "identity": "le plaisir de conduire",
        "angles": ["conduite", "design", "qualité intérieure", "Skyactiv"],
    },
    "subaru": {
        "tone": "aventure",
        "emoji": "🏔️",
        "identity": "la traction intégrale de série",
        "angles": ["AWD", "sécurité", "fiabilité", "conduite hivernale"],
    },
    "volkswagen": {
        "tone": "raffiné",
        "emoji": "🇩🇪",
        "identity": "l'ingénierie allemande",
        "angles": ["qualité de construction", "conduite", "technologie", "raffinement"],
    },
    "bmw": {
        "tone": "luxe",
        "emoji": "🏎️",
        "identity": "le plaisir de conduire premium",
        "angles": ["performance", "luxe", "technologie", "prestige"],
    },
    "mercedes": {
        "tone": "luxe",
        "emoji": "⭐",
        "identity": "le luxe qui ne fait pas de compromis",
        "angles": ["confort", "prestige", "sécurité", "technologie de pointe"],
    },
    "lamborghini": {
        "tone": "exotique",
        "emoji": "🐂",
        "identity": "le rêve automobile",
        "angles": ["exclusivité", "performance extrême", "design", "expérience unique"],
    },
    "porsche": {
        "tone": "exotique",
        "emoji": "🏎️",
        "identity": "la perfection sportive",
        "angles": ["ingénierie", "performance", "prestige", "conduite"],
    },
    "tesla": {
        "tone": "futuriste",
        "emoji": "⚡",
        "identity": "le futur de l'automobile",
        "angles": ["autonomie", "technologie", "performance instantanée", "zéro émission"],
    },
    "gmc": {
        "tone": "puissance",
        "emoji": "💪",
        "identity": "le premium professionnel",
        "angles": ["capacité", "luxe utilitaire", "robustesse", "technologie"],
    },
    "nissan": {
        "tone": "polyvalent",
        "emoji": "🔥",
        "identity": "l'innovation accessible",
        "angles": ["technologie", "polyvalence", "fiabilité", "rapport qualité-prix"],
    },
    "plymouth": {
        "tone": "classique",
        "emoji": "🏁",
        "identity": "la légende américaine",
        "angles": ["collector", "rareté", "histoire", "look unique"],
    },
    "ferrari": {
        "tone": "exotique",
        "emoji": "🏎️",
        "identity": "la quintessence de la supercar italienne",
        "angles": ["exclusivité", "performance extrême", "héritage course", "design italien"],
    },
    "audi": {
        "tone": "raffiné",
        "emoji": "🇩🇪",
        "identity": "la technologie allemande de pointe",
        "angles": ["Quattro AWD", "technologie", "qualité de construction", "performance"],
    },
    "buick": {
        "tone": "confort",
        "emoji": "✨",
        "identity": "le confort américain premium",
        "angles": ["confort", "silence de roulement", "technologie", "valeur"],
    },
    "cadillac": {
        "tone": "luxe",
        "emoji": "⭐",
        "identity": "le luxe américain audacieux",
        "angles": ["luxe", "technologie", "performance", "prestige"],
    },
    "mitsubishi": {
        "tone": "aventure",
        "emoji": "🏔️",
        "identity": "le 4x4 japonais fiable",
        "angles": ["AWD", "fiabilité", "garantie", "rapport qualité-prix"],
    },
}

# ─── Base de connaissance : Modèles spécifiques ───
MODEL_SPECS = {
    # DODGE
    "challenger": {
        "type": "muscle_car",
        "known_for": "muscle car américain légendaire",
        "trims": {
            "sxt": {"hp": "303", "engine": "V6 Pentastar 3.6L", "vibe": "l'entrée dans le monde muscle"},
            "gt": {"hp": "303", "engine": "V6 Pentastar 3.6L AWD", "vibe": "le muscle avec traction intégrale"},
            "r/t": {"hp": "375", "engine": "V8 HEMI 5.7L", "vibe": "le vrai son HEMI"},
            "r/t scat pack": {"hp": "485", "engine": "V8 HEMI 6.4L 392", "vibe": "485 chevaux de pure adrénaline"},
            "scat pack": {"hp": "485", "engine": "V8 HEMI 6.4L 392", "vibe": "la bête de 485 chevaux"},
            "hellcat": {"hp": "717", "engine": "V8 HEMI Supercharged 6.2L", "vibe": "717 chevaux. Point final."},
            "demon": {"hp": "840", "engine": "V8 HEMI Supercharged 6.2L", "vibe": "le monstre de la drag strip"},
        },
    },
    "charger": {
        "type": "muscle_sedan",
        "known_for": "la seule berline muscle car 4 portes",
        "trims": {
            "sxt": {"hp": "303", "engine": "V6 Pentastar 3.6L"},
            "gt": {"hp": "303", "engine": "V6 Pentastar 3.6L AWD"},
            "r/t": {"hp": "375", "engine": "V8 HEMI 5.7L"},
            "scat pack": {"hp": "485", "engine": "V8 HEMI 6.4L 392"},
            "hellcat": {"hp": "717", "engine": "V8 HEMI Supercharged 6.2L"},
        },
    },
    "hornet": {
        "type": "suv_compact",
        "known_for": "le petit SUV Dodge avec du punch",
        "trims": {
            "gt": {"hp": "268", "engine": "Turbo 2.0L", "vibe": "compact mais costaud"},
            "r/t": {"hp": "288", "engine": "Turbo 1.3L + électrique PHEV", "vibe": "hybride rechargeable avec du caractère"},
            "r/t plus": {"hp": "288", "engine": "Turbo 1.3L + électrique PHEV", "vibe": "le PHEV tout équipé"},
        },
    },
    # JEEP
    "wrangler": {
        "type": "off_road",
        "known_for": "l'icône du hors-route depuis 1941",
        "trims": {
            "sport": {"vibe": "le Wrangler pur et dur, prêt pour la trail"},
            "sahara": {"vibe": "le Wrangler confortable pour la route ET la trail"},
            "rubicon": {"vibe": "le roi absolu du hors-route, lockers et tout"},
            "4xe": {"vibe": "le Wrangler hybride rechargeable — trail ET électrique"},
            "rubicon 4xe": {"vibe": "hors-route extrême + hybride rechargeable"},
        },
    },
    "grand cherokee": {
        "type": "suv_premium",
        "known_for": "le SUV premium américain par excellence",
        "trims": {
            "laredo": {"vibe": "l'entrée dans le monde Grand Cherokee"},
            "limited": {"vibe": "cuir, tech et confort — le sweet spot"},
            "overland": {"vibe": "le luxe avec capacité hors-route"},
            "summit": {"vibe": "le sommet du luxe — tout y est"},
            "trailhawk": {"vibe": "le Grand Cherokee prêt pour le sentier"},
            "4xe": {"vibe": "hybride rechargeable avec le luxe Jeep"},
        },
    },
    "compass": {
        "type": "suv_compact",
        "known_for": "le SUV compact Jeep accessible",
        "trims": {
            "sport": {"vibe": "compact et capable"},
            "latitude": {"vibe": "bien équipé pour le quotidien"},
            "limited": {"vibe": "le petit luxe Jeep"},
            "trailhawk": {"vibe": "le plus capable de sa catégorie"},
        },
    },
    # RAM
    "1500": {
        "type": "pickup",
        "known_for": "le pickup pleine grandeur le plus confortable",
        "trims": {
            "tradesman": {"vibe": "le truck de travail, simple et efficace"},
            "big horn": {"vibe": "le meilleur rapport équipement-prix"},
            "classic slt": {"vibe": "le Classic — équipement solide à prix compétitif"},
            "classic tradesman": {"vibe": "le Classic pour le travail au quotidien"},
            "slt": {"vibe": "bien équipé — le choix populaire"},
            "sport": {"hp": "395", "engine": "V8 HEMI 5.7L", "vibe": "le HEMI avec le look sport — roues noires et grille sport"},
            "laramie": {"vibe": "cuir et chrome — le truck premium"},
            "rebel": {"vibe": "le look off-road avec la suspension Bilstein"},
            "limited": {"vibe": "le truck limousine — tout le luxe"},
            "trx": {"hp": "702", "engine": "V8 HEMI Supercharged 6.2L", "vibe": "702 chevaux dans un pickup. Oui."},
        },
    },
    "2500": {
        "type": "pickup_hd",
        "known_for": "le heavy-duty qui remorque tout",
        "trims": {
            "tradesman": {"vibe": "fait pour travailler, point"},
            "slt": {"vibe": "heavy-duty bien équipé au bon prix"},
            "big horn": {"vibe": "heavy-duty bien équipé"},
            "laramie": {"vibe": "HD avec intérieur premium"},
            "limited": {"vibe": "le HD le plus luxueux sur le marché"},
            "power wagon": {"vibe": "le HD off-road ultime avec Warn winch"},
        },
    },
    "promaster": {
        "type": "commercial",
        "known_for": "le fourgon commercial #1 pour les entrepreneurs",
        "trims": {
            "cargo van": {"vibe": "l'espace de travail mobile"},
            "tradesman": {"vibe": "prêt pour le business dès la sortie du lot"},
            "1500": {"vibe": "le ProMaster compact — maniable en ville"},
            "2500": {"vibe": "le ProMaster mid — bon équilibre charge/maniabilité"},
            "3500": {"vibe": "le ProMaster max — charge maximale pour les pros"},
            "1500 136": {"vibe": "empattement court — parfait pour les livraisons urbaines"},
            "1500 118": {"vibe": "le plus compact — facile à stationner"},
            "2500 high": {"vibe": "toit haut — debout à l'intérieur pour travailler"},
            "3500 high": {"vibe": "toit haut + charge max — le fourgon ultime"},
            "3500 high extended": {"vibe": "toit haut + empattement long — le plus d'espace possible"},
        },
    },
    # FORD
    "mustang": {
        "type": "muscle_car",
        "known_for": "la légende américaine depuis 1964",
        "trims": {
            "ecoboost": {"hp": "310", "engine": "Turbo 2.3L EcoBoost", "vibe": "le turbo efficace"},
            "gt": {"hp": "450", "engine": "V8 Coyote 5.0L", "vibe": "le V8 légendaire"},
            "mach 1": {"hp": "480", "engine": "V8 Coyote 5.0L", "vibe": "entre le GT et le Shelby"},
            "shelby gt500": {"hp": "760", "engine": "V8 Supercharged 5.2L", "vibe": "la Mustang ultime"},
        },
    },
    # FIAT
    "500": {
        "type": "citadine",
        "known_for": "le style italien électrique",
        "trims": {
            "e": {"vibe": "100% électrique, 100% style"},
            "red": {"vibe": "édition spéciale (RED) — style et cause"},
        },
    },
    # TOYOTA
    "rav4": {
        "type": "suv_compact",
        "known_for": "le SUV compact le plus vendu au monde",
        "trims": {
            "le": {"vibe": "bien équipé de série"},
            "xle": {"vibe": "le sweet spot — confort et valeur"},
            "limited": {"vibe": "tout équipé, rien ne manque"},
            "trail": {"vibe": "prêt pour l'aventure avec AWD"},
        },
    },
    # MAZDA
    "cx-90": {
        "type": "suv_premium",
        "known_for": "le SUV 3 rangées premium de Mazda",
        "trims": {
            "gs-l": {"vibe": "le luxe Mazda accessible"},
            "gt": {"vibe": "cuir Nappa et bois véritable"},
            "phev": {"vibe": "hybride rechargeable premium"},
            "premium": {"vibe": "le haut de gamme Mazda — cuir, bois, technologie"},
            "premium plus": {"vibe": "le summum du luxe Mazda avec tout l'équipement"},
            "premium signature": {"vibe": "édition signature — le meilleur de Mazda, point final"},
        },
    },
    "cx-5": {
        "type": "suv_compact",
        "known_for": "le SUV compact le plus plaisant à conduire",
        "trims": {
            "gs": {"vibe": "bien équipé et agréable"},
            "gt": {"vibe": "cuir et toit ouvrant — le sweet spot"},
            "signature": {"vibe": "le CX-5 ultime — turbo et luxe"},
        },
    },
    "cx-50": {
        "type": "suv_compact",
        "known_for": "le SUV compact aventurier de Mazda",
        "trims": {
            "gs": {"vibe": "prêt pour l'aventure de série"},
            "gt": {"vibe": "confort et capacité off-road"},
            "meridian": {"vibe": "édition premium — turbo et cuir"},
        },
    },
    # PLYMOUTH
    "prowler": {
        "type": "collector",
        "known_for": "le hot rod de usine — une pièce de collection rare",
        "trims": {},
    },
    "satellite": {
        "type": "collector",
        "known_for": "le muscle car classique Plymouth des années 60-70",
        "trims": {},
    },
    # JEEP (modèles manquants)
    "wagoneer": {
        "type": "suv_premium",
        "known_for": "le grand SUV de luxe américain par Jeep",
        "trims": {
            "series i": {"vibe": "l'entrée dans le monde Wagoneer — déjà très équipé"},
            "series ii": {"vibe": "le luxe Wagoneer avec plus de technologie et de confort"},
            "series iii": {"vibe": "le Wagoneer tout inclus — rien ne manque"},
        },
    },
    "renegade": {
        "type": "suv_compact",
        "known_for": "le petit Jeep au look unique — compact mais capable",
        "trims": {
            "sport": {"vibe": "compact et abordable avec le badge Jeep"},
            "north": {"vibe": "bien équipé pour le climat canadien"},
            "limited": {"vibe": "le petit luxe Jeep"},
            "trailhawk": {"vibe": "le plus capable des petits SUV — Trail Rated"},
        },
    },
    # CHEVROLET
    "malibu": {
        "type": "berline",
        "known_for": "la berline intermédiaire fiable et économique",
        "trims": {
            "ls": {"vibe": "l'essentiel bien fait"},
            "lt": {"hp": "160", "engine": "Turbo 1.5L", "vibe": "le meilleur rapport équipement-prix"},
            "rs": {"vibe": "le look sportif avec le turbo"},
            "premier": {"vibe": "tout équipé — cuir et technologie"},
        },
    },
    "silverado": {
        "type": "pickup",
        "known_for": "le pickup pleine grandeur le plus vendu en Amérique",
        "trims": {
            "wt": {"vibe": "le truck de travail, simple et efficace"},
            "custom": {"vibe": "le look custom sans le prix custom"},
            "lt": {"vibe": "bien équipé pour le quotidien"},
            "rst": {"vibe": "le look sport streetside"},
            "ltz": {"vibe": "cuir et chrome — le Silverado premium"},
            "high country": {"vibe": "le Silverado le plus luxueux — tout y est"},
            "trail boss": {"vibe": "le off-road Chevy avec suspension relevée"},
            "zr2": {"hp": "420", "engine": "V8 6.2L", "vibe": "le Silverado off-road extrême — Multimatic DSSV"},
        },
    },
    "equinox": {
        "type": "suv_compact",
        "known_for": "le SUV compact familial par excellence chez Chevy",
        "trims": {
            "ls": {"vibe": "l'essentiel pour la famille"},
            "lt": {"vibe": "bien équipé et polyvalent"},
            "rs": {"vibe": "le look sportif"},
            "premier": {"vibe": "tout équipé — cuir et technologie"},
        },
    },
    # HONDA
    "civic": {
        "type": "berline",
        "known_for": "la compacte la plus fiable et la plus vendue au monde",
        "trims": {
            "dx": {"vibe": "l'essentiel Honda — fiable et économique"},
            "lx": {"vibe": "bien équipé de série"},
            "ex": {"hp": "158", "engine": "2.0L i-VTEC", "vibe": "le sweet spot — toit ouvrant et Honda Sensing"},
            "ex-l": {"vibe": "cuir et tout le confort"},
            "touring": {"vibe": "la Civic tout équipée — navigation et cuir"},
            "sport": {"vibe": "le look sportif avec le moteur turbo"},
            "si": {"hp": "200", "engine": "Turbo 1.5L", "vibe": "la Civic sportive — turbo et manuelle"},
            "type r": {"hp": "315", "engine": "Turbo 2.0L", "vibe": "la bête de piste — 315 chevaux de pure rage"},
        },
    },
    "cr-v": {
        "type": "suv_compact",
        "known_for": "le SUV compact Honda — fiabilité légendaire",
        "trims": {
            "lx": {"vibe": "AWD et Honda Sensing de série"},
            "ex": {"vibe": "le sweet spot avec toit ouvrant"},
            "ex-l": {"vibe": "cuir et sièges chauffants"},
            "touring": {"vibe": "tout équipé — le CR-V ultime"},
        },
    },
    "accord": {
        "type": "berline",
        "known_for": "la berline intermédiaire référence — confort et fiabilité",
        "trims": {
            "lx": {"vibe": "bien équipé de série"},
            "ex": {"vibe": "le meilleur rapport qualité-prix"},
            "ex-l": {"vibe": "cuir et navigation"},
            "sport": {"hp": "252", "engine": "Turbo 2.0L", "vibe": "le turbo qui surprend"},
            "touring": {"hp": "252", "engine": "Turbo 2.0L", "vibe": "tout le luxe Honda — le sommet"},
        },
    },
    # CHRYSLER
    "pacifica": {
        "type": "minivan",
        "known_for": "la meilleure minifourgonnette sur le marché — confort familial",
        "trims": {
            "lx": {"vibe": "l'essentiel familial bien fait"},
            "touring": {"vibe": "Stow 'n Go et confort pour toute la famille"},
            "touring l": {"vibe": "cuir et portières électriques"},
            "limited": {"vibe": "le luxe familial — tout y est"},
            "pinnacle": {"vibe": "le summum du luxe en minifourgonnette"},
            "hybrid": {"vibe": "hybride rechargeable — économique et familial"},
        },
    },
    "300": {
        "type": "berline",
        "known_for": "la grande berline américaine au look imposant",
        "trims": {
            "touring": {"hp": "292", "engine": "V6 Pentastar 3.6L", "vibe": "le look imposant à bon prix"},
            "s": {"hp": "300", "engine": "V6 Pentastar 3.6L", "vibe": "le look sport avec les roues noires"},
            "c": {"hp": "363", "engine": "V8 HEMI 5.7L", "vibe": "le V8 HEMI dans une berline de luxe"},
        },
    },
    # DODGE (modèles manquants)
    "durango": {
        "type": "suv_premium",
        "known_for": "le seul SUV 3 rangées avec un V8 HEMI disponible",
        "trims": {
            "sxt": {"hp": "293", "engine": "V6 Pentastar 3.6L", "vibe": "le SUV Dodge accessible"},
            "gt": {"hp": "293", "engine": "V6 Pentastar 3.6L", "vibe": "le look sport avec AWD"},
            "r/t": {"hp": "360", "engine": "V8 HEMI 5.7L", "vibe": "le V8 HEMI dans un SUV familial"},
            "citadel": {"hp": "360", "engine": "V8 HEMI 5.7L", "vibe": "le luxe Durango — cuir et chrome"},
            "srt 392": {"hp": "475", "engine": "V8 HEMI 6.4L 392", "vibe": "475 chevaux dans un SUV 3 rangées"},
            "srt hellcat": {"hp": "710", "engine": "V8 HEMI Supercharged 6.2L", "vibe": "le SUV le plus puissant jamais construit"},
        },
    },
    # RAM (trims manquants)
    "promaster city": {
        "type": "commercial",
        "known_for": "le fourgon compact idéal pour la ville",
        "trims": {
            "tradesman": {"vibe": "compact et maniable pour les livraisons"},
            "wagon": {"vibe": "version passagers — 5 places"},
        },
    },
    # TOYOTA (modèles supplémentaires)
    "corolla": {
        "type": "berline",
        "known_for": "la voiture la plus vendue de l'histoire — fiabilité absolue",
        "trims": {
            "l": {"vibe": "l'essentiel Toyota"},
            "le": {"vibe": "bien équipé et économique"},
            "se": {"vibe": "le look sport avec la boîte CVT"},
            "xse": {"vibe": "le sport haut de gamme"},
        },
    },
    "tacoma": {
        "type": "pickup",
        "known_for": "le pickup mid-size indestructible",
        "trims": {
            "sr": {"vibe": "le truck de travail Toyota"},
            "sr5": {"vibe": "le sweet spot — bien équipé"},
            "trd sport": {"vibe": "le look sport sur route"},
            "trd off-road": {"vibe": "Trail Rated — prêt pour le sentier"},
            "trd pro": {"vibe": "le Tacoma ultime — TRD suspension et tout"},
            "limited": {"vibe": "le luxe dans un pickup mid-size"},
        },
    },
    "4runner": {
        "type": "off_road",
        "known_for": "le SUV body-on-frame — robuste et indestructible",
        "trims": {
            "sr5": {"vibe": "le 4Runner classique"},
            "trd off-road": {"vibe": "différentiel arrière verrouillable — sérieux"},
            "trd pro": {"vibe": "le 4Runner ultime pour le hors-route extrême"},
            "limited": {"vibe": "luxe et capacité combinés"},
        },
    },
    "highlander": {
        "type": "suv_premium",
        "known_for": "le SUV 3 rangées familial par excellence",
        "trims": {
            "le": {"vibe": "bien équipé de série"},
            "xle": {"vibe": "le sweet spot familial"},
            "limited": {"vibe": "cuir et technologie — tout y est"},
            "platinum": {"vibe": "le sommet du luxe Toyota"},
        },
    },
    # FORD (modèles supplémentaires)
    "f-150": {
        "type": "pickup",
        "known_for": "le véhicule le plus vendu en Amérique — le roi des pickups",
        "trims": {
            "xl": {"vibe": "le truck de travail Ford"},
            "xlt": {"hp": "400", "engine": "V6 EcoBoost 3.5L", "vibe": "le meilleur vendeur — bien équipé"},
            "lariat": {"vibe": "cuir et chrome — le F-150 premium"},
            "king ranch": {"vibe": "l'héritage texan — cuir et bois"},
            "platinum": {"vibe": "le luxe absolu dans un pickup"},
            "tremor": {"vibe": "le F-150 off-road avec suspension trail"},
            "raptor": {"hp": "450", "engine": "V6 EcoBoost 3.5L HO", "vibe": "le pickup haute performance — Baja ready"},
            "raptor r": {"hp": "720", "engine": "V8 Supercharged 5.2L", "vibe": "720 chevaux dans un pickup. Fou."},
        },
    },
    "explorer": {
        "type": "suv_premium",
        "known_for": "le SUV 3 rangées Ford — aventure et famille",
        "trims": {
            "base": {"vibe": "l'Explorer bien équipé de série"},
            "xlt": {"vibe": "le sweet spot familial"},
            "limited": {"vibe": "cuir et technologie"},
            "st": {"hp": "400", "engine": "V6 EcoBoost 3.0L", "vibe": "400 chevaux dans un SUV familial"},
            "timberline": {"vibe": "l'Explorer prêt pour le sentier"},
        },
    },
    "bronco": {
        "type": "off_road",
        "known_for": "le retour de la légende Ford — hors-route pur et dur",
        "trims": {
            "base": {"vibe": "le Bronco pur — portes et toit amovibles"},
            "big bend": {"vibe": "un peu plus de confort pour la trail"},
            "outer banks": {"vibe": "le look côtier avec tout l'équipement"},
            "badlands": {"vibe": "le sérieux hors-route — stabilisateur déconnectable"},
            "wildtrak": {"vibe": "les gros pneus et le Sasquatch package"},
            "raptor": {"hp": "418", "engine": "V6 EcoBoost 3.0L", "vibe": "le Bronco extrême — suspension Baja"},
        },
    },
    "escape": {
        "type": "suv_compact",
        "known_for": "le SUV compact Ford — polyvalent et économique",
        "trims": {
            "s": {"vibe": "l'essentiel Ford"},
            "se": {"vibe": "bien équipé et AWD disponible"},
            "sel": {"vibe": "confort et technologie"},
            "titanium": {"vibe": "le haut de gamme compact Ford"},
        },
    },
    # FERRARI
    "488": {
        "type": "exotique",
        "known_for": "la supercar turbo qui a redéfini Ferrari",
        "trims": {
            "gtb": {"hp": "661", "engine": "V8 Biturbo 3.9L", "vibe": "661 chevaux de pure ingénierie italienne"},
            "spider": {"hp": "661", "engine": "V8 Biturbo 3.9L", "vibe": "le même monstre, mais à ciel ouvert"},
            "pista": {"hp": "710", "engine": "V8 Biturbo 3.9L", "vibe": "née sur la piste — la 488 ultime"},
        },
    },
    "488gtb": {
        "type": "exotique",
        "known_for": "la supercar turbo qui a redéfini Ferrari",
        "trims": {},
    },
    # HYUNDAI (modèles courants)
    "tucson": {
        "type": "suv_compact",
        "known_for": "le SUV compact au design futuriste",
        "trims": {
            "essential": {"vibe": "bien équipé de série"},
            "preferred": {"vibe": "AWD et sièges chauffants"},
            "ultimate": {"vibe": "tout inclus — le luxe Hyundai"},
        },
    },
    "santa fe": {
        "type": "suv_premium",
        "known_for": "le SUV familial redessiné avec audace",
        "trims": {
            "essential": {"vibe": "spacieux et bien équipé"},
            "preferred": {"vibe": "le sweet spot familial"},
            "ultimate": {"vibe": "cuir et panoramique — tout y est"},
            "calligraphy": {"vibe": "le sommet du luxe Hyundai"},
        },
    },
    # SUBARU
    "outback": {
        "type": "suv_compact",
        "known_for": "le wagon surélevé avec AWD — aventure et quotidien",
        "trims": {
            "base": {"vibe": "AWD de série — prêt pour l'hiver"},
            "limited": {"vibe": "cuir et EyeSight — le sweet spot"},
            "onyx": {"vibe": "le look aventurier avec les accents noirs"},
            "wilderness": {"vibe": "le vrai off-road Subaru — suspension relevée"},
        },
    },
    "forester": {
        "type": "suv_compact",
        "known_for": "le SUV compact avec la meilleure visibilité de sa catégorie",
        "trims": {
            "base": {"vibe": "AWD et EyeSight de série"},
            "touring": {"vibe": "cuir et toit panoramique"},
            "sport": {"vibe": "le look sport avec le moteur turbo"},
            "wilderness": {"vibe": "le Forester prêt pour le sentier"},
        },
    },
}

# ─── Kilométrage intelligence ───
def km_description(km: int) -> str:
    if km is None:
        return ""
    if km <= 100:
        return "pratiquement neuf — jamais roulé"
    if km <= 5000:
        return "à peine rodé"
    if km <= 15000:
        return "très bas kilométrage"
    if km <= 30000:
        return "bas kilométrage"
    if km <= 60000:
        return "kilométrage raisonnable"
    if km <= 100000:
        return "bien entretenu"
    if km <= 150000:
        return "kilométrage honnête pour l'année"
    return "véhicule d'expérience"

# ─── Prix intelligence ───
def price_description(price: int, vehicle_type: str = "") -> str:
    if price is None:
        return ""
    if price < 20000:
        return "prix d'ami"
    if price < 30000:
        return "excellent rapport qualité-prix"
    if price < 45000:
        return "bien positionné"
    if price < 65000:
        return "investissement solide"
    if price < 100000:
        return "véhicule premium"
    if price < 200000:
        return "véhicule de prestige"
    return "pièce d'exception"


def parse_vehicle_title(title: str) -> Dict[str, str]:
    """
    Parse un titre comme 'Ram 2500 BIG HORN 2025' ou 'Dodge CHALLENGER R/T SCAT PACK BLANC 2023'
    Retourne: brand, model, trim, year, color
    """
    title = (title or "").strip()
    result = {"brand": "", "model": "", "trim": "", "year": "", "color": "", "raw_title": title}

    # Extraire l'année (4 chiffres, généralement 2000+)
    year_match = re.search(r'\b(19\d{2}|20\d{2})\b', title)
    if year_match:
        result["year"] = year_match.group(1)
        title_no_year = title[:year_match.start()].strip()
    else:
        title_no_year = title

    # Couleurs connues à retirer
    colors = ["blanc", "blanche", "noir", "noire", "rouge", "bleu", "bleue", "gris", "grise",
              "argent", "vert", "verte", "orange", "jaune", "brun", "brune", "beige",
              "white", "black", "red", "blue", "grey", "gray", "silver", "green"]
    title_clean = title_no_year
    for c in colors:
        pattern = re.compile(r'\b' + re.escape(c) + r'\b', re.IGNORECASE)
        if pattern.search(title_clean):
            result["color"] = c.capitalize()
            title_clean = pattern.sub('', title_clean).strip()

    # Nettoyer les espaces multiples
    title_clean = re.sub(r'\s+', ' ', title_clean).strip()

    # Détecter la marque
    parts = title_clean.split()
    if not parts:
        return result

    brand_candidate = parts[0].lower().replace("-", "")
    # Cas spéciaux
    if brand_candidate in ("lamborghin", "lamborghini"):
        brand_candidate = "lamborghini"
    elif brand_candidate == "mercedes" or brand_candidate == "mercedes-benz":
        brand_candidate = "mercedes"

    result["brand"] = brand_candidate

    # Le reste est modèle + trim
    remaining = " ".join(parts[1:]).strip()

    # Essayer de matcher un modèle connu
    remaining_lower = remaining.lower()
    best_model = ""
    best_model_len = 0

    brand_models = {k: v for k, v in MODEL_SPECS.items()}
    for model_name in brand_models:
        if model_name.lower() in remaining_lower:
            if len(model_name) > best_model_len:
                best_model = model_name
                best_model_len = len(model_name)

    if best_model:
        result["model"] = best_model
        # Ce qui reste après le modèle = trim
        idx = remaining_lower.find(best_model.lower())
        after_model = remaining[idx + len(best_model):].strip()
        # Nettoyer
        after_model = re.sub(r'\s+', ' ', after_model).strip()
        # Retirer A/C, 4X4, AWD etc. du trim pour le garder propre
        result["trim"] = after_model
    else:
        # Pas de modèle connu — prendre le premier mot comme modèle
        rem_parts = remaining.split()
        if rem_parts:
            result["model"] = rem_parts[0]
            result["trim"] = " ".join(rem_parts[1:])

    return result


def get_vehicle_profile(parsed: Dict[str, str]) -> Dict[str, Any]:
    """
    Retourne un profil complet du véhicule basé sur le parsing.
    """
    brand = parsed.get("brand", "").lower()
    model = parsed.get("model", "").lower()
    trim = parsed.get("trim", "").lower()

    profile = {
        "brand_profile": BRAND_PROFILES.get(brand, BRAND_PROFILES.get("ford")),  # fallback générique
        "model_specs": None,
        "trim_specs": None,
        "vehicle_type": "general",
        "known_for": "",
        "hp": "",
        "engine": "",
        "vibe": "",
    }

    # Chercher le modèle
    model_data = MODEL_SPECS.get(model)
    if model_data:
        profile["model_specs"] = model_data
        profile["vehicle_type"] = model_data.get("type", "general")
        profile["known_for"] = model_data.get("known_for", "")

        # Chercher le trim
        trims = model_data.get("trims", {})
        best_trim = None
        best_trim_len = 0
        for trim_key, trim_val in trims.items():
            if trim_key.lower() in trim:
                if len(trim_key) > best_trim_len:
                    best_trim = trim_val
                    best_trim_len = len(trim_key)

        if best_trim:
            profile["trim_specs"] = best_trim
            profile["hp"] = best_trim.get("hp", "")
            profile["engine"] = best_trim.get("engine", "")
            profile["vibe"] = best_trim.get("vibe", "")

    return profile


def humanize_options(options_text: str) -> List[str]:
    """
    Convertit les options brutes du sticker en texte humain lisible.
    """
    translations = {
        "BAQUETS AVANT": "Sièges baquets avant",
        "VENTILES DESSUS CUIR": "ventilés en cuir",
        "TISSU CATEGORIE SUP": "en tissu premium",
        "SIEGES AVANT CHAUFFANTS": "Sièges avant chauffants",
        "SIEGES ARRIERE CHAUFFANTS": "Sièges arrière chauffants",
        "VOLANT CHAUFFANT": "Volant chauffant",
        "ENSEMBLE SIEGES ET VOLANT CHAUFFANTS": "Sièges et volant chauffants",
        "ECROUS DE ROUE ANTIVOL": "Écrous de roue antivol",
        "ENSEMBLE TECHNOLOGIE": "Ensemble technologie",
        "ENSEMBLE PROTECTION": "Ensemble protection",
        "ENSEMBLE ECLAIR": "Ensemble complet",
        "EDITION NUIT": "Édition Nuit (look noir)",
        "TRANS AUTO": "Transmission automatique",
        "TORQUEFLITE": "TorqueFlite",
        "GLACES A ECRAN SOLAIRE": "Vitres teintées",
        "FREINS ANTIBLOCAGE": "Freins ABS",
        "SYSTEME DE REDUCTION ACTIF DU BRUIT": "Insonorisation active",
        "COUCHE NACREE ROUGE": "Peinture rouge nacrée",
        "COUCHE NACREE": "Peinture nacrée",
        "SUSPENSION HAUTE PERFORMANCE": "Suspension sport haute performance",
        "PNEUS RTE/HORS RTE": "Pneus route/hors-route",
        "PORT USB": "Port USB",
        "PORTS USB": "Ports USB",
        "ECRAN COULEUR TFT": "Écran couleur TFT",
        "OUVRE-PORTE DE GARAGE UNIVERSEL": "Ouvre-porte de garage intégré",
        "TROUSSE DE REPARATION DE PNEUS": "Kit de réparation de pneus",
        "MOPAR": "Mopar (accessoire officiel)",
        "PASSENGER BUCKET SEAT": "Siège passager baquet",
        "CARGO AREA FLOOR MAT": "Tapis de plancher cargo",
        "KEY FOBS": "clés supplémentaires",
    }

    lines = options_text.strip().split("\n")
    humanized = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("▫️"):
            continue

        clean = line.lstrip("✅").lstrip("■").lstrip("-").strip()
        if not clean or len(clean) < 3:
            continue

        # Appliquer les traductions
        result = clean
        for raw, human in translations.items():
            if raw.upper() in result.upper():
                result = result.upper().replace(raw.upper(), human)
                break

        # Nettoyer les codes internes (2UZ, 22B, 2GH, etc.)
        result = re.sub(r'\b\d{1,2}[A-Z]{1,3}\b', '', result).strip()
        result = re.sub(r'\s+', ' ', result).strip()

        if result and len(result) > 3:
            humanized.append(result)

    return humanized[:8]  # Max 8 options


def build_vehicle_context(vehicle: Dict[str, Any]) -> Dict[str, Any]:
    """
    Construit le contexte complet pour la génération de texte.
    Entrée: dictionnaire véhicule (title, stock, vin, price_int, km_int, etc.)
    Sortie: contexte enrichi avec intelligence véhicule
    """
    title = vehicle.get("title", "")
    parsed = parse_vehicle_title(title)
    profile = get_vehicle_profile(parsed)

    price = vehicle.get("price_int")
    km = vehicle.get("km_int")

    context = {
        # Identité
        "title": title,
        "brand": parsed["brand"],
        "model": parsed["model"],
        "trim": parsed["trim"],
        "year": parsed["year"],
        "color": parsed["color"],
        "stock": vehicle.get("stock", ""),
        "vin": vehicle.get("vin", ""),

        # Chiffres
        "price": price,
        "price_formatted": f"{price:,}".replace(",", " ") + " $" if price else "",
        "km": km,
        "km_formatted": f"{km:,}".replace(",", " ") + " km" if km else "",

        # Intelligence
        "vehicle_type": profile["vehicle_type"],
        "brand_tone": profile["brand_profile"]["tone"] if profile["brand_profile"] else "polyvalent",
        "brand_emoji": profile["brand_profile"]["emoji"] if profile["brand_profile"] else "🔥",
        "brand_identity": profile["brand_profile"]["identity"] if profile["brand_profile"] else "",
        "brand_angles": profile["brand_profile"]["angles"] if profile["brand_profile"] else [],
        "model_known_for": profile["known_for"],
        "hp": profile["hp"],
        "engine": profile["engine"],
        "trim_vibe": profile["vibe"],
        "km_description": km_description(km) if km else "",
        "price_description": price_description(price, profile["vehicle_type"]) if price else "",

        # URL
        "url": vehicle.get("url", ""),
    }

    return context
