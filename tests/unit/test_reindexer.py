"""Tests unitaires — reindexer (fonctions pures sans Supabase)."""

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# _classify_file
# ═══════════════════════════════════════════════════════════════════════════

class TestClassifyFile:
    def test_pdf_extension(self, reindexer_module):
        r = reindexer_module
        assert r._classify_file("cours.pdf") == "pdf"
        assert r._classify_file("maths.PDF") == "pdf"
        assert r._classify_file("chemin/vers/document.Pdf") == "pdf"

    def test_mp4_extension(self, reindexer_module):
        r = reindexer_module
        assert r._classify_file("video.mp4") == "mp4"
        assert r._classify_file("lecon.MP4") == "mp4"
        assert r._classify_file("sous/dossier/video.Mp4") == "mp4"

    def test_unknown_extension(self, reindexer_module):
        r = reindexer_module
        assert r._classify_file("image.png") == "unknown"
        assert r._classify_file("document.txt") == "unknown"
        assert r._classify_file("archive.zip") == "unknown"
        assert r._classify_file("README.md") == "unknown"

    def test_no_extension(self, reindexer_module):
        r = reindexer_module
        assert r._classify_file("fichier_sans_extension") == "unknown"
        assert r._classify_file("") == "unknown"
        assert r._classify_file(".") == "unknown"

    def test_dotted_filename(self, reindexer_module):
        r = reindexer_module
        assert r._classify_file(".hidden.pdf") == "pdf"
        assert r._classify_file(".gitkeep") == "unknown"

    def test_with_full_path(self, reindexer_module):
        r = reindexer_module
        path = "/home/user/documents/cours/mathematiques/chapitre1.pdf"
        assert r._classify_file(path) == "pdf"
        path2 = "C:\\Users\\prof\\videos\\lecon.mp4"
        assert r._classify_file(path2) == "mp4"


# ═══════════════════════════════════════════════════════════════════════════
# _is_supported_type
# ═══════════════════════════════════════════════════════════════════════════

class TestIsSupportedType:
    def test_pdf_supported(self, reindexer_module):
        r = reindexer_module
        assert r._is_supported_type("cours.pdf") is True
        assert r._is_supported_type("chemin/document.PDF") is True

    def test_mp4_supported(self, reindexer_module):
        r = reindexer_module
        assert r._is_supported_type("video.mp4") is True
        assert r._is_supported_type("dossier/lecon.MP4") is True

    def test_unsupported_types(self, reindexer_module):
        r = reindexer_module
        assert r._is_supported_type("image.png") is False
        assert r._is_supported_type("document.txt") is False
        assert r._is_supported_type("archive.zip") is False
        assert r._is_supported_type("fichier") is False
        assert r._is_supported_type("") is False


# ═══════════════════════════════════════════════════════════════════════════
# format_sync_summary
# ═══════════════════════════════════════════════════════════════════════════

class TestFormatSyncSummary:
    def test_empty(self, reindexer_module):
        r = reindexer_module
        status = {
            "total_in_supabase": 0,
            "total_indexed": 0,
            "new_files": [],
            "modified_files": [],
            "missing_files": [],
            "synced_files": [],
            "last_checked": "2026-07-17T12:00:00",
        }
        summary = r.format_sync_summary(status)
        assert "0 fichier(s) dans Supabase" in summary
        assert "0 document(s)" in summary

    def test_all_synced(self, reindexer_module):
        r = reindexer_module
        status = {
            "total_in_supabase": 5,
            "total_indexed": 5,
            "new_files": [],
            "modified_files": [],
            "missing_files": [],
            "synced_files": ["a.pdf", "b.pdf", "c.pdf", "d.mp4", "e.pdf"],
            "last_checked": "2026-07-17T12:00:00",
        }
        summary = r.format_sync_summary(status)
        assert "5 fichier(s) dans Supabase" in summary
        assert "5 document(s)" in summary
        assert "5 fichier(s) à jour" in summary

    def test_with_new_files(self, reindexer_module):
        r = reindexer_module
        status = {
            "total_in_supabase": 6,
            "total_indexed": 4,
            "new_files": [
                {"name": "nouv1.pdf"},
                {"name": "nouv2.mp4"},
            ],
            "modified_files": [],
            "missing_files": [],
            "synced_files": ["a.pdf", "b.pdf", "c.pdf", "d.mp4"],
            "last_checked": "2026-07-17T12:00:00",
        }
        summary = r.format_sync_summary(status)
        assert "6 fichier(s) dans Supabase" in summary
        assert "4 document(s)" in summary
        assert "2 nouveau(x) à indexer" in summary
        assert "4 fichier(s) à jour" in summary

    def test_with_modified_files(self, reindexer_module):
        r = reindexer_module
        status = {
            "total_in_supabase": 4,
            "total_indexed": 4,
            "new_files": [],
            "modified_files": [{"name": "mod.pdf"}],
            "missing_files": [],
            "synced_files": ["a.pdf", "b.pdf", "c.mp4"],
            "last_checked": "2026-07-17T12:00:00",
        }
        summary = r.format_sync_summary(status)
        assert "1 fichier(s) modifié(s)" in summary

    def test_with_missing_files(self, reindexer_module):
        r = reindexer_module
        status = {
            "total_in_supabase": 3,
            "total_indexed": 5,
            "new_files": [],
            "modified_files": [],
            "missing_files": ["old1.pdf", "old2.mp4"],
            "synced_files": ["a.pdf", "b.pdf", "c.mp4"],
            "last_checked": "2026-07-17T12:00:00",
        }
        summary = r.format_sync_summary(status)
        assert "2 fichier(s) manquant(s)" in summary

    def test_with_all_changes(self, reindexer_module):
        r = reindexer_module
        status = {
            "total_in_supabase": 10,
            "total_indexed": 8,
            "new_files": [{"name": "new.pdf"}],
            "modified_files": [{"name": "mod.pdf"}],
            "missing_files": ["del.pdf"],
            "synced_files": ["a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf"],
            "last_checked": "2026-07-17T12:00:00",
        }
        summary = r.format_sync_summary(status)
        assert "10 fichier(s) dans Supabase" in summary
        assert "8 document(s)" in summary
        assert "1 nouveau(x)" in summary
        assert "1 fichier(s) modifié(s)" in summary
        assert "1 fichier(s) manquant(s)" in summary
        assert "5 fichier(s) à jour" in summary

    def test_zero_counts(self, reindexer_module):
        """Aucun fichier nulle part."""
        r = reindexer_module
        status = {
            "total_in_supabase": 0,
            "total_indexed": 0,
            "new_files": [],
            "modified_files": [],
            "missing_files": [],
            "synced_files": [],
            "last_checked": "2026-07-17T12:00:00",
        }
        summary = r.format_sync_summary(status)
        assert "0 fichier(s) dans Supabase" in summary
        assert "0 document(s)" in summary
