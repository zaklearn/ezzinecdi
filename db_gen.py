"""
db_gen.py — Génération incrémentale de la base (v5).

Base non pré-remplie : chaque mois est généré à la demande. Aucune dépendance
Streamlit. Les constantes de type/statut/barème sont définies ici et réutilisées
ailleurs (source unique, évite la duplication).

Schéma stocké (9 champs ; l'export reste à 8 colonnes, date_paiement est technique) :
    n, date_echeance, mois, type, montant, statut, rappel_j1, observations, date_paiement
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

# Barème fixe : (jour, type, montant, ordre_tri)
BAREME: List[Tuple[int, str, int, int]] = [
    (10, T_S1, 2500, 0),
    (10, T_CN, 1500, 1),
    (20, T_S2, 2500, 2),
    (30, T_S3, 2000, 3),
]
ORDRE_TYPE = {t: o for _, t, _, o in BAREME}
MONTANT_TYPE = {t: m for _, t, m, _ in BAREME}   # montant attendu par type
JOUR_TYPE = {t: j for j, t, _, _ in BAREME}

# Statut de référence — défini UNE fois ici, importé ailleurs
STATUT_NON_PAYE = "Non payé"


def mois_label(annee: int, mois: int) -> str:
    return f"{MOIS_FR[mois]} {annee}"


def _jour_valide(annee: int, mois: int, jour: int) -> int:
    return min(jour, calendar.monthrange(annee, mois)[1])


def generer_mois(annee: int, mois: int) -> List[Dict]:
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
            "date_paiement": None,
        })
    return out


def cle(rec: Dict) -> Tuple[str, str]:
    return (rec.get("mois", ""), rec.get("type", ""))


def _tri_key(rec: Dict):
    return (rec.get("date_echeance", ""), ORDRE_TYPE.get(rec.get("type", ""), 9))


def trier_renumeroter(records: List[Dict]) -> List[Dict]:
    ordered = sorted(records, key=_tri_key)
    for i, rec in enumerate(ordered, start=1):
        rec["n"] = i
    return ordered


def mois_present(records: List[Dict], label: str) -> bool:
    return any(r.get("mois") == label for r in records)


def ajouter_mois(records: List[Dict], annee: int, mois: int) -> Tuple[List[Dict], bool, str]:
    label = mois_label(annee, mois)
    if mois_present(records, label):
        return records, False, f"Le mois « {label} » est déjà enregistré."
    records = trier_renumeroter(records + generer_mois(annee, mois))
    return records, True, f"Mois « {label} » ajouté (4 échéances)."


def base_vide() -> List[Dict]:
    return []
