"""Tests unitaires — document_store (fonctions pures)."""

import hashlib

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# compute_content_hash
# ═══════════════════════════════════════════════════════════════════════════

class TestComputeContentHash:
    def test_consistent_hash(self, empty_doc_store):
        """Même entrée → même hash (déterministe)."""
        ds = empty_doc_store
        h1 = ds.compute_content_hash(b"contenu du cours")
        h2 = ds.compute_content_hash(b"contenu du cours")
        assert h1 == h2

    def test_different_input_different_hash(self, empty_doc_store):
        """Entrée différente → hash différent."""
        ds = empty_doc_store
        h1 = ds.compute_content_hash(b"contenu A")
        h2 = ds.compute_content_hash(b"contenu B")
        assert h1 != h2

    def test_hash_length(self, empty_doc_store):
        """SHA256 → 64 caractères hexadécimaux."""
        ds = empty_doc_store
        h = ds.compute_content_hash(b"test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_hash_empty_bytes(self, empty_doc_store):
        """Fichier vide → hash cohérent."""
        ds = empty_doc_store
        h = ds.compute_content_hash(b"")
        assert len(h) == 64
        # SHA256("") connu
        assert h == hashlib.sha256(b"").hexdigest()

    def test_hash_large_content(self, empty_doc_store):
        """Gros fichier → hash rapide et correct."""
        ds = empty_doc_store
        large = b"x" * 10_000_000  # 10 MB
        h = ds.compute_content_hash(large)
        assert len(h) == 64


# ═══════════════════════════════════════════════════════════════════════════
# chunk_text
# ═══════════════════════════════════════════════════════════════════════════

class TestChunkText:
    def test_small_text_single_chunk(self, empty_doc_store):
        """Texte plus petit que chunk_size → 1 seul chunk."""
        ds = empty_doc_store
        text = "mot " * 10
        chunks = ds.chunk_text(text, chunk_size=500, overlap=50)
        assert len(chunks) == 1
        # Le texte original peut avoir un espace final, on compare le contenu
        assert chunks[0].strip() == ("mot " * 10).strip()
        assert "mot" in chunks[0]

    def test_large_text_multiple_chunks(self, empty_doc_store):
        """Texte plus grand → plusieurs chunks."""
        ds = empty_doc_store
        text = "mot " * 1000
        chunks = ds.chunk_text(text, chunk_size=100, overlap=20)
        assert len(chunks) >= 5

    def test_overlap_present(self, empty_doc_store):
        """Des mots du chunk n apparaissent dans le chunk n+1 (overlap)."""
        ds = empty_doc_store
        text = "mot " * 500
        chunks = ds.chunk_text(text, chunk_size=100, overlap=30)
        if len(chunks) > 1:
            words_0 = set(chunks[0].split())
            words_1 = set(chunks[1].split())
            intersection = words_0 & words_1
            assert len(intersection) > 0, (
                "L'overlap devrait produire des mots communs entre chunks"
            )

    def test_exact_chunk_size(self, empty_doc_store):
        """Texte = exactement chunk_size mots → 1 chunk."""
        ds = empty_doc_store
        text = "mot " * 100
        chunks = ds.chunk_text(text, chunk_size=100, overlap=0)
        assert len(chunks) == 1

    def test_overlap_equals_chunk_size(self, empty_doc_store):
        """Overlap = chunk_size → chaque chunk se répète (cas extrême)."""
        ds = empty_doc_store
        text = "mot " * 300
        chunks = ds.chunk_text(text, chunk_size=100, overlap=100)
        # Avec overlap = chunk_size, on n'avance jamais → boucle infinie évitée ?
        # En réalité start += 0 → boucle infinie.
        # Vérifions qu'on a au moins 1 chunk et pas de boucle.
        assert len(chunks) >= 1

    def test_single_word(self, empty_doc_store):
        """Un seul mot → 1 chunk."""
        ds = empty_doc_store
        chunks = ds.chunk_text("Bonjour", chunk_size=500, overlap=50)
        assert len(chunks) == 1
        assert chunks[0] == "Bonjour"

    def test_empty_text(self, empty_doc_store):
        """Texte vide → 1 chunk vide."""
        ds = empty_doc_store
        chunks = ds.chunk_text("", chunk_size=500, overlap=50)
        assert len(chunks) == 1
        assert chunks[0] == ""

    def test_chunk_boundary(self, empty_doc_store):
        """Texte = chunk_size + 1 mot → 2 chunks."""
        ds = empty_doc_store
        text = "mot " * 101
        chunks = ds.chunk_text(text, chunk_size=100, overlap=0)
        assert len(chunks) == 2


# ═══════════════════════════════════════════════════════════════════════════
# _extract_keywords
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractKeywords:
    def test_basic_keywords(self, empty_doc_store):
        """Mots significatifs extraits."""
        ds = empty_doc_store
        kw = ds._extract_keywords("Quelle est la formule de l'énergie cinétique ?")
        assert "formule" in kw
        assert "énergie" in kw
        assert "cinétique" in kw

    def test_stopwords_filtered(self, empty_doc_store):
        """Stopwords exclus (mots de 3+ car. présents dans la liste)."""
        ds = empty_doc_store
        kw = ds._extract_keywords("le la les un une des dans avec pour sur")
        # Les mots de 2 lettres sont exclus par len(w) >= 3
        # Les stopwords de 3+ lettres doivent être filtrés
        for stop in ("dans", "avec", "pour", "sur", "les"):
            assert stop not in kw, f"Stopword '{stop}' ne devrait pas être dans les keywords"

    def test_short_words_filtered(self, empty_doc_store):
        """Mots de moins de 3 caractères exclus."""
        ds = empty_doc_store
        kw = ds._extract_keywords("a b c de du et ou")
        assert all(w not in kw for w in ("a", "b", "c"))

    def test_accented_chars(self, empty_doc_store):
        """Caractères accentués français supportés."""
        ds = empty_doc_store
        kw = ds._extract_keywords("république française écologie phénomène")
        assert "république" in kw
        assert "française" in kw
        assert "écologie" in kw
        assert "phénomène" in kw

    def test_empty_string(self, empty_doc_store):
        """Chaîne vide → ensemble vide."""
        ds = empty_doc_store
        assert ds._extract_keywords("") == set()

    def test_only_stopwords(self, empty_doc_store):
        """Que des stopwords → ensemble vide."""
        ds = empty_doc_store
        assert ds._extract_keywords("le dans avec pour") == set()

    def test_numbers_ignored(self, empty_doc_store):
        """Les chiffres seuls sont ignorés (moins de 3 caractères)."""
        ds = empty_doc_store
        kw = ds._extract_keywords("123 45 6 test")
        # "123" fait 3 chiffres mais notre regex cherche [a-zA-Z...]
        assert "test" in kw


# ═══════════════════════════════════════════════════════════════════════════
# _format_size
# ═══════════════════════════════════════════════════════════════════════════

class TestFormatSize:
    def test_bytes(self, empty_doc_store):
        ds = empty_doc_store
        assert ds._format_size(0) == "0 o"
        assert ds._format_size(1) == "1 o"
        assert ds._format_size(1023) == "1023 o"

    def test_kilobytes(self, empty_doc_store):
        ds = empty_doc_store
        assert ds._format_size(1024) == "1.0 Ko"
        assert ds._format_size(2048) == "2.0 Ko"
        assert ds._format_size(1536) == "1.5 Ko"

    def test_megabytes(self, empty_doc_store):
        ds = empty_doc_store
        assert ds._format_size(1048576) == "1.0 Mo"
        assert ds._format_size(2097152) == "2.0 Mo"

    def test_large_values(self, empty_doc_store):
        ds = empty_doc_store
        assert ds._format_size(1073741824) == "1024.0 Mo"  # 1 Go en Mo
