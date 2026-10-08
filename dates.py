"""
dates.py — Source unique de la date courante (v5).

Appeler `aujourdhui()` à chaque usage plutôt que de figer une constante au
chargement du module : ainsi badges, régularité et compteurs restent exacts
sur une session longue. Fuseau explicite Africa/Casablanca pour éviter la
dérive UTC du serveur Streamlit Cloud.
"""
from __future__ import annotations

import datetime as dt

try:
    from zoneinfo import ZoneInfo
    _TZ = ZoneInfo("Africa/Casablanca")
except Exception:  # repli si tzdata indisponible
    _TZ = None


def maintenant() -> dt.datetime:
    return dt.datetime.now(_TZ) if _TZ else dt.datetime.now()


def aujourdhui() -> dt.date:
    return maintenant().date()
