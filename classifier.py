# classifier.py – version intelligente 2026 pour personnaliser AI/hashtags/tone
def classify(vehicle: dict) -> str:
    """
    Détecte le type de véhicule pour adapter l'AI intro, hashtags et ton vendeur.
    Priorité : brand > title > mots-clés.
    
    Types retournés:
    - truck: RAM, F-150, Silverado, etc.
    - suv: Jeep, 4Runner, Explorer, etc.
    - exotic: Ferrari, Lamborghini, Porsche, etc.
    - sedan: Corolla, Civic, Accord, etc.
    - coupe: Mustang, Camaro, Challenger, etc.
    - ev: Hybride, électrique
    - minivan: Caravan, Pacifica, etc.
    - default: Tout le reste
    """
    title = (vehicle.get("title") or "").lower()
    brand = (vehicle.get("brand") or "").lower()
    model = (vehicle.get("model") or "").lower()
    full_text = f"{brand} {model} {title}".strip()

    # Exotic / haut de gamme (très recherchés, ton premium)
    exotic_brands = ("ferrari", "lamborghini", "mclaren", "porsche", "aston martin", "bentley", "rolls royce", "maserati")
    if any(b in full_text for b in exotic_brands):
        return "exotic"

    # Truck / Pickup (robuste, travail, towing)
    truck_keywords = (
        "1500", "2500", "3500", "f-150", "f150", "f-250", "f250", "f-350", "f350",
        "silverado", "sierra", "tacoma", "tundra", "pickup", "camion",
        "ranger", "frontier", "colorado", "canyon", "titan", "ridgeline",
        "gladiator",  # Jeep Gladiator est un truck
    )
    truck_brands = ("ram",)  # RAM est toujours un truck
    if any(b in brand for b in truck_brands):
        return "truck"
    if any(w in full_text for w in truck_keywords):
        return "truck"

    # Jeep = toujours SUV (sauf Gladiator déjà traité)
    if "jeep" in full_text:
        return "suv"

    # SUV / CUV / VUS (familial, polyvalent, hiver Beauce)
    suv_words = (
        "suv", "cuv", "vus", "crossover",
        "rogue", "cherokee", "grand cherokee", "durango", "explorer", 
        "rav4", "cr-v", "crv", "highlander", "pilot", "pathfinder",
        "4runner", "sequoia", "expedition", "tahoe", "suburban", "yukon",
        "traverse", "blazer", "equinox", "terrain", "acadia",
        "tucson", "santa fe", "palisade", "sorento", "telluride",
        "forester", "outback", "ascent", "crosstrek",
        "cx-5", "cx-9", "cx-50", "cx-90",
        "wrangler", "wagoneer", "compass", "renegade",  # Jeep models
        "bronco", "escape", "edge",
        "hornet",  # Dodge Hornet
    )
    if any(w in full_text for w in suv_words):
        return "suv"

    # Minivan / Familial (famille, sièges, espace)
    minivan_words = ("minivan", "caravan", "grand caravan", "pacifica", "odyssey", "sienna", "town & country", "voyager")
    if any(w in full_text for w in minivan_words):
        return "minivan"

    # EV / Hybride / Électrique (éco, futur, économie essence)
    ev_words = ("ev", "électrique", "electric", "hybrid", "hybride", "plug-in", "phev", "bolt", "leaf", "model 3", "model y", "ioniq", "prius", "4xe", "e-tron")
    if any(w in full_text for w in ev_words):
        return "ev"

    # Coupe / Sport (performance, jeune)
    coupe_words = ("coupe", "charger", "challenger", "mustang", "camaro", "370z", "supra", "86", "brz", "gt-r", "corvette")
    if any(w in full_text for w in coupe_words):
        return "coupe"

    # Sedan / Berline (économique, ville)
    sedan_words = (
        "sedan", "berline", 
        "accord", "camry", "civic", "corolla", "malibu", "altima", "sentra",
        "elantra", "sonata", "optima", "k5", "forte",
        "mazda3", "mazda 3", "mazda6", "mazda 6",
        "jetta", "passat", "golf",
        "impreza", "legacy",
        "charger",  # Dodge Charger peut être sedan
    )
    if any(w in full_text for w in sedan_words):
        return "sedan"

    # Default (catch-all)
    return "default"
