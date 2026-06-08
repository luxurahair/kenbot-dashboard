# devops/contexts/__init__.py
"""Définitions des contextes projets (1 ligne par projet)."""
from .base import BaseContext

KENBOT = BaseContext(
    project="kenbot",
    keywords=["kenbot", "beauce", "facebook"],
    exclude=["calcauto", "aipro"],  # CalcAuto a son propre contexte
)

LUXURA = BaseContext(
    project="luxura",
    keywords=["luxura"],
)

CALCAUTO = BaseContext(
    project="calcauto",
    keywords=["calcauto", "aipro"],
)

ALL_PROJECTS = {
    "kenbot": KENBOT,
    "luxura": LUXURA,
    "calcauto": CALCAUTO,
}


def get_context(name):
    """Récupère un contexte par nom (lève KeyError si inconnu)."""
    return ALL_PROJECTS[name]
