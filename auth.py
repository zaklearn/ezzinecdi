"""
auth.py — Porte d'accès par mot de passe + rôles (v5).

Deux rôles :
  - "superadmin" : lecture ET écriture (payer, dévalider, importer, remplacer, déclarer).
  - "user"       : lecture seule + export.

Les mots de passe viennent de st.secrets (jamais en dur dans le code) :

    [auth]
    superadmin_password = "..."
    user_password = "..."

Reset : éditer Settings → Secrets (Streamlit Cloud) ou .streamlit/secrets.toml (local).
"""
from __future__ import annotations

import hmac
import streamlit as st

SUPERADMIN = "superadmin"
USER = "user"


def _secrets_ok() -> bool:
    try:
        a = st.secrets["auth"]
        return "superadmin_password" in a and "user_password" in a
    except Exception:
        return False


def _check(saisi: str) -> str | None:
    """Retourne le rôle si le mot de passe correspond, sinon None (comparaison constante)."""
    a = st.secrets["auth"]
    if hmac.compare_digest(saisi, str(a["superadmin_password"])):
        return SUPERADMIN
    if hmac.compare_digest(saisi, str(a["user_password"])):
        return USER
    return None


def login() -> str | None:
    """Affiche le formulaire si besoin et renvoie le rôle courant (ou None)."""
    if st.session_state.get("role"):
        return st.session_state["role"]

    st.title("🔐 Suivi virements & CNSS")
    if not _secrets_ok():
        st.error("Authentification non configurée : ajoutez un bloc [auth] "
                 "(superadmin_password, user_password) dans les secrets.")
        st.stop()

    with st.form("login"):
        pwd = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Se connecter"):
            role = _check(pwd)
            if role:
                st.session_state["role"] = role
                st.rerun()
            else:
                st.error("Mot de passe incorrect.")
    st.caption("Super admin : lecture/écriture · Utilisateur : lecture + export.")
    return None


def logout_button() -> None:
    if st.sidebar.button("🚪 Se déconnecter"):
        st.session_state.pop("role", None)
        st.rerun()


def is_admin(role: str | None) -> bool:
    return role == SUPERADMIN
