# 🔧 Corrections runner_cron_prod.py — PHOTOS_ADDED ne détecte pas les posts "no photo"

## Résumé des 3 bugs trouvés et corrigés

---

### ❌ Bug 1 (CRITIQUE) : `no_photo` jamais mis à `True` lors de la création d'un post NEW

**Fichier:** `runner_cron_prod.py` — section NEW POST (ligne ~340)

**Problème:**
Quand `_download_photos()` ne trouve pas de vraies photos et utilise le fallback NO_PHOTO (`{stock}_NO_PHOTO.jpg`), le post est créé avec :
```python
"no_photo": False,        # ← TOUJOURS False !
"photo_count": len(photos),  # ← 1 (le placeholder), pas 0
```

**Conséquence:**
La détection PHOTOS_ADDED ne trouvera JAMAIS ces posts car :
- `no_photo` est `False` (pas `True`)
- `photo_count` est `1` (pas `0`)
- Le `base_text` ne contient pas forcément les mots-clés recherchés

**Fix appliqué:**
```python
# Nouvelle fonction utilitaire
def _is_no_photo_fallback(photos: List[Path]) -> bool:
    if not photos:
        return False
    if len(photos) == 1 and "NO_PHOTO" in photos[0].name:
        return True
    return False

# Dans la section NEW POST :
using_no_photo_fallback = _is_no_photo_fallback(photos)

upsert_post(sb, {
    ...
    "no_photo": using_no_photo_fallback,  # ✅ True si fallback
    "photo_count": 0 if using_no_photo_fallback else len(photos),  # ✅ 0 si fallback
})
```

---

### ❌ Bug 2 (CRASH) : Mauvais ordre d'arguments dans `_build_ad_text`

**Fichier:** `runner_cron_prod.py` — section PHOTOS_ADDED (ligne ~310)

**Problème:**
```python
# AVANT (BUGUÉ) :
base_text = _build_ad_text(sb, v, "NEW", run_id)
#                          sb  run_id  slug   v     ← SIGNATURES
#                          sb  v       "NEW"  run_id ← APPEL BUGUÉ
```

La signature est `_build_ad_text(sb, run_id, slug, v, event)` mais l'appel passe `v` comme `run_id`, `"NEW"` comme `slug`, et `run_id` comme `v`.

**Conséquence:** Crash systématique quand on essaie de régénérer le texte pour un PHOTOS_ADDED.

**Fix appliqué:**
```python
# APRÈS (CORRIGÉ) :
base_text = _build_ad_text(sb, run_id, slug, v, "NEW")
```

---

### ❌ Bug 3 : Détection de "no photo" trop restrictive

**Fichier:** `runner_cron_prod.py` — section PHOTOS_ADDED détection (ligne ~250)

**Problème:**
La recherche de mots-clés dans `base_text` ne cherche que 3 phrases :
- "photos suivront"
- "photo non disponible"  
- "nouveau véhicule en inventaire"

Mais le texte généré ne contient pas forcément ces phrases exactes.

**Fix appliqué:**
- Ajout de mots-clés supplémentaires : "no_photo", "sans photo", "photo à venir", "photos à venir"
- Ajout de logs détaillés pour chaque détection : `[PHOTOS_ADDED DETECT]`
- Dans PHOTOS_ADDED handler : vérification que les photos téléchargées ne sont PAS le fallback avec `_is_no_photo_fallback(photos)`

---

## Comment appliquer le fix

1. Copier le fichier `runner_cron_prod.py` corrigé dans votre repo `kenbot-runner`
2. Push sur GitHub
3. Render redéploie automatiquement

## Vérification

Après le prochain run du cron, vérifiez les logs pour :
- `[NO_PHOTO POST]` — confirme que le flag est correctement mis
- `[PHOTOS_ADDED DETECT]` — confirme que la détection fonctionne
- `[PHOTOS_ADDED] ✅` — confirme que le post a été recréé avec les vraies photos
