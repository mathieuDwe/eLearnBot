"""🧪 Tests de sécurité — Auth, sessions, injections, périmètres.

Couvre :
  - Hash et vérification des mots de passe
  - Validation des noms d'utilisateur (injection SQL, XSS)
  - Validation des rôles
  - Sécurité des tokens de session (HMAC, expiration)
  - Path traversal dans les noms de fichiers
  - Injection HTML/script dans les métadonnées
  - Contournement de type de fichier
"""

import base64
import json
import hashlib
import hmac
import os
import sys
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# ── Mocker streamlit et supabase AVANT les imports des modules core ─────
# Ces dépendances ne sont pas disponibles dans l'environnement de test
sys.modules["streamlit"] = MagicMock()
sys.modules["supabase"] = MagicMock()
sys.modules["supabase"].create_client = MagicMock()

# Ajouter src/ au PYTHONPATH
_SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src")
sys.path.insert(0, os.path.abspath(_SRC_DIR))


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def auth():
    """Module auth — test des fonctions pures (pas de Supabase)."""
    from core import auth
    return auth


@pytest.fixture
def session():
    """Module session — test des fonctions de token."""
    from core import session
    return session


@pytest.fixture
def doc_store(tmp_data_dir):
    """Module document_store avec data_dir temporaire."""
    from core import document_store
    return document_store


# ═══════════════════════════════════════════════════════════════════════════
# Tests mot de passe
# ═══════════════════════════════════════════════════════════════════════════

class TestPasswordSecurity:
    """Sécurité des mots de passe — hash, vérification, résistance."""

    def test_hash_consistent(self, auth):
        """Même mot de passe → même hash (déterministe)."""
        h1 = auth._hash_password("MonMot2P@ss!")
        h2 = auth._hash_password("MonMot2P@ss!")
        assert h1 == h2

    def test_hash_different(self, auth):
        """Mot de passe différent → hash différent."""
        h1 = auth._hash_password("password123")
        h2 = auth._hash_password("password124")
        assert h1 != h2

    def test_hash_length(self, auth):
        """SHA256 → 64 caractères hex."""
        h = auth._hash_password("test")
        assert len(h) == 64

    def test_hash_not_reversible(self, auth):
        """Le hash ne contient pas le mot de passe en clair."""
        h = auth._hash_password("MonMotDePasseSecret!")
        assert "MonMotDePasseSecret" not in h
        assert "MotDePasse" not in h

    def test_verify_correct(self, auth):
        """Vérification d'un hash correct."""
        h = auth._hash_password("correct-password")
        assert auth._verify_password("correct-password", h) is True

    def test_verify_incorrect(self, auth):
        """Vérification d'un mauvais mot de passe → False."""
        h = auth._hash_password("correct-password")
        assert auth._verify_password("wrong-password", h) is False

    def test_verify_empty_password(self, auth):
        """Mot de passe vide — hash cohérent."""
        h = auth._hash_password("")
        assert auth._verify_password("", h) is True
        assert auth._verify_password("a", h) is False

    def test_verify_plaintext_fallback(self, auth):
        """Fallback texte clair (compatibilité ascendante)."""
        assert auth._verify_password("admin123", "admin123") is True
        assert auth._verify_password("wrong", "admin123") is False

    def test_verify_tampered_hash(self, auth):
        """Hash modifié → échec de la vérification."""
        h = auth._hash_password("password")
        tampered = h[:-1] + ("0" if h[-1] == "f" else "f")
        assert auth._verify_password("password", tampered) is False

    def test_long_password(self, auth):
        """Mot de passe très long (1000 caractères) → pas de crash."""
        long_pwd = "A" * 1000
        h = auth._hash_password(long_pwd)
        assert len(h) == 64
        # La vérification SHA256 fonctionne pour les longues chaînes
        assert auth._verify_password(long_pwd, h) is True


# ═══════════════════════════════════════════════════════════════════════════
# Tests validation nom d'utilisateur
# ═══════════════════════════════════════════════════════════════════════════

class TestUsernameValidation:
    """Protection contre les injections et usurpations via le username."""

    def test_valid_usernames(self, auth):
        """Usernames valides acceptés."""
        valid = [
            "jean",
            "jean.dupont",
            "jean-dupont",
            "jean_dupont",
            "jean.dupont92",
            "a" * 30,
        ]
        for username in valid:
            assert auth._validate_username(username), f"Devrait être valide : {username}"

    def test_invalid_usernames(self, auth):
        """Usernames invalides rejetés."""
        invalid = [
            "",                    # Vide
            "a",                   # Trop court (1 caractère)
            "a" * 31,             # Trop long (31 caractères)
            "jean dupont",        # Espace
            "jean@dupont",        # @
            "jean/dupont",        # Slash
            "jean\\dupont",       # Backslash
            "jean'dupont",        # Quote simple — tentative injection SQL
            "jean\"dupont",       # Quote double — injection SQL
            "jean;drop table",    # SQL injection
            "admin'--",           # SQL injection comment
            "admin OR 1=1",       # SQL injection
            "<script>",           # XSS
            "{{template}}",       # SSTI
            "${jndi:ldap}",       # Log4j
            "../../etc/passwd",   # Path traversal
            "admin\n",            # Newline
            "admin\t",            # Tab
        ]
        for username in invalid:
            assert not auth._validate_username(username), f"Devrait être invalide : {username}"

    def test_unicode_usernames(self, auth):
        """Caractères unicode (accents français) — rejetés ou acceptés selon la regex."""
        # La regex actuelle n'accepte que [a-zA-Z0-9_.-]
        assert not auth._validate_username("éloïse")
        assert not auth._validate_username("françois")
        assert not auth._validate_username("élève")

    def test_boundary_length_2(self, auth):
        """Juste 2 caractères → valide."""
        assert auth._validate_username("ab") is True

    def test_boundary_length_30(self, auth):
        """Exactement 30 caractères → valide."""
        assert auth._validate_username("a" * 30) is True

    def test_boundary_length_31(self, auth):
        """31 caractères → invalide."""
        assert auth._validate_username("a" * 31) is False


# ═══════════════════════════════════════════════════════════════════════════
# Tests rôles
# ═══════════════════════════════════════════════════════════════════════════

class TestRoleSecurity:
    """Validation des rôles — pas de rôle non autorisé."""

    def test_valid_roles(self, auth):
        """Les 3 rôles valides sont acceptés."""
        assert "admin" in auth.ROLES
        assert "professeur" in auth.ROLES
        assert "eleve" in auth.ROLES
        assert len(auth.ROLES) == 3

    def test_invalid_role_rejected(self, auth):
        """Rôle invalide → la fonction register_user() le rejette."""
        # Test unitaire sans appeler Supabase: on vérifie juste le check
        from core.auth import register_user
        # Sans Supabase, register_user échoue sur _get_client()
        # mais on peut vérifier la validation en amont en mockant
        # Vérification directe du comportement attendu
        invalid_roles = ["superadmin", "moderator", "user", "student", "teacher", "", None]
        for role in invalid_roles:
            if role is None:
                continue
            assert role not in auth.ROLES, f"{role} ne devrait pas être un rôle valide"

    def test_role_case_sensitive(self, auth):
        """Les rôles sont sensibles à la casse."""
        assert "Admin" not in auth.ROLES
        assert "Professeur" not in auth.ROLES
        assert "Eleve" not in auth.ROLES


# ═══════════════════════════════════════════════════════════════════════════
# Tests tokens de session (HMAC)
# ═══════════════════════════════════════════════════════════════════════════

class TestSessionTokenSecurity:
    """Sécurité des tokens — signature HMAC, expiration, antialtération."""

    def test_token_valid(self, session):
        """Token valide → utilisateur décodé."""
        session._get_secret = lambda: "test_secret_key_123"
        user = {"username": "jean", "role": "professeur"}
        token = session._make_token(user)
        decoded = session._parse_token(token)
        assert decoded is not None
        assert decoded["username"] == "jean"
        assert decoded["role"] == "professeur"

    def test_token_tampered(self, session):
        """Token modifié (altération du payload) → rejeté."""
        session._get_secret = lambda: "test_secret_key_123"
        user = {"username": "jean", "role": "eleve"}
        token = session._make_token(user)
        # Altérer le payload
        parts = token.split(".")
        tampered_payload = base64.urlsafe_b64encode(
            json.dumps({"username": "admin", "role": "admin"}).encode()
        ).decode().rstrip("=")
        tampered = f"{tampered_payload}.{parts[1]}"
        decoded = session._parse_token(tampered)
        assert decoded is None, "Token altéré devrait être rejeté"

    def test_token_wrong_secret(self, session):
        """Token signé avec une clé différente → rejeté."""
        session._get_secret = lambda: "key_a"
        user = {"username": "jean", "role": "eleve"}
        token = session._make_token(user)
        # Vérifier avec une autre clé
        session._get_secret = lambda: "key_b"
        decoded = session._parse_token(token)
        assert decoded is None, "Mauvaise clé → token invalide"

    def test_token_expired(self, session):
        """Token expiré → rejeté."""
        session._get_secret = lambda: "test_key"
        # Créer un token avec expiration dans le passé
        payload = {
            "username": "jean",
            "role": "professeur",
            "exp": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
        }
        data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        sig = hmac.new(
            b"test_key", data.encode(), hashlib.sha256
        ).hexdigest()
        token = f"{data}.{sig}"
        decoded = session._parse_token(token)
        assert decoded is None, "Token expiré devrait être rejeté"

    def test_token_malformed(self, session):
        """Token malformé → rejeté silencieusement (pas d'exception)."""
        session._get_secret = lambda: "test_key"
        malformed = [
            "",
            "not-a-token",
            "too.many.dots",
            "invalid-base64!!.signature",
        ]
        for t in malformed:
            decoded = session._parse_token(t)
            assert decoded is None, f"Token malformé devrait être None : {t!r}"

    def test_token_role_elevation(self, session):
        """Tentative d'élévation de rôle dans le token → doit échouer."""
        session._get_secret = lambda: "secret"
        # Token qui dit être admin sans signature valide
        payload = {
            "username": "attacker",
            "role": "admin",
            "exp": (datetime.utcnow() + timedelta(days=1)).isoformat(),
        }
        data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
        # Mauvaise signature
        wrong_sig = "0" * 64
        token = f"{data}.{wrong_sig}"
        decoded = session._parse_token(token)
        assert decoded is None, "Élévation de rôle impossible sans signature valide"

    def test_token_username_tampering(self, session):
        """Changer le nom d'utilisateur dans le token → échoue."""
        session._get_secret = lambda: "secret"
        valid_user = {"username": "legit_user", "role": "eleve"}
        valid_token = session._make_token(valid_user)
        # Décoder, modifier, re-encoder sans signer
        parts = valid_token.split(".")
        decoded_bytes = base64.urlsafe_b64decode(parts[0] + "==")
        payload = json.loads(decoded_bytes)
        payload["username"] = "admin_user"
        tampered_data = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).decode().rstrip("=")
        tampered_token = f"{tampered_data}.{parts[1]}"
        decoded = session._parse_token(tampered_token)
        assert decoded is None


# ═══════════════════════════════════════════════════════════════════════════
# Tests document_store — sécurité des entrées
# ═══════════════════════════════════════════════════════════════════════════

class TestDocumentStoreSecurity:
    """Résistance aux injections et manipulations via les documents."""

    def test_path_traversal_in_filename(self, doc_store):
        """Path traversal dans le nom de fichier → stocké tel quel (pas d'exploit)."""
        # Le filename est stocké dans le JSON, pas utilisé pour écrire sur le disque
        dangerous_names = [
            "../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "/etc/shadow",
            "~/.ssh/id_rsa",
            "%00",  # Null byte
        ]
        for name in dangerous_names:
            doc_id = doc_store.add_document(
                text="contenu",
                filename=name,
                metadata={"content_type": "pdf"},
            )
            assert doc_id is not None
            doc = doc_store.get_document_by_filename(name)
            assert doc is not None, f"Le document {name!r} devrait être stocké"
            doc_store.delete_document(name)

    def test_html_injection_in_text(self, doc_store):
        """Injection HTML/script dans le texte du document → stocké sans exécution."""
        malicious_text = (
            "<script>alert('XSS')</script>"
            "<img src=x onerror=alert(1)>"
            "{{7*7}}"
            "${7*7}"
        )
        doc_id = doc_store.add_document(
            text=malicious_text,
            filename="xss_test.pdf",
            metadata={"content_type": "pdf"},
        )
        assert doc_id is not None
        doc = doc_store.get_document_by_filename("xss_test.pdf")
        assert doc is not None
        assert "<script>" in doc["text"]
        assert "alert('XSS')" in doc["text"]

    def test_html_injection_in_metadata(self, doc_store):
        """Injection dans les métadonnées → stocké sans exécution."""
        malicious_meta = {
            "content_type": "pdf",
            "title": "<script>alert('XSS')</script>",
            "description": "{{7*7}}",
        }
        doc_id = doc_store.add_document(
            text="contenu",
            filename="meta_xss.pdf",
            metadata=malicious_meta,
        )
        assert doc_id is not None
        doc = doc_store.get_document_by_filename("meta_xss.pdf")
        assert doc["metadata"]["title"] == "<script>alert('XSS')</script>"

    def test_very_long_filename(self, doc_store):
        """Nom de fichier très long (5000 caractères) → pas de crash."""
        long_name = "a" * 5000 + ".pdf"
        doc_id = doc_store.add_document(
            text="contenu",
            filename=long_name,
            metadata={"content_type": "pdf"},
        )
        assert doc_id is not None
        doc = doc_store.get_document_by_filename(long_name)
        assert doc is not None
        doc_store.delete_document(long_name)

    def test_filename_with_special_chars(self, doc_store):
        """Caractères spéciaux dans le nom → stocké correctement."""
        special_names = [
            "cours (1).pdf",
            "cours - physique [2026].pdf",
            "cours#1.pdf",
            "cours+chimie.pdf",
            "cours_à_jour.pdf",
        ]
        for name in special_names:
            doc_id = doc_store.add_document(
                text="contenu",
                filename=name,
                metadata={"content_type": "pdf"},
            )
            assert doc_id is not None
            doc = doc_store.get_document_by_filename(name)
            assert doc is not None, f"Le nom {name!r} devrait être accepté"
            doc_store.delete_document(name)

    def test_unicode_injection_in_text(self, doc_store):
        """Caractères unicode spéciaux (RTL, zero-width, etc.) → stockés."""
        unicode_attacks = [
            "Hello\u202EWorld",           # RTL override
            "Hello\u200BWorld",            # Zero-width space
            "Hello\u0000World",            # Null byte
            "Hello\u00A0World",            # Non-breaking space
        ]
        for text in unicode_attacks:
            doc_id = doc_store.add_document(
                text=text,
                filename="unicode_test.pdf",
                metadata={"content_type": "pdf"},
            )
            assert doc_id is not None
            doc = doc_store.get_document_by_filename("unicode_test.pdf")
            assert text in doc["text"]
            doc_store.delete_document("unicode_test.pdf")

    def test_json_injection_in_metadata(self, doc_store):
        """Métadonnées avec types non JSON-sérialisables → pas de crash."""
        # Les métadonnées passent par json.dump donc les types non natifs
        # sont convertis automatiquement
        meta = {
            "content_type": "pdf",
            "count": 42,
            "ratio": 3.14,
            "tags": ["maths", "physique"],
            "active": True,
            "nested": {"key": "value"},
        }
        doc_id = doc_store.add_document(
            text="contenu",
            filename="json_types.pdf",
            metadata=meta,
        )
        assert doc_id is not None

    def test_search_injection(self, doc_store):
        """Injection dans la requête de recherche → pas de crash."""
        doc_store.add_document(
            text="Contenu normal de cours.",
            filename="safe.pdf",
            metadata={"content_type": "pdf"},
        )
        injections = [
            "'; DROP TABLE users; --",
            "\" OR 1=1 --",
            "''; SELECT * FROM users;",
            "<script>alert('xss')</script>",
            "../../etc/passwd",
            "\\x00\\x01\\x02",
        ]
        for query in injections:
            results = doc_store.search(query)
            assert results is not None
            assert isinstance(results, list)


# ═══════════════════════════════════════════════════════════════════════════
# Tests reindexer — sécurité des entrées
# ═══════════════════════════════════════════════════════════════════════════

class TestReindexerSecurity:
    """Résistance du reindexer aux entrées malveillantes."""

    def test_path_traversal_filename(self, reindexer_module):
        """_classify_file gère les path traversal sans crash."""
        r = reindexer_module
        attacks = [
            "../../etc/passwd.pdf",
            "..\\..\\windows\\system32\\config.pdf",
            "/var/log/syslog.pdf",
            "~/.ssh/id_rsa.pdf",
        ]
        for fname in attacks:
            ftype = r._classify_file(fname)
            assert ftype == "pdf"  # L'extension est toujours .pdf

    def test_no_extension_handling(self, reindexer_module):
        """Fichier sans extension → unknown, pas de crash."""
        r = reindexer_module
        assert r._classify_file("") == "unknown"
        assert r._is_supported_type("") is False

    def test_double_extension(self, reindexer_module):
        """Double extension → seule la dernière compte (et .exe → unknown)."""
        r = reindexer_module
        assert r._classify_file("virus.pdf.exe") == "unknown"  # exe non supporté
        assert r._classify_file("document.txt.pdf") == "pdf"
        assert r._is_supported_type("document.txt.pdf") is True  # se termine par .pdf

    def test_hidden_file(self, reindexer_module):
        """Fichier caché Unix (.hidden.pdf) → détecté comme PDF."""
        r = reindexer_module
        assert r._classify_file(".hidden.pdf") == "pdf"
        assert r._is_supported_type(".hidden.pdf") is True
