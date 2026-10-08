"""
integrity.py — Contrôle d'intégrité & détection payé/non payé (modèle v4).

Logique pure (aucun import Streamlit). `reconcile()` est exécuté au démarrage
et après chaque import : il valide, dédoublonne, répare les champs dérivés,
détecte l'état payé/non payé et renumérote. Un rapport est renvoyé pour
affichage dans l'expander « Diagnostic ».
"""
from __future__ import annotations

import datetime as dt
from typing import List, Dict, Tuple

import db_gen

# --- Statuts ----------------------------------------------------------------
STATUT_NON_PAYE = "Non payé"
REG_A_TEMPS = "à temps"
REG_RETARD = "retard"
REG_AVANCE = "avance"
_REGS = (REG_A_TEMPS, REG_RETARD, REG_AVANCE)

STATUTS_PAYES = tuple(f"Payé – {r}" for r in _REGS)
STATUTS_VALIDES = (STATUT_NON_PAYE,) + STATUTS_PAYES

TYPES_VALIDES = (db_gen.T_S1, db_gen.T_CN, db_gen.T_S2, db_gen.T_S3)
CLES = ("date_echeance", "mois", "type", "montant", "statut", "rappel_j1", "observations")


def regularite(date_echeance_iso: str, today: dt.date) -> str:
    """Compare le mois de l'échéance au mois courant → à temps / retard / avance."""
    d = dt.date.fromisoformat(date_echeance_iso)
    ref_e, ref_t = (d.year, d.month), (today.year, today.month)
    if ref_e == ref_t:
        return REG_A_TEMPS
    return REG_RETARD if ref_e < ref_t else REG_AVANCE


def statut_paye(reg: str) -> str:
    return f"Payé – {reg}"


def est_paye(rec: Dict) -> bool:
    return str(rec.get("statut", "")).startswith("Payé")


def est_en_retard(rec: Dict, today: dt.date) -> bool:
    """Badge calculé (non stocké) : échéance échue et non payée."""
    if est_paye(rec):
        return False
    try:
        return dt.date.fromisoformat(rec["date_echeance"]) < today
    except (KeyError, ValueError, TypeError):
        return False


def _valide(rec: Dict) -> bool:
    if not all(k in rec for k in CLES):
        return False
    if rec["type"] not in TYPES_VALIDES:
        return False
    if rec["statut"] not in STATUTS_VALIDES:
        return False
    try:
        dt.date.fromisoformat(rec["date_echeance"])
        int(rec["montant"])
    except (ValueError, TypeError):
        return False
    return True


def reconcile(records: List[Dict], today: dt.date | None = None) -> Tuple[List[Dict], Dict]:
    """
    Filtre, répare, dédoublonne, renumérote et détecte payé/non payé.
    Retourne (records_propres, rapport).
    """
    today = today or dt.date.today()
    report = {
        "recus": len(records or []),
        "rejetes": 0, "doublons": 0, "rappels_corriges": 0,
        "total": 0, "payes": 0, "non_payes": 0, "en_retard": 0,
        "modifie": False, "details": [],
    }

    valides: List[Dict] = []
    for rec in (records or []):
        if not isinstance(rec, dict) or not _valide(rec):
            report["rejetes"] += 1
            report["details"].append(f"Rejeté (schéma invalide) : {str(rec)[:80]}")
            continue
        valides.append(rec)

    # Dédoublonnage (mois+type) — on garde l'enregistrement payé en cas de conflit
    par_cle: Dict[Tuple[str, str], Dict] = {}
    for rec in valides:
        k = db_gen.cle(rec)
        if k not in par_cle:
            par_cle[k] = rec
        else:
            report["doublons"] += 1
            report["modifie"] = True
            if est_paye(rec) and not est_paye(par_cle[k]):
                par_cle[k] = rec  # le payé prime
            report["details"].append(f"Doublon fusionné : {k[1]} / {k[0]}")
    dedup = list(par_cle.values())

    # Réparation du rappel J-1 dérivé de la date d'échéance
    for rec in dedup:
        d = dt.date.fromisoformat(rec["date_echeance"])
        attendu = (d - dt.timedelta(days=1)).isoformat()
        if rec.get("rappel_j1") != attendu:
            rec["rappel_j1"] = attendu
            report["rappels_corriges"] += 1
            report["modifie"] = True
        rec["montant"] = int(rec["montant"])
        rec["observations"] = rec.get("observations") or ""

    # Tri + renumérotation
    clean = db_gen.trier_renumeroter(dedup)
    if report["rejetes"] or report["doublons"]:
        report["modifie"] = True

    # Détection payé / non payé
    report["total"] = len(clean)
    report["payes"] = sum(1 for r in clean if est_paye(r))
    report["non_payes"] = report["total"] - report["payes"]
    report["en_retard"] = sum(1 for r in clean if est_en_retard(r, today))
    return clean, report
