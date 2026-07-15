"""🍪 Gestion de session persistante via cookie signé.

Stocke un token JWT-like (HMAC-SHA256) dans un cookie navigateur.
Permet la reconnexion automatique après redémarrage de l'app."""

import json
import os
import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from typing import Optional

import streamlit as st

COOKIE_NAME = "elearnbot_session"
SESSION_DAYS = 30


def _get_secret() -> str:
    """Clé secrète pour signer les tokens."""
    return os.getenv("SESSION_SECRET") or os.getenv("SUPABASE_KEY", "")


def _make_token(user: dict) -> str:
    """Génère un token signé contenant les infos utilisateur."""
    payload = {
        "username": user["username"],
        "role": user["role"],
        "exp": (datetime.utcnow() + timedelta(days=SESSION_DAYS)).isoformat(),
    }
    data = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    sig = hmac.new(
        _get_secret().encode(), data.encode(), hashlib.sha256
    ).hexdigest()
    return f"{data}.{sig}"


def _parse_token(token: str) -> Optional[dict]:
    """Valide et décode un token signé.

    Returns:
        Dict utilisateur ou None si invalide/expiré.
    """
    try:
        data_b64, sig = token.split(".")
        expected = hmac.new(
            _get_secret().encode(), data_b64.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None

        payload = json.loads(base64.urlsafe_b64decode(data_b64.encode()))
        exp = datetime.fromisoformat(payload["exp"])
        if datetime.utcnow() > exp:
            return None

        return {
            "username": payload["username"],
            "name": payload["username"],
            "role": payload["role"],
        }
    except Exception:
        return None


def set_session_cookie(user: dict):
    """Stocke le token dans un cookie navigateur (30 jours)."""
    token = _make_token(user)
    st.markdown(
        f"""<script>
        document.cookie = "{COOKIE_NAME}={token}; path=/; max-age={SESSION_DAYS * 86400}; SameSite=Lax";
        </script>""",
        unsafe_allow_html=True,
    )


def clear_session_cookie():
    """Supprime le cookie de session."""
    st.markdown(
        f"""<script>
        document.cookie = "{COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax";
        </script>""",
        unsafe_allow_html=True,
    )


def inject_cookie_check():
    """Injecte un script JS qui lit le cookie et le passe à Streamlit.

    Le JS vérifie que 'session_token' n'est pas déjà dans l'URL
    pour éviter les boucles de redirection.
    """
    st.markdown(
        f"""<script>
        (function() {{
            if (window.location.search.includes('session_token')) return;
            var cookies = document.cookie.split('; ');
            for (var i = 0; i < cookies.length; i++) {{
                if (cookies[i].startsWith('{COOKIE_NAME}=')) {{
                    var token = cookies[i].split('=')[1];
                    if (!token) return;
                    var sep = window.location.href.includes('?') ? '&' : '?';
                    window.location.replace(
                        window.location.href + sep + 'session_token=' + encodeURIComponent(token)
                    );
                    break;
                }}
            }}
        }})();
        </script>""",
        unsafe_allow_html=True,
    )


def try_auto_login() -> Optional[dict]:
    """Tente une connexion automatique depuis le token dans l'URL.

    Returns:
        Dict utilisateur si token valide, None sinon.
    """
    if st.session_state.get("authenticated"):
        return None

    raw = st.query_params.get("session_token")
    if not raw:
        return None

    user = _parse_token(raw)
    if user is None:
        clear_session_cookie()
    return user
