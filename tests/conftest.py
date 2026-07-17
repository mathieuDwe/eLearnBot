"""Fixtures partagées pour tous les tests eLearnBot.

Les tests utilisent le mode mémoire du document_store (pas de cloud).
Les données sont réinitialisées entre chaque test via force_in_memory_mode().
"""

import importlib
import os
import sys

import pytest

# Ajouter src/ au PYTHONPATH
_SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(_SRC_DIR))

# Désactiver Supabase pour les tests
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_KEY"] = ""


@pytest.fixture(autouse=True)
def reset_document_store():
    """Réinitialise le document_store en mode mémoire avant chaque test.

    Cette fixture est automatique (autouse=True) : elle s'exécute pour
    tous les tests sans avoir besoin d'être déclarée explicitement.
    Le cache mémoire est vidé, et Supabase est désactivé.
    """
    from core import document_store
    importlib.reload(document_store)
    document_store.force_in_memory_mode()
    yield


@pytest.fixture
def empty_doc_store():
    """Retourne le module document_store en mode mémoire (prêt à l'emploi).

    Les documents ajoutés restent en mémoire le temps du test.
    Aucune persistance cloud ni fichier local.
    """
    from core import document_store
    return document_store


@pytest.fixture
def sample_text():
    """Texte de cours réaliste pour les tests."""
    return (
        "Le théorème de Pythagore est un théorème fondamental de la géométrie "
        "euclidienne. Il stipule que dans un triangle rectangle, le carré de "
        "l'hypoténuse (le côté opposé à l'angle droit) est égal à la somme des "
        "carrés des deux autres côtés. Ce théorème est nommé d'après Pythagore "
        "de Samos, mathématicien et philosophe grec de l'Antiquité. "
        "Il existe plusieurs centaines de démonstrations de ce théorème, "
        "ce qui lui confère une place particulière dans l'histoire des mathématiques. "
        "En pratique, le théorème de Pythagore permet de calculer la longueur "
        "d'un côté d'un triangle rectangle connaissant les deux autres. "
        "Par exemple, si un triangle a des côtés de longueur 3 et 4, "
        "l'hypoténuse mesurera 5 (car 3² + 4² = 9 + 16 = 25 = 5²)."
    )


@pytest.fixture
def reindexer_module():
    """Retourne le module reindexer (sans dépendance Supabase)."""
    from core import reindexer
    return reindexer
