"""
storage.py — Persistance Google Drive durcie (v5).

- API Drive v3 via google-api-python-client + google-auth (oauth2client retiré).
- Scope minimal drive.file (fichiers créés par l'app uniquement).
- Erreurs NON silencieuses : une panne API lève DriveError → l'app passe en
  lecture seule au lieu de retomber muettement sur une base vide.
- Verrou optimiste : la révision (headRevisionId) du fichier est suivie ;
  save() refuse d'écraser si la révision a changé (conflit → recharger/fusionner).
- Rotation des backups (garde les N plus récents).
- Repli local (sans secrets) : data.json + backups/ sur disque, écriture atomique.

Secrets attendus :
    [gdrive]
    folder_id = "..."
    [gdrive.service_account]
    type = "service_account"
    ...
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from typing import List, Dict, Optional, Tuple

import streamlit as st

DATA_FILE = "data.json"
BACKUP_DIR = "backups"
DRIVE_DATA_NAME = "data.json"
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
GARDE_BACKUPS = 15


class DriveError(RuntimeError):
    """Panne Drive distincte d'un fichier absent (ne jamais traiter comme base vide)."""


# --------------------------------------------------------------------------- #
#  Détection / client
# --------------------------------------------------------------------------- #
def drive_active() -> bool:
    try:
        return "gdrive" in st.secrets and "service_account" in st.secrets["gdrive"]
    except Exception:
        return False


def mode_label() -> str:
    return "Google Drive" if drive_active() else "Local (Drive non configuré)"


@st.cache_resource(show_spinner=False)
def _service():
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    info = dict(st.secrets["gdrive"]["service_account"])
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _folder_id() -> str:
    return st.secrets["gdrive"]["folder_id"]


# --------------------------------------------------------------------------- #
#  Local atomique
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
#  Drive v3 (lève DriveError sur panne, renvoie None si réellement absent)
# --------------------------------------------------------------------------- #
def _drive_find(name: str) -> Optional[dict]:
    from googleapiclient.errors import HttpError
    try:
        q = (f"'{_folder_id()}' in parents and name = '{name}' and trashed = false")
        res = _service().files().list(
            q=q, spaces="drive",
            fields="files(id, name, headRevisionId, modifiedTime)").execute()
        files = res.get("files", [])
        return files[0] if files else None
    except HttpError as e:
        raise DriveError(f"Drive list a échoué : {e}") from e


def _drive_download(file_id: str) -> str:
    from googleapiclient.errors import HttpError
    try:
        return _service().files().get_media(fileId=file_id).execute().decode("utf-8")
    except HttpError as e:
        raise DriveError(f"Drive download a échoué : {e}") from e


def _drive_upload(name: str, payload: str, file_id: Optional[str]) -> dict:
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaInMemoryUpload
    media = MediaInMemoryUpload(payload.encode("utf-8"), mimetype="application/json")
    try:
        if file_id:
            return _service().files().update(
                fileId=file_id, media_body=media,
                fields="id, headRevisionId").execute()
        meta = {"name": name, "parents": [_folder_id()]}
        return _service().files().create(
            body=meta, media_body=media, fields="id, headRevisionId").execute()
    except HttpError as e:
        raise DriveError(f"Drive upload a échoué : {e}") from e


def _rotate_backups() -> None:
    from googleapiclient.errors import HttpError
    try:
        q = (f"'{_folder_id()}' in parents and name contains 'backup_' and trashed = false")
        res = _service().files().list(
            q=q, spaces="drive", orderBy="name desc",
            fields="files(id, name)").execute()
        for f in res.get("files", [])[GARDE_BACKUPS:]:
            _service().files().delete(fileId=f["id"]).execute()
    except HttpError:
        pass  # la purge ne doit jamais bloquer une sauvegarde


# --------------------------------------------------------------------------- #
#  API publique
# --------------------------------------------------------------------------- #
def load() -> Tuple[List[Dict], Optional[str]]:
    """
    Charge la base. Renvoie (data, revision).
    Lève DriveError sur panne Drive (l'appelant passe en lecture seule) —
    distinct d'un fichier réellement absent (renvoie [] , None).
    """
    if drive_active():
        f = _drive_find(DRIVE_DATA_NAME)            # peut lever DriveError
        if f is None:
            return [], None                          # réellement absent
        raw = _drive_download(f["id"])               # peut lever DriveError
        data = json.loads(raw)
        if not isinstance(data, list):
            raise DriveError("data.json distant corrompu (format inattendu).")
        _write_local_atomic(DATA_FILE, json.dumps(data, ensure_ascii=False, indent=2))
        return data, f.get("headRevisionId")
    local = _read_local()
    return (local if local is not None else []), None


def save(data: List[Dict], expected_revision: Optional[str] = None
         ) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Backup horodaté puis écriture de data.json.
    Verrou optimiste : si expected_revision ≠ révision actuelle → conflit.
    Renvoie (ok, nouvelle_revision, erreur).
    """
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    _write_local_atomic(DATA_FILE, payload)   # cache local toujours

    if not drive_active():
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        _write_local_atomic(os.path.join(BACKUP_DIR, f"backup_{stamp}.json"), payload)
        return True, None, None

    try:
        current = _drive_find(DRIVE_DATA_NAME)
        cur_rev = current.get("headRevisionId") if current else None
        if expected_revision is not None and cur_rev is not None \
                and cur_rev != expected_revision:
            return False, cur_rev, "conflit"   # révision changée entre-temps
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        _drive_upload(f"backup_{stamp}.json", payload, None)
        updated = _drive_upload(DRIVE_DATA_NAME, payload,
                                current["id"] if current else None)
        _rotate_backups()
        return True, updated.get("headRevisionId"), None
    except DriveError as e:
        return False, None, str(e)
