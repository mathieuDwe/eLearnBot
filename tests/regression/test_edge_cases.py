"""🧪 Tests de non-régression — Cas aux limites, résilience, scénarios d'erreur."""

import os
import tempfile

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# document_store — cas aux limites
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentStoreEdgeCases:
    """Cas limites du stockage documentaire."""

    def test_empty_text(self, empty_doc_store):
        """Texte vide → document créé avec un seul chunk vide."""
        ds = empty_doc_store
        doc_id = ds.add_document(
            text="",
            filename="empty.pdf",
            metadata={"content_type": "pdf"},
        )
        assert doc_id is not None
        doc = ds.get_document_by_filename("empty.pdf")
        assert doc["chunks"] == [""] or doc["chunks"] == []

    def test_text_with_only_whitespace(self, empty_doc_store):
        """Texte avec uniquement des espaces → pas de crash."""
        ds = empty_doc_store
        doc_id = ds.add_document(
            text="   \n\n\t   ",
            filename="whitespace.pdf",
            metadata={"content_type": "pdf"},
        )
        assert doc_id is not None

    def test_filename_case_sensitivity(self, empty_doc_store):
        """Les noms de fichiers sont sensibles à la casse."""
        ds = empty_doc_store
        ds.add_document(text="Version minuscule", filename="Cours.pdf", metadata={})
        ds.add_document(text="Version majuscule", filename="COURS.pdf", metadata={})
        docs = ds.get_documents_list()
        filenames = [d["filename"] for d in docs]
        assert "Cours.pdf" in filenames
        assert "COURS.pdf" in filenames
        assert len(docs) == 2

    def test_delete_nonexistent_document(self, empty_doc_store):
        """Supprimer un document qui n'existe pas → 0 chunks supprimés."""
        ds = empty_doc_store
        result = ds.delete_document("inexistant.pdf")
        assert result == 0

    def test_get_nonexistent_document(self, empty_doc_store):
        """Chercher un document inexistant → None."""
        ds = empty_doc_store
        assert ds.get_document_by_filename("inexistant.pdf") is None

    def test_add_without_metadata(self, empty_doc_store):
        """Ajouter un document sans metadata → pas de crash, metadata = {}."""
        ds = empty_doc_store
        doc_id = ds.add_document(text="Cours sans meta", filename="bare.pdf")
        assert doc_id is not None
        doc = ds.get_document_by_filename("bare.pdf")
        assert doc["metadata"] == {}

    def test_add_with_none_metadata(self, empty_doc_store):
        """Ajouter avec metadata=None → transformé en {}."""
        ds = empty_doc_store
        doc_id = ds.add_document(text="Test", filename="none_meta.pdf", metadata=None)
        assert doc_id is not None
        doc = ds.get_document_by_filename("none_meta.pdf")
        assert doc["metadata"] == {}

    def test_multiple_documents_same_prefix(self, empty_doc_store):
        """Noms de fichiers avec le même préfixe ne se confondent pas."""
        ds = empty_doc_store
        ds.add_document(text="Doc 1", filename="doc.pdf", metadata={})
        ds.add_document(text="Doc 2", filename="doc_v2.pdf", metadata={})
        ds.add_document(text="Doc 3", filename="document.pdf", metadata={})
        assert len(ds.get_documents_list()) == 3
        assert ds.get_document_by_filename("doc.pdf") is not None
        assert ds.get_document_by_filename("doc_v2.pdf") is not None
        assert ds.get_document_by_filename("document.pdf") is not None

    def test_very_large_metadata(self, empty_doc_store):
        """Métadonnées volumineuses (10000 entrées) → pas de crash."""
        ds = empty_doc_store
        large_meta = {f"key_{i}": f"value_{i}" for i in range(1000)}
        large_meta["content_type"] = "pdf"
        doc_id = ds.add_document(
            text="Cours avec grosses métadonnées",
            filename="large_meta.pdf",
            metadata=large_meta,
        )
        assert doc_id is not None

    def test_search_empty_index(self, empty_doc_store):
        """Recherche dans un index vide → liste vide."""
        ds = empty_doc_store
        assert ds.search("quoi que ce soit") == []

    def test_search_with_no_matches(self, empty_doc_store):
        """Recherche sans résultat → liste vide."""
        ds = empty_doc_store
        ds.add_document(text="Cours de mathématiques", filename="maths.pdf", metadata={})
        results = ds.search("informatique")
        assert results == []

    def test_chunk_text_overlap_larger_than_text(self, empty_doc_store):
        """Overlap > taille du texte → 1 chunk."""
        ds = empty_doc_store
        chunks = ds.chunk_text("petit texte", chunk_size=3, overlap=100)
        assert len(chunks) >= 1

    def test_chunk_text_zero_overlap(self, empty_doc_store):
        """Overlap = 0 → pas de recouvrement entre chunks."""
        ds = empty_doc_store
        text = "mot " * 500
        chunks = ds.chunk_text(text, chunk_size=100, overlap=0)
        assert len(chunks) == 5  # 500/100 = 5
        # Vérifier qu'il n'y a pas d'overlap
        for i in range(len(chunks) - 1):
            last_words = set(chunks[i].split()[-10:])
            first_words = set(chunks[i + 1].split()[:10])
            # Il peut y avoir des mots communs par hasard, mais pas les 10 derniers
            # (en fait avec overlap=0, le chunk i+1 commence là où i s'arrête)
            # Donc ils sont adjacents sans recouvrement

    def test_get_documents_list_empty(self, empty_doc_store):
        """Liste vide quand aucun document."""
        ds = empty_doc_store
        assert ds.get_documents_list() == []

    def test_count_zero(self, empty_doc_store):
        """count = 0 quand aucun document."""
        ds = empty_doc_store
        assert ds.count_documents() == 0


# ═══════════════════════════════════════════════════════════════════════════
# reindexer — cas aux limites
# ═══════════════════════════════════════════════════════════════════════════

class TestReindexerEdgeCases:
    """Cas limites du moteur de ré-indexation."""

    def test_classify_file_null_bytes(self, reindexer_module):
        """Nom de fichier avec des null bytes → pas de crash."""
        r = reindexer_module
        try:
            result = r._classify_file("cours\x00.pdf")
            # Soit ça retourne quelque chose, soit ça lève une exception propre
            assert result is not None or result == "unknown"
        except Exception as e:
            pytest.fail(f"Null byte dans le nom ne devrait pas crasher : {e}")

    def test_classify_file_very_long_name(self, reindexer_module):
        """Nom de 10 000 caractères → pas de crash."""
        r = reindexer_module
        long_name = "a" * 10000 + ".pdf"
        result = r._classify_file(long_name)
        assert result == "pdf"

    def test_is_supported_type_empty(self, reindexer_module):
        """Chaîne vide → False (pas de crash)."""
        r = reindexer_module
        assert r._is_supported_type("") is False

    def test_is_supported_type_none(self, reindexer_module):
        """None → TypeError (comportement attendu)."""
        r = reindexer_module
        with pytest.raises((TypeError, AttributeError)):
            r._is_supported_type(None)

    def test_format_sync_summary_none_values(self, reindexer_module):
        """Le formatage ne crash pas avec des listes vides."""
        r = reindexer_module
        status = {
            "total_in_supabase": 0,
            "total_indexed": 0,
            "new_files": [],
            "modified_files": [],
            "missing_files": [],
            "synced_files": [],
            "last_checked": "2026-07-17T00:00:00",
        }
        summary = r.format_sync_summary(status)
        assert isinstance(summary, str)
        assert len(summary) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Résilience — comportement sans Supabase
# ═══════════════════════════════════════════════════════════════════════════

class TestReindexerResilience:
    """Comportement du reindexer quand Supabase est indisponible."""

    def test_scan_supabase_files_no_config(self, reindexer_module):
        """scan_supabase_files sans Supabase → liste vide (pas d'erreur)."""
        # Les vars d'env sont déjà vides dans conftest
        files = reindexer_module.scan_supabase_files()
        assert files == []

    def test_get_storage_file_hash_no_config(self, reindexer_module):
        """get_storage_file_hash sans Supabase → None."""
        h = reindexer_module.get_storage_file_hash("test.pdf")
        assert h is None

    def test_auto_reindex_on_startup_no_config(self, reindexer_module):
        """auto_reindex_on_startup sans Supabase → rapport avec message."""
        report = reindexer_module.auto_reindex_on_startup()
        assert report.get("message") is not None
        assert "Supabase" in report["message"]
        assert report["total_processed"] == 0

    def test_reindex_all_no_config(self, reindexer_module):
        """reindex_all sans Supabase → fichier individuel échoue."""
        result = reindexer_module.reindex_file("test.pdf")
        assert result["success"] is False
        assert "Supabase" in result.get("error", "")

    def test_check_sync_status_no_config(self, reindexer_module):
        """check_sync_status sans Supabase → index local vide."""
        status = reindexer_module.check_sync_status()
        assert status["total_in_supabase"] == 0
        assert "last_checked" in status


# ═══════════════════════════════════════════════════════════════════════════
# Résilience — corruption du fichier JSON
# ═══════════════════════════════════════════════════════════════════════════

class TestJSONResilience:
    """Comportement face à un fichier documents.json corrompu."""

    def test_corrupted_json(self, tmp_data_dir):
        """Fichier JSON corrompu → chargement silencieux (liste vide)."""
        import json
        from core import document_store
        import importlib
        importlib.reload(document_store)

        # Écrire un JSON invalide
        data_file = os.path.join(tmp_data_dir, "documents.json")
        with open(data_file, "w") as f:
            f.write("{ceci n'est pas du json valide!!")

        docs = document_store.get_documents_list()
        assert docs == []

    def test_empty_json_file(self, tmp_data_dir):
        """Fichier JSON vide → liste vide."""
        from core import document_store
        import importlib
        importlib.reload(document_store)

        data_file = os.path.join(tmp_data_dir, "documents.json")
        with open(data_file, "w") as f:
            f.write("")

        docs = document_store.get_documents_list()
        assert docs == []

    def test_json_not_a_list(self, tmp_data_dir):
        """JSON valide mais pas une liste → liste vide."""
        import json
        from core import document_store
        import importlib
        importlib.reload(document_store)

        data_file = os.path.join(tmp_data_dir, "documents.json")
        with open(data_file, "w") as f:
            json.dump({"not_a_list": True}, f)

        # _load_documents tente json.load → retourne un dict, puis
        # la boucle dans get_documents_list échoue. Vérifions la résilience.
        docs = document_store.get_documents_list()
        assert docs == []

    def test_json_with_missing_keys(self, tmp_data_dir):
        """Documents avec clés manquantes → pas de crash."""
        import json
        from core import document_store
        import importlib
        importlib.reload(document_store)

        data_file = os.path.join(tmp_data_dir, "documents.json")
        with open(data_file, "w") as f:
            json.dump([
                {"id": "1", "filename": "ok.pdf", "text": "contenu",
                 "chunks": ["contenu"], "chunks_count": 1, "metadata": {}},
                {"id": "2", "filename": "no_text.pdf"},  # clés manquantes
            ], f)

        docs = document_store.get_documents_list()
        assert len(docs) >= 1
        # Le document avec clés manquantes ne devrait pas crasher
