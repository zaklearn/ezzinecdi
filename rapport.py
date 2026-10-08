"""
rapport.py — Export Excel du recap (8 colonnes), généré en mémoire.

Logique pure (openpyxl uniquement). Respecte strictement le schéma :
N° · Date échéance · Mois · Type · Montant (DH) · Statut · Rappel J-1 · Observations
"""
from __future__ import annotations

import datetime as dt
from io import BytesIO
from typing import List, Dict

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

import integrity

COLONNES = ["N°", "Date échéance", "Mois", "Type", "Montant (DH)",
            "Statut", "Rappel J-1", "Observations"]

_H_FILL = PatternFill("solid", fgColor="1F3864")
_H_FONT = Font(color="FFFFFF", bold=True)
_THIN = Side(style="thin", color="BFBFBF")
_BORD = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
_CENTER = Alignment(horizontal="center", vertical="center")


def _fr(iso: str) -> str:
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso or ""


def build_recap_xlsx(records: List[Dict], only_paid: bool = True) -> bytes:
    """Construit le classeur recap et renvoie ses octets (.xlsx)."""
    lignes = [r for r in records if (integrity.est_paye(r) if only_paid else True)]
    lignes = sorted(lignes, key=lambda r: r.get("n", 0))

    wb = Workbook()
    ws = wb.active
    ws.title = "Recap" if only_paid else "Complet"

    ws.append(COLONNES)
    for c in range(1, len(COLONNES) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill, cell.font, cell.alignment, cell.border = _H_FILL, _H_FONT, _CENTER, _BORD

    for r in lignes:
        ws.append([
            r.get("n"), _fr(r.get("date_echeance", "")), r.get("mois", ""),
            r.get("type", ""), r.get("montant", 0), r.get("statut", ""),
            _fr(r.get("rappel_j1", "")), r.get("observations", ""),
        ])

    nmax = len(lignes) + 1
    for row in ws.iter_rows(min_row=2, max_row=nmax, max_col=len(COLONNES)):
        for cell in row:
            cell.border = _BORD
        row[0].alignment = _CENTER
        row[1].alignment = _CENTER
        row[4].number_format = '#,##0 "DH"'
        row[6].alignment = _CENTER

    # Ligne total
    tr = nmax + 1
    lab = ws.cell(row=tr, column=4, value="TOTAL")
    lab.font = Font(bold=True)
    lab.alignment = Alignment(horizontal="right")
    tc = ws.cell(row=tr, column=5, value=sum(int(r.get("montant", 0)) for r in lignes))
    tc.font = Font(bold=True)
    tc.number_format = '#,##0 "DH"'
    tc.fill = PatternFill("solid", fgColor="DDEBF7")
    tc.border = _BORD

    for col, w in zip("ABCDEFGH", (6, 15, 16, 28, 14, 18, 14, 30)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    if nmax >= 1:
        ws.auto_filter.ref = f"A1:H{nmax}"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
