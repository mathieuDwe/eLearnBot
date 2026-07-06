"""🔐 Authentification — Gestion des utilisateurs et sessions."""

import json
import os
from datetime import datetime
from typing import Optional

import bcrypt
import streamlit as st


# ── Fichier de stockage des utilisateurs ─────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

# S'assurer que le dossier data/ existe
os.makedirs(DATA_DIR, exist_ok=True)


# ── Modèle utilisateur ───────────────────────────────────────────────────
ROLES = ("admin", "professeur", "eleve")

# Code secret admin (depuis .env ou valeur par défaut)
ADMIN_SECRET_CODE = os.getenv("ADMIN_SECRET_CODE", "admin123")


def _load_users() -> list[dict]:
    """Charge la liste des utilisateurs depuis le fichier JSON."""
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(users: list[dict]):
    """Sauvegarde la liste des utilisateurs dans le fichier JSON."""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def _hash_password(password: str) -> str:
    """Hash un mot de passe avec bcrypt."""
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """Vérifie un mot de passe contre son hash."""
    return bcrypt.checkpw(
        password.encode("utf-8"), password_hash.encode("utf-8")
    )


def _validate_username(username: str) -> bool:
    """Valide le format d'un nom d'utilisateur (2-30 car., lettres, chiffres, tirets)."""
    if len(username) < 2 or len(username) > 30:
        return False
    # Caractères autorisés : lettres, chiffres, tirets, underscores, points
    import re
    return re.match(r"^[a-zA-Z0-9_.-]+$", username) is not None


# ── API publique ─────────────────────────────────────────────────────────


def register_user(
    username: str,
    name: str,
    password: str,
    role: str,
) -> dict:
    """Inscrit un nouvel utilisateur.

    Args:
        username: Nom d'utilisateur (identifiant de connexion).
        name: Nom d'affichage.
        password: Mot de passe (>= 6 caractères).
        role: "admin", "professeur" ou "eleve".

    Returns:
        dict avec "success" (bool) et "message" (str) ou "user" (dict).

    Exemple:
        {"success": True, "user": {"username": "...", "name": "...", "role": "professeur"}}
        {"success": False, "message": "Nom d'utilisateur déjà utilisé."}
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

    if not name.strip():
        return {"success": False, "message": "Le nom est requis."}

    # Vérifier si le nom d'utilisateur existe déjà
    users = _load_users()
    if any(u["username"] == username for u in users):
        return {
            "success": False,
            "message": "Ce nom d'utilisateur est déjà pris.",
        }

    # Créer l'utilisateur
    user = {
        "username": username,
        "name": name.strip(),
        "password_hash": _hash_password(password),
        "role": role,
        "created_at": datetime.now().isoformat(),
    }
    users.append(user)
    _save_users(users)

    return {
        "success": True,
        "user": {k: v for k, v in user.items() if k != "password_hash"},
    }


def authenticate_user(username: str, password: str) -> dict:
    """Authentifie un utilisateur.

    Args:
        username: Nom d'utilisateur.
        password: Mot de passe.

    Returns:
        dict avec "success" (bool) et "message" (str) ou "user" (dict).
    """
    users = _load_users()

    for user in users:
        if user["username"] == username:
            if _verify_password(password, user["password_hash"]):
                return {
                    "success": True,
                    "user": {
                        k: v for k, v in user.items() if k != "password_hash"
                    },
                }
            return {
                "success": False,
                "message": "Mot de passe incorrect.",
            }

    return {
        "success": False,
        "message": "Aucun compte trouvé avec ce nom d'utilisateur.",
    }


# ── Gestion des sessions Streamlit ───────────────────────────────────────


def init_session():
    """Initialise les clés de session dans Streamlit."""
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "user" not in st.session_state:
        st.session_state.user = None


def login_user(user: dict):
    """Connecte l'utilisateur dans la session Streamlit.

    Args:
        user: Dict avec username, name, role.
    """
    st.session_state.authenticated = True
    st.session_state.user = user


def logout_user():
    """Déconnecte l'utilisateur."""
    st.session_state.authenticated = False
    st.session_state.user = None
    # Nettoyer les clés de session liées aux pages
    for key in list(st.session_state.keys()):
        if key not in ("authenticated", "user"):
            del st.session_state[key]


def get_current_user() -> Optional[dict]:
    """Retourne l'utilisateur connecté ou None."""
    if st.session_state.get("authenticated") and st.session_state.get("user"):
        return st.session_state.user
    return None


def is_authenticated() -> bool:
    """Vérifie si un utilisateur est connecté."""
    return st.session_state.get("authenticated", False)


def require_role(*roles: str) -> bool:
    """Vérifie si l'utilisateur connecté a un des rôles spécifiés.

    Args:
        *roles: Rôles autorisés ("professeur", "eleve").

    Returns:
        True si l'utilisateur a un des rôles.

    Exemple:
        require_role("professeur")  # Seulement les profs
        require_role("professeur", "eleve")  # Les deux
    """
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
    return f"{role_icon} {user['name']} ({user['username']})"


# ── Fonctions Admin ───────────────────────────────────────────────────────


def get_all_users() -> list[dict]:
    """Retourne la liste de tous les utilisateurs (sans les hash)."""
    users = _load_users()
    return [
        {k: v for k, v in u.items() if k != "password_hash"}
        for u in users
    ]


def delete_user(username: str) -> dict:
    """Supprime un utilisateur par son nom d'utilisateur.

    Args:
        username: Nom d'utilisateur à supprimer.

    Returns:
        dict avec success et message.
    """
    users = _load_users()
    filtered = [u for u in users if u["username"] != username]

    if len(filtered) == len(users):
        return {"success": False, "message": "Utilisateur introuvable."}

    _save_users(filtered)
    return {
        "success": True,
        "message": f"Utilisateur {username} supprimé.",
    }


def update_user_role(username: str, new_role: str) -> dict:
    """Change le rôle d'un utilisateur.

    Args:
        username: Nom d'utilisateur.
        new_role: Nouveau rôle.

    Returns:
        dict avec success et message.
    """
    if new_role not in ROLES:
        return {"success": False, "message": f"Rôle invalide : {new_role}"}

    users = _load_users()
    for u in users:
        if u["username"] == username:
            u["role"] = new_role
            _save_users(users)
            return {
                "success": True,
                "message": f"Rôle de {username} changé en {new_role}.",
            }

    return {"success": False, "message": "Utilisateur introuvable."}


def admin_create_user(
    username: str,
    name: str,
    password: str,
    role: str,
) -> dict:
    """Crée un utilisateur directement depuis le panneau admin (sans code secret).

    Args:
        username: Nom d'utilisateur.
        name: Nom d'affichage.
        password: Mot de passe (>= 6 caractères).
        role: "admin", "professeur" ou "eleve".

    Returns:
        dict avec success et message.
    """
    return register_user(username, name, password, role)


def count_users() -> dict:
    """Compte les utilisateurs par rôle.

    Returns:
        dict avec total, admin, professeur, eleve.
    """
    users = _load_users()
    counts = {"total": len(users), "admin": 0, "professeur": 0, "eleve": 0}
    for u in users:
        role = u.get("role", "eleve")
        if role in counts:
            counts[role] += 1
    return counts