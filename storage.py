"""
storage.py — Persistance de la base.

Source de vérité = data.json sur Google Drive (survie aux redéploiements
Streamlit Cloud). Repli local automatique quand Google Drive n'est pas
configuré (st.secrets absents), pour que l'app tourne aussi en local.

Chaîne de récupération au chargement :  Drive principal → backup Drive → base vide.
Écriture :  backup horodaté → mise à jour de data.json.  (Écriture locale atomique
dans tous les cas pour servir de cache.)

Secrets attendus (.streamlit/secrets.toml) :

    [gdrive]
    folder_id = "ID_DU_DOSSIER_DRIVE_PARTAGE"
    [gdrive.service_account]
    type = "service_account"
    project_id = "..."
    private_key_id = "..."
    private_key = "-----BEGIN PRIVATE KEY-----\\n...\\n-----END PRIVATE KEY-----\\n"
    client_email = "...@....iam.gserviceaccount.com"
    client_id = "..."
    token_uri = "https://oauth2.googleapis.com/token"
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from typing import List, Dict, Optional

import streamlit as st

DATA_FILE = "data.json"
BACKUP_DIR = "backups"
DRIVE_DATA_NAME = "data.json"


# --------------------------------------------------------------------------- #
#  Détection Google Drive
# --------------------------------------------------------------------------- #
def drive_active() -> bool:
    """Vrai si les secrets Google Drive sont présents."""
    try:
        return "gdrive" in st.secrets and "service_account" in st.secrets["gdrive"]
    except Exception:
        return False


@st.cache_resource(show_spinner=False)
def _drive():
    """Client Drive (pydrive2) authentifié par compte de service. Mis en cache."""
    from pydrive2.auth import GoogleAuth
    from pydrive2.drive import GoogleDrive
    from oauth2client.service_account import ServiceAccountCredentials

    info = dict(st.secrets["gdrive"]["service_account"])
    scope = ["https://www.googleapis.com/auth/drive"]
    gauth = GoogleAuth()
    gauth.credentials = ServiceAccountCredentials.from_json_keyfile_dict(info, scope)
    return GoogleDrive(gauth)


def _folder_id() -> str:
    return st.secrets["gdrive"]["folder_id"]


# --------------------------------------------------------------------------- #
#  Écriture / lecture locale (cache + repli)
# --------------------------------------------------------------------------- #
def _write_local_atomic(path: str, payload: str) -> None:
    d = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _read_local() -> Optional[List[Dict]]:
    if not os.path.exists(DATA_FILE):
        return None
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else None
    except (json.JSONDecodeError, OSError):
        return None


# --------------------------------------------------------------------------- #
#  Drive : lecture / écriture
# --------------------------------------------------------------------------- #
def _drive_find(name: str):
    q = (f"'{_folder_id()}' in parents and title = '{name}' "
         f"and trashed = false")
    files = _drive().ListFile({"q": q}).GetList()
    return files[0] if files else None


def _drive_read(name: str) -> Optional[List[Dict]]:
    try:
        f = _drive_find(name)
        if not f:
            return None
        data = json.loads(f.GetContentString())
        return data if isinstance(data, list) else None
    except Exception:
        return None


def _drive_write(name: str, payload: str) -> bool:
    try:
        f = _drive_find(name)
        if f is None:
            f = _drive().CreateFile({"title": name, "parents": [{"id": _folder_id()}]})
        f.SetContentString(payload)
        f.Upload()
        return True
    except Exception as e:  # noqa: BLE001
        st.warning(f"Écriture Google Drive impossible : {e}")
        return False


# --------------------------------------------------------------------------- #
#  API publique
# --------------------------------------------------------------------------- #
def load() -> List[Dict]:
    """Charge la base : Drive principal → backup Drive → local → base vide."""
    if drive_active():
        data = _drive_read(DRIVE_DATA_NAME)
        if data is not None:
            _write_local_atomic(DATA_FILE, json.dumps(data, ensure_ascii=False, indent=2))
            return data
        # backup le plus récent sur Drive
        try:
            q = (f"'{_folder_id()}' in parents and title contains 'backup_' "
                 f"and trashed = false")
            backups = _drive().ListFile({"q": q}).GetList()
            if backups:
                backups.sort(key=lambda x: x["title"], reverse=True)
                data = json.loads(backups[0].GetContentString())
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    local = _read_local()
    return local if local is not None else []


def save(data: List[Dict]) -> bool:
    """Backup horodaté puis mise à jour de data.json (Drive + cache local atomique)."""
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    _write_local_atomic(DATA_FILE, payload)  # cache local toujours

    if not drive_active():
        # Repli local : conserve aussi un backup sur disque
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        _write_local_atomic(os.path.join(BACKUP_DIR, f"backup_{stamp}.json"), payload)
        return True

    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    _drive_write(f"backup_{stamp}.json", payload)
    return _drive_write(DRIVE_DATA_NAME, payload)


def mode_label() -> str:
    return "Google Drive" if drive_active() else "Local (Drive non configuré)"
