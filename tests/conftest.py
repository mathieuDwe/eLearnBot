"""Fixtures partagées pour tous les tests eLearnBot."""

import importlib
import os
import shutil
import sys
import tempfile

import pytest

# Ajouter src/ au PYTHONPATH
_SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, os.path.abspath(_SRC_DIR))

# Désactiver Supabase pour les tests
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_KEY"] = ""


@pytest.fixture
def tmp_data_dir():
    """Crée un répertoire data temporaire isolé pour chaque test.

    Nettoie automatiquement après le test.
    Surcharge DATA_DIR et recharge document_store pour éviter les caches.
    """
    tmpdir = tempfile.mkdtemp()
    old_data_dir = os.environ.get("DATA_DIR")
    os.environ["DATA_DIR"] = tmpdir

    # Recharger pour prendre en compte le nouveau DATA_DIR
    from core import document_store
    importlib.reload(document_store)

    yield tmpdir

    # Nettoyage
    shutil.rmtree(tmpdir, ignore_errors=True)
    if old_data_dir:
        os.environ["DATA_DIR"] = old_data_dir
    else:
        os.environ.pop("DATA_DIR", None)


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
def empty_doc_store(tmp_data_dir):
    """Retourne le module document_store avec un data_dir vide."""
    from core import document_store
    return document_store


@pytest.fixture
def reindexer_module():
    """Retourne le module reindexer (sans dépendance Supabase)."""
    from core import reindexer
    return reindexer
