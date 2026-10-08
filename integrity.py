"""
integrity.py — Intégrité, régularité au jour et détection payé/non payé (v5).

Changements v5 :
- régularité calculée au JOUR à partir de `date_paiement` vs `date_echeance` ;
- champ technique `date_paiement` géré et cohérence payé ⇔ date_paiement ;
- validation renforcée à l'import : montant == barème(type), mois == mois(date) ;
- distinction badge « en retard » (échu non payé) vs statut « payé en retard ».
"""
from __future__ import annotations

import datetime as dt
from typing import List, Dict, Tuple

import db_gen

STATUT_NON_PAYE = db_gen.STATUT_NON_PAYE          # source unique
REG_A_TEMPS, REG_RETARD, REG_AVANCE = "à temps", "retard", "avance"
_REGS = (REG_A_TEMPS, REG_RETARD, REG_AVANCE)
STATUTS_PAYES = tuple(f"Payé – {r}" for r in _REGS)
STATUTS_VALIDES = (STATUT_NON_PAYE,) + STATUTS_PAYES
TYPES_VALIDES = (db_gen.T_S1, db_gen.T_CN, db_gen.T_S2, db_gen.T_S3)
CLES = ("date_echeance", "mois", "type", "montant", "statut",
        "rappel_j1", "observations", "date_paiement")


# --- Régularité (au jour) --------------------------------------------------- #
def regularite(date_paiement_iso: str, date_echeance_iso: str) -> str:
    """retard si payé après l'échéance ; avance si échéance dans un mois futur ;
    sinon à temps (payé le même mois, à la date d'échéance ou avant)."""
    p = dt.date.fromisoformat(date_paiement_iso)
    e = dt.date.fromisoformat(date_echeance_iso)
    if p > e:
        return REG_RETARD
    if (e.year, e.month) > (p.year, p.month):
        return REG_AVANCE
    return REG_A_TEMPS


def statut_paye(reg: str) -> str:
    return f"Payé – {reg}"


def est_paye(rec: Dict) -> bool:
    return str(rec.get("statut", "")).startswith("Payé")


def est_en_retard(rec: Dict, today: dt.date) -> bool:
    """Badge d'affichage : échéance échue ET non payée (jamais stocké)."""
    if est_paye(rec):
        return False
    try:
        return dt.date.fromisoformat(rec["date_echeance"]) < today
    except (KeyError, ValueError, TypeError):
        return False


# --- Validation ------------------------------------------------------------- #
def _schema_ok(rec: Dict) -> bool:
    if not isinstance(rec, dict) or not all(k in rec for k in CLES):
        return False
    if rec["type"] not in TYPES_VALIDES or rec["statut"] not in STATUTS_VALIDES:
        return False
    try:
        dt.date.fromisoformat(rec["date_echeance"])
        int(rec["montant"])
    except (ValueError, TypeError):
        return False
    if rec["date_paiement"] is not None:
        try:
            dt.date.fromisoformat(rec["date_paiement"])
        except (ValueError, TypeError):
            return False
    return True


# --- Réconciliation --------------------------------------------------------- #
def reconcile(records: List[Dict], today: dt.date | None = None) -> Tuple[List[Dict], Dict]:
    today = today or dt.date.today()
    rep = {"recus": len(records or []), "rejetes": 0, "doublons": 0,
           "rappels_corriges": 0, "montants_corriges": 0, "mois_corriges": 0,
           "statuts_corriges": 0, "total": 0, "payes": 0, "non_payes": 0,
           "en_retard": 0, "modifie": False, "details": []}

    valides: List[Dict] = []
    for rec in (records or []):
        if not _schema_ok(rec):
            rep["rejetes"] += 1
            rep["details"].append(f"Rejeté (schéma) : {str(rec)[:80]}")
            continue
        valides.append(rec)

    # Dédoublonnage (mois+type) — le payé prime
    par_cle: Dict[Tuple[str, str], Dict] = {}
    for rec in valides:
        k = db_gen.cle(rec)
        if k not in par_cle:
            par_cle[k] = rec
        else:
            rep["doublons"] += 1
            if est_paye(rec) and not est_paye(par_cle[k]):
                par_cle[k] = rec
            rep["details"].append(f"Doublon fusionné : {k[1]} / {k[0]}")
    dedup = list(par_cle.values())

    for rec in dedup:
        e = dt.date.fromisoformat(rec["date_echeance"])
        # rappel J-1 dérivé
        attendu = (e - dt.timedelta(days=1)).isoformat()
        if rec.get("rappel_j1") != attendu:
            rec["rappel_j1"] = attendu
            rep["rappels_corriges"] += 1
        # montant attendu par type
        att_m = db_gen.MONTANT_TYPE[rec["type"]]
        if int(rec["montant"]) != att_m:
            rec["montant"] = att_m
            rep["montants_corriges"] += 1
        else:
            rec["montant"] = int(rec["montant"])
        # mois cohérent avec la date
        att_mois = db_gen.mois_label(e.year, e.month)
        if rec.get("mois") != att_mois:
            rec["mois"] = att_mois
            rep["mois_corriges"] += 1
        rec["observations"] = rec.get("observations") or ""

        # Cohérence payé ⇔ date_paiement + recalcul du statut
        if est_paye(rec):
            if not rec.get("date_paiement"):
                rec["date_paiement"] = rec["date_echeance"]  # repli : à temps
            reg = regularite(rec["date_paiement"], rec["date_echeance"])
            att_statut = statut_paye(reg)
            if rec["statut"] != att_statut:
                rec["statut"] = att_statut
                rep["statuts_corriges"] += 1
        else:
            if rec.get("date_paiement") is not None:
                rec["date_paiement"] = None
                rep["statuts_corriges"] += 1

    clean = db_gen.trier_renumeroter(dedup)
    rep["modifie"] = any(rep[k] for k in
                         ("rejetes", "doublons", "rappels_corriges",
                          "montants_corriges", "mois_corriges", "statuts_corriges"))
    rep["total"] = len(clean)
    rep["payes"] = sum(1 for r in clean if est_paye(r))
    rep["non_payes"] = rep["total"] - rep["payes"]
    rep["en_retard"] = sum(1 for r in clean if est_en_retard(r, today))
    return clean, rep
