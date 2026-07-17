"""🧪 Tests fonctionnels — Workflows complets du document_store et reindexer."""

import os
import tempfile

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# Workflows document_store
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentWorkflows:
    """Workflows CRUD complets sur les documents."""

    def test_add_then_search_workflow(self, empty_doc_store, sample_text):
        """Ajouter un document → le rechercher → résultats pertinents."""
        ds = empty_doc_store
        ds.add_document(
            text=sample_text,
            filename="pythagore.pdf",
            metadata={"content_type": "pdf", "size": 1024},
        )
        results = ds.search("théorème Pythagore hypoténuse")
        assert len(results) > 0
        best = results[0]
        assert "Pythagore" in best["text"]
        assert best["score"] > 0
        assert best["metadata"]["filename"] == "pythagore.pdf"

    def test_add_then_get_workflow(self, empty_doc_store):
        """Ajouter → récupérer par nom → infos correctes."""
        ds = empty_doc_store
        ds.add_document(
            text="Cours de physique quantique.",
            filename="physique.pdf",
            metadata={"content_type": "pdf", "auteur": "Einstein"},
        )
        doc = ds.get_document_by_filename("physique.pdf")
        assert doc is not None
        assert doc["filename"] == "physique.pdf"
        assert "physique quantique" in doc["text"]
        assert doc["metadata"]["auteur"] == "Einstein"
        assert doc["chunks_count"] >= 1

    def test_add_then_list_workflow(self, empty_doc_store):
        """Ajouter plusieurs docs → les lister → tous présents."""
        ds = empty_doc_store
        ds.add_document(text="Cours A", filename="a.pdf", metadata={})
        ds.add_document(text="Cours B", filename="b.pdf", metadata={})
        ds.add_document(text="Cours C", filename="c.pdf", metadata={})
        docs = ds.get_documents_list()
        assert len(docs) == 3
        filenames = [d["filename"] for d in docs]
        assert "a.pdf" in filenames
        assert "b.pdf" in filenames
        assert "c.pdf" in filenames

    def test_update_then_search_workflow(self, empty_doc_store):
        """Mettre à jour un document → la recherche trouve la nouvelle version."""
        ds = empty_doc_store
        ds.add_document(
            text="Ancienne version du cours.",
            filename="cours.pdf",
            metadata={"version": 1},
        )
        ds.add_document(
            text="Nouvelle version du cours avec plus de contenu.",
            filename="cours.pdf",
            metadata={"version": 2},
        )
        results = ds.search("Nouvelle version")
        assert len(results) > 0
        assert "Nouvelle" in results[0]["text"]
        # L'ancienne version ne devrait plus être trouvable
        doc = ds.get_document_by_filename("cours.pdf")
        assert doc["metadata"]["version"] == 2

    def test_delete_then_search_workflow(self, empty_doc_store):
        """Supprimer un document → plus trouvable dans les résultats."""
        ds = empty_doc_store
        ds.add_document(text="À supprimer", filename="delete_me.pdf", metadata={})
        assert len(ds.get_documents_list()) == 1
        ds.delete_document("delete_me.pdf")
        assert len(ds.get_documents_list()) == 0
        results = ds.search("supprimer")
        assert len(results) == 0

    def test_search_specific_document(self, empty_doc_store, sample_text):
        """Recherche filtrée sur un document spécifique."""
        ds = empty_doc_store
        ds.add_document(text=sample_text, filename="pythagore.pdf", metadata={})
        ds.add_document(text="Cours de biologie sur la photosynthèse.",
                        filename="biologie.pdf", metadata={})
        results = ds.search("photosynthèse", document_name="biologie.pdf")
        assert len(results) > 0
        assert "photosynthèse" in results[0]["text"]
        # Pas de résultats dans l'autre doc
        results2 = ds.search("photosynthèse", document_name="pythagore.pdf")
        assert len(results2) == 0

    def test_add_with_content_hash_workflow(self, empty_doc_store):
        """Workflow complet avec content_hash."""
        ds = empty_doc_store
        original_hash = ds.compute_content_hash(b"contenu du fichier PDF")
        doc_id = ds.add_document(
            text="Contenu extrait du PDF.",
            filename="cours_hash.pdf",
            metadata={"content_type": "pdf", "size": 2048},
            content_hash=original_hash,
        )
        doc = ds.get_document_by_filename("cours_hash.pdf")
        assert doc["metadata"]["content_hash"] == original_hash
        assert doc["metadata"]["hash_algorithm"] == "sha256"
        # Vérifier que le hash est aussi exposé en haut niveau
        docs_list = ds.get_documents_list()
        matching = [d for d in docs_list if d["filename"] == "cours_hash.pdf"]
        assert len(matching) == 1
        assert matching[0]["content_hash"] == original_hash


# ═══════════════════════════════════════════════════════════════════════════
# Workflows reindexer
# ═══════════════════════════════════════════════════════════════════════════

class TestReindexerWorkflows:
    """Workflows de ré-indexation sans Supabase (tests unitaires)."""

    def test_classify_all_types_workflow(self, reindexer_module):
        """Classifier un lot de fichiers → tous corrects."""
        r = reindexer_module
        test_files = [
            ("cours.pdf", "pdf"),
            ("video.mp4", "mp4"),
            ("image.png", "unknown"),
            ("notes.txt", "unknown"),
            ("archive.tar.gz", "unknown"),
        ]
        for fname, expected in test_files:
            assert r._classify_file(fname) == expected
            if expected in ("pdf", "mp4"):
                assert r._is_supported_type(fname) is True
            else:
                assert r._is_supported_type(fname) is False

    def test_format_sync_report_workflow(self, reindexer_module):
        """Générer un rapport de synchro → formaté correctement."""
        r = reindexer_module
        status = {
            "total_in_supabase": 10,
            "total_indexed": 7,
            "new_files": [{"name": "new1.pdf"}, {"name": "new2.mp4"}],
            "modified_files": [{"name": "mod1.pdf"}],
            "missing_files": ["old1.pdf"],
            "synced_files": ["a.pdf", "b.pdf", "c.pdf", "d.mp4", "e.pdf",
                             "f.pdf", "g.mp4"],
            "last_checked": "2026-07-17T14:30:00",
        }
        summary = r.format_sync_summary(status)
        assert "10" in summary
        assert "7" in summary
        assert "2 nouveau(x)" in summary
        assert "1 fichier(s) modifié(s)" in summary
        assert "1 fichier(s) manquant(s)" in summary


# ═══════════════════════════════════════════════════════════════════════════
# Workflows intégrés document_store + reindexer
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegratedWorkflows:
    """Scénarios complets utilisant document_store ET reindexer."""

    def test_sync_status_empty_index(self, empty_doc_store, reindexer_module):
        """Index vide, Supabase vide → tout à 0, pas d'erreur."""
        # Simule Supabase vide (scan_supabase_files retourne [])
        original_scan = reindexer_module.scan_supabase_files
        reindexer_module.scan_supabase_files = lambda: []
        try:
            status = reindexer_module.check_sync_status()
            assert status["total_in_supabase"] == 0
            assert status["total_indexed"] == 0
            assert status["new_files"] == []
            assert status["modified_files"] == []
            assert status["missing_files"] == []
        finally:
            reindexer_module.scan_supabase_files = original_scan

    def test_sync_status_detects_new_files(self, empty_doc_store, reindexer_module):
        """Fichier dans Supabase mais pas dans l'index → détecté comme nouveau."""
        original_scan = reindexer_module.scan_supabase_files
        reindexer_module.scan_supabase_files = lambda: [
            {"name": "new_cours.pdf", "size": 2048, "updated_at": "2026-07-17T10:00:00",
             "id": "1"},
            {"name": "synced.pdf", "size": 1024, "updated_at": "2026-07-16T10:00:00",
             "id": "2"},
        ]
        # Ajouter un document déjà indexé
        empty_doc_store.add_document(
            text="Déjà indexé",
            filename="synced.pdf",
            metadata={"content_hash": "aaa"},
        )
        # Et un document sans hash à mettre à jour
        empty_doc_store.add_document(
            text="Ancien sans hash",
            filename="old_no_hash.pdf",
            metadata={},
        )
        try:
            status = reindexer_module.check_sync_status()
            assert status["total_in_supabase"] == 2
            assert status["total_indexed"] == 2
            # new_cours.pdf est nouveau
            new_names = [f["name"] for f in status["new_files"]]
            assert "new_cours.pdf" in new_names
            # old_no_hash.pdf est dans l'index mais pas dans Supabase
            assert "old_no_hash.pdf" in status["missing_files"]
        finally:
            reindexer_module.scan_supabase_files = original_scan
