"""
rapport.py — Export Excel (8 colonnes) + ré-export ICS des rappels (v5).

Logique pure. L'Excel conserve strictement les 8 colonnes ; `date_paiement`
(technique) est reflété dans « Observations ». L'ICS régénère les rappels J-1
pour les échéances non payées (le champ rappel_j1 devient enfin utile).
"""
from __future__ import annotations

import datetime as dt
import uuid
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


# --- Excel ------------------------------------------------------------------ #
def build_recap_xlsx(records: List[Dict], only_paid: bool = True) -> bytes:
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
        obs = r.get("observations", "")
        ws.append([r.get("n"), _fr(r.get("date_echeance", "")), r.get("mois", ""),
                   r.get("type", ""), r.get("montant", 0), r.get("statut", ""),
                   _fr(r.get("rappel_j1", "")), obs])

    nmax = len(lignes) + 1
    for row in ws.iter_rows(min_row=2, max_row=nmax, max_col=len(COLONNES)):
        for cell in row:
            cell.border = _BORD
        row[0].alignment = _CENTER
        row[1].alignment = _CENTER
        row[4].number_format = '#,##0 "DH"'
        row[6].alignment = _CENTER

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


# --- ICS (rappels J-1) ------------------------------------------------------ #
def _fold(line: str) -> str:
    b = line.encode("utf-8")
    if len(b) <= 73:
        return line
    out, cur = [], b""
    for ch in line:
        e = ch.encode("utf-8")
        if len(cur) + len(e) > 73:
            out.append(cur.decode("utf-8"))
            cur = b" "
        cur += e
    out.append(cur.decode("utf-8"))
    return "\r\n".join(out)


def _esc(s: str) -> str:
    return (s.replace("\\", "\\\\").replace(";", "\\;")
            .replace(",", "\\,").replace("\n", "\\n"))


def build_ics(records: List[Dict], only_unpaid: bool = True) -> bytes:
    """Rappels J-1 (alarme -PT15H, journée entière) pour les échéances non payées."""
    cibles = [r for r in records if (not integrity.est_paye(r)) or (not only_unpaid)]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    L = ["BEGIN:VCALENDAR", "VERSION:2.0",
         "PRODID:-//Suivi salaires & CNSS//Zak//FR", "CALSCALE:GREGORIAN",
         "METHOD:PUBLISH", "X-WR-CALNAME:Rappels salaires & CNSS",
         "X-WR-TIMEZONE:Africa/Casablanca"]
    for r in sorted(cibles, key=lambda x: x.get("date_echeance", "")):
        try:
            d = dt.date.fromisoformat(r["date_echeance"])
        except (KeyError, ValueError, TypeError):
            continue
        montant = format(int(r.get("montant", 0)), ",d").replace(",", " ")
        titre = f"{r.get('type','')} — {montant} DH"
        desc = (f"{r.get('mois','')} — échéance {d.strftime('%d/%m/%Y')}\\n"
                f"Statut : {r.get('statut','')}")
        L += ["BEGIN:VEVENT",
              "UID:%s@ezzinecdi" % uuid.uuid5(uuid.NAMESPACE_DNS, f"{d}-{r.get('type','')}"),
              "DTSTAMP:" + stamp,
              "DTSTART;VALUE=DATE:" + d.strftime("%Y%m%d"),
              "DTEND;VALUE=DATE:" + (d + dt.timedelta(days=1)).strftime("%Y%m%d"),
              _fold("SUMMARY:" + _esc(titre)),
              _fold("DESCRIPTION:" + _esc(desc)),
              "CATEGORIES:" + ("CNSS" if r.get("type") == "CNSS – cotisation mensuelle" else "SALAIRE"),
              "TRANSP:TRANSPARENT", "STATUS:CONFIRMED",
              "BEGIN:VALARM", "ACTION:DISPLAY", "TRIGGER:-PT15H",
              _fold("DESCRIPTION:Rappel J-1 — " + _esc(titre)),
              "END:VALARM", "END:VEVENT"]
    L.append("END:VCALENDAR")
    return ("\r\n".join(L) + "\r\n").encode("utf-8")
