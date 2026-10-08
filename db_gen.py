"""
db_gen.py — Génération incrémentale de la base (modèle v4).

Aucune dépendance Streamlit : logique pure, testable en isolation.
La base n'est PAS pré-remplie : chaque mois est généré à la demande
(mois courant d'abord, puis rattrapage des mois antérieurs).

Schéma d'un enregistrement (8 colonnes) :
    n, date_echeance, mois, type, montant, statut, rappel_j1, observations
"""
from __future__ import annotations

import calendar
import datetime as dt
from typing import List, Dict, Tuple

MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre",
    12: "Décembre",
}

# Types d'échéances
T_S1 = "Salaire – 1er versement"
T_CN = "CNSS – cotisation mensuelle"
T_S2 = "Salaire – 2e versement"
T_S3 = "Salaire – 3e versement"

# Barème fixe d'un mois : (jour, type, montant, ordre_tri)
BAREME: List[Tuple[int, str, int, int]] = [
    (10, T_S1, 2500, 0),
    (10, T_CN, 1500, 1),
    (20, T_S2, 2500, 2),
    (30, T_S3, 2000, 3),
]

# Ordre de tri stable pour départager deux échéances de même date
ORDRE_TYPE = {t: o for _, t, _, o in BAREME}

STATUT_NON_PAYE = "Non payé"


def mois_label(annee: int, mois: int) -> str:
    """Libellé « Octobre 2026 »."""
    return f"{MOIS_FR[mois]} {annee}"


def _jour_valide(annee: int, mois: int, jour: int) -> int:
    """Rabat le jour sur le dernier jour du mois s'il n'existe pas (ex. 30 fév.)."""
    dernier = calendar.monthrange(annee, mois)[1]
    return min(jour, dernier)


def generer_mois(annee: int, mois: int) -> List[Dict]:
    """Retourne les 4 échéances d'un mois (sans 'n', attribué à l'insertion)."""
    label = mois_label(annee, mois)
    out: List[Dict] = []
    for jour, typ, montant, _ in BAREME:
        d = dt.date(annee, mois, _jour_valide(annee, mois, jour))
        out.append({
            "date_echeance": d.isoformat(),
            "mois": label,
            "type": typ,
            "montant": montant,
            "statut": STATUT_NON_PAYE,
            "rappel_j1": (d - dt.timedelta(days=1)).isoformat(),
            "observations": "",
        })
    return out


def cle(rec: Dict) -> Tuple[str, str]:
    """Clé d'unicité d'une échéance : (mois, type)."""
    return (rec.get("mois", ""), rec.get("type", ""))


def _tri_key(rec: Dict):
    return (rec.get("date_echeance", ""), ORDRE_TYPE.get(rec.get("type", ""), 9))


def trier_renumeroter(records: List[Dict]) -> List[Dict]:
    """Trie par date puis type et réattribue 'n' de 1..N."""
    ordered = sorted(records, key=_tri_key)
    for i, rec in enumerate(ordered, start=1):
        rec["n"] = i
    return ordered


def mois_present(records: List[Dict], label: str) -> bool:
    return any(r.get("mois") == label for r in records)


def ajouter_mois(records: List[Dict], annee: int, mois: int) -> Tuple[List[Dict], bool, str]:
    """
    Ajoute les 4 échéances d'un mois si absent (anti-doublon).
    Retourne (records, ok, message).
    """
    label = mois_label(annee, mois)
    if mois_present(records, label):
        return records, False, f"Le mois « {label} » est déjà enregistré."
    records = records + generer_mois(annee, mois)
    records = trier_renumeroter(records)
    return records, True, f"Mois « {label} » ajouté (4 échéances)."


def base_vide() -> List[Dict]:
    return []
