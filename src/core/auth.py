"""🔐 Authentification — Utilisateurs dans Supabase (table 'utilisateurs')."""

import hashlib
import os
from datetime import datetime
from typing import Optional

import streamlit as st
from supabase import create_client, Client


# ── Configuration Supabase ──────────────────────────────────────────────────
_SUPABASE_URL = os.getenv("SUPABASE_URL", "")
_SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
_TABLE = "users"

# Nettoyer l'URL (enlever /rest/v1/ si présent dans SUPABASE_URL)
if _SUPABASE_URL.endswith("/rest/v1/"):
    _SUPABASE_URL = _SUPABASE_URL[: -len("/rest/v1/")]

# Cache du client (persistance de connexion)
_client_cache: Optional[Client] = None


def _get_client() -> Client:
    """Retourne le client Supabase (instance unique, persistante).

    Le client est créé une seule fois et réutilisé pour éviter de
    multiplier les connexions à chaque appel (Streamlit rerun).
    """
    global _client_cache
    if _client_cache is not None:
        return _client_cache

    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise RuntimeError(
            "Supabase non configuré. "
            "Définissez SUPABASE_URL et SUPABASE_KEY dans .env"
        )
    _client_cache = create_client(_SUPABASE_URL, _SUPABASE_KEY)
    return _client_cache


# ── Rôles ──────────────────────────────────────────────────────────────────
ROLES = ("admin", "professeur", "eleve")
ADMIN_SECRET_CODE = os.getenv("ADMIN_SECRET_CODE", "admin123")


# ── Helpers ────────────────────────────────────────────────────────────────

def _hash_password(password: str) -> str:
    """Hash un mot de passe avec SHA-256."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def _verify_password(password: str, stored: str) -> bool:
    """Vérifie un mot de passe.

    Supporte trois formats :
      - SHA-256 (nouveaux comptes)
      - hash bcrypt (anciens comptes, préfixe $2b$)
      - texte clair (compatibilité)
    """
    sha = hashlib.sha256(password.encode("utf-8")).hexdigest()
    if sha == stored:
        return True
    # Fallback : bcrypt ou texte clair
    if stored.startswith("$2b$"):
        return bcrypt.checkpw(
            password.encode("utf-8"), stored.encode("utf-8")
        )
    return password == stored


def _validate_username(username: str) -> bool:
    """Valide le format d'un nom d'utilisateur."""
    import re
    if len(username) < 2 or len(username) > 30:
        return False
    return re.match(r"^[a-zA-Z0-9_.-]+$", username) is not None


# ── API publique ───────────────────────────────────────────────────────────

def register_user(
    username: str,
    name: str,
    password: str,
    role: str,
) -> dict:
    """Inscrit un nouvel utilisateur dans Supabase.

    La table 'utilisateurs' a la structure :
      username (text), password (text), type (text)

    Note : le paramètre 'name' est ignoré (pas de colonne 'name'
    dans Supabase). Le username sert aussi de nom d'affichage.

    Returns:
        dict avec "success" (bool) et "message" (str) ou "user" (dict).
    """
    # Validation
    if role not in ROLES:
        return {"success": False, "message": f"Rôle invalide : {role}"}

    if not _validate_username(username):
        return {
            "success": False,
            "message": (
                "Nom d'utilisateur invalide (2-30 caractères, "
                "lettres, chiffres, tirets et underscores uniquement)."
            ),
        }

    if len(password) < 6:
        return {
            "success": False,
            "message": "Le mot de passe doit faire au moins 6 caractères.",
        }

    # Vérifier si l'utilisateur existe déjà
    try:
        client = _get_client()
        existing = (
            client.table(_TABLE)
            .select("username")
            .eq("username", username)
            .execute()
        )
        if existing.data:
            return {
                "success": False,
                "message": "Ce nom d'utilisateur est déjà pris.",
            }
    except Exception as e:
        return {"success": False, "message": f"Erreur Supabase : {e}"}

    # Créer l'utilisateur
    try:
        data = {
            "username": username,
            "password": _hash_password(password),  # hash bcrypt
            "type": role,
        }
        client.table(_TABLE).insert(data).execute()

        return {
            "success": True,
            "user": {
                "username": username,
                "name": username,
                "role": role,
            },
        }
    except Exception as e:
        return {"success": False, "message": f"Erreur lors de l'inscription : {e}"}


def authenticate_user(username: str, password: str) -> dict:
    """Authentifie un utilisateur via Supabase.

    Args:
        username: Nom d'utilisateur.
        password: Mot de passe.

    Returns:
        dict avec "success" (bool) et "message" (str) ou "user" (dict).
    """
    try:
        client = _get_client()
        result = (
            client.table(_TABLE)
            .select("*")
            .eq("username", username)
            .execute()
        )

        if not result.data:
            return {
                "success": False,
                "message": "Aucun compte trouvé avec ce nom d'utilisateur.",
            }

        user = result.data[0]
        stored_hash = user.get("password", "")

        if _verify_password(password, stored_hash):
            return {
                "success": True,
                "user": {
                    "username": user["username"],
                    "name": user["username"],  # Pas de colonne 'name'
                    "role": user["type"],
                },
            }
        else:
            return {
                "success": False,
                "message": "Mot de passe incorrect.",
            }

    except Exception as e:
        return {"success": False, "message": f"Erreur de connexion : {e}"}


# ── Gestion des sessions Streamlit ───────────────────────────────────────

def init_session():
    """Initialise les clés de session dans Streamlit."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None


def login_user(user: dict):
    """Connecte l'utilisateur dans la session Streamlit + cookie."""
    st.session_state.authenticated = True
    st.session_state.user = user
    # Persistance : stocker le cookie pour les redémarrages
    from core.session import set_session_cookie
    set_session_cookie(user)


def logout_user():
    """Déconnecte l'utilisateur et efface le cookie."""
    st.session_state.authenticated = False
    st.session_state.user = None
    for key in list(st.session_state.keys()):
        if key not in ("authenticated", "user"):
            del st.session_state[key]
    # Effacer le cookie
    from core.session import clear_session_cookie
    clear_session_cookie()


def get_current_user() -> Optional[dict]:
    """Retourne l'utilisateur connecté ou None."""
    if st.session_state.get("authenticated") and st.session_state.get("user"):
        return st.session_state.user
    return None


def is_authenticated() -> bool:
    """Vérifie si un utilisateur est connecté."""
    return st.session_state.get("authenticated", False)


def require_role(*roles: str) -> bool:
    """Vérifie si l'utilisateur connecté a un des rôles spécifiés."""
    user = get_current_user()
    if not user:
        return False
    return user.get("role") in roles


def get_user_display() -> str:
    """Retourne le nom d'affichage de l'utilisateur connecté."""
    user = get_current_user()
    if not user:
        return "Inconnu"
    role_icon = {
        "admin": "👑",
        "professeur": "👨‍🏫",
        "eleve": "👨‍🎓",
    }.get(user["role"], "👤")
    return f"{role_icon} {user['name']} (@{user['username']})"


# ── Fonctions Admin ────────────────────────────────────────────────────────

def get_all_users() -> list[dict]:
    """Retourne la liste de tous les utilisateurs (sans le hash)."""
    try:
        client = _get_client()
        result = (
            client.table(_TABLE)
            .select("username, type")
            .order("username")
            .execute()
        )
        users = []
        for u in result.data:
            users.append({
                "username": u["username"],
                "name": u["username"],   # Pas de colonne 'name'
                "role": u["type"],
                "created_at": "",
            })
        return users
    except Exception as e:
        st.error(f"Erreur chargement utilisateurs : {e}")
        return []


def delete_user(username: str) -> dict:
    """Supprime un utilisateur par son nom d'utilisateur."""
    try:
        client = _get_client()
        result = (
            client.table(_TABLE)
            .delete()
            .eq("username", username)
            .execute()
        )
        if result.data:
            return {
                "success": True,
                "message": f"Utilisateur {username} supprimé.",
            }
        return {"success": False, "message": "Utilisateur introuvable."}
    except Exception as e:
        return {"success": False, "message": f"Erreur suppression : {e}"}


def update_user_role(username: str, new_role: str) -> dict:
    """Change le rôle d'un utilisateur."""
    if new_role not in ROLES:
        return {"success": False, "message": f"Rôle invalide : {new_role}"}

    try:
        client = _get_client()
        result = (
            client.table(_TABLE)
            .update({"type": new_role})
            .eq("username", username)
            .execute()
        )
        if result.data:
            return {
                "success": True,
                "message": f"Rôle de {username} changé en {new_role}.",
            }
        return {"success": False, "message": "Utilisateur introuvable."}
    except Exception as e:
        return {"success": False, "message": f"Erreur mise à jour : {e}"}


def admin_create_user(
    username: str,
    name: str,
    password: str,
    role: str,
) -> dict:
    """Crée un utilisateur depuis le panneau admin."""
    return register_user(username, name, password, role)


def count_users() -> dict:
    """Compte les utilisateurs par rôle."""
    try:
        client = _get_client()
        result = client.table(_TABLE).select("type").execute()
        counts = {"total": len(result.data), "admin": 0, "professeur": 0, "eleve": 0}
        for u in result.data:
            role = u.get("type", "eleve")
            if role in counts:
                counts[role] += 1
        return counts
    except Exception:
        return {"total": 0, "admin": 0, "professeur": 0, "eleve": 0}