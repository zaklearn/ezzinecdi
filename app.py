"""
app.py — Suivi des virements salaires & CNSS (Streamlit, modèle v4).

Sidebar de navigation (mois courant figé + 3 panneaux + régularisation + import)
et persistance Google Drive. Voir conception_app_suivi_virements_v4.md.
"""
from __future__ import annotations

import datetime as dt
import json

import streamlit as st

import db_gen
import integrity
import rapport
import storage

st.set_page_config(page_title="Suivi virements & CNSS", page_icon="💸", layout="wide")

# --------------------------------------------------------------------------- #
#  Style
# --------------------------------------------------------------------------- #
st.markdown("""
<style>
.block-container {padding-top: 2rem;}
.carte {border:1px solid #d9dee8; border-radius:12px; padding:14px 16px; margin-bottom:12px;
        background:var(--background-color);}
.carte h4 {margin:0 0 4px 0; font-size:0.95rem;}
.montant {font-size:1.35rem; font-weight:700;}
.badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.78rem; font-weight:600;}
.b-venir {background:#FFF3CD; color:#8A6D00;}
.b-retard {background:#F8D7DA; color:#842029;}
.b-paye {background:#D1E7DD; color:#0F5132;}
.sub {color:#6c757d; font-size:0.82rem;}
</style>
""", unsafe_allow_html=True)

TODAY = dt.date.today()
MOIS_COURANT = db_gen.mois_label(TODAY.year, TODAY.month)


# --------------------------------------------------------------------------- #
#  État
# --------------------------------------------------------------------------- #
def _charger():
    data = storage.load()
    data, report = integrity.reconcile(data, TODAY)
    if report["modifie"]:
        storage.save(data)
    st.session_state["data"] = data
    st.session_state["diag"] = report


if "data" not in st.session_state:
    _charger()


def _data():
    return st.session_state["data"]


def _persister(data):
    data, report = integrity.reconcile(data, TODAY)
    storage.save(data)
    st.session_state["data"] = data
    st.session_state["diag"] = report


def _fr(iso: str) -> str:
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso


def _dh(montant) -> str:
    return f"{int(montant):,}".replace(",", " ") + " DH"


# --------------------------------------------------------------------------- #
#  Paiement (canal unique)
# --------------------------------------------------------------------------- #
def _appliquer_paiement(n: int):
    data = _data()
    for rec in data:
        if rec["n"] == n:
            reg = integrity.regularite(rec["date_echeance"], TODAY)
            rec["statut"] = integrity.statut_paye(reg)
            rec["observations"] = f"Payé le {TODAY.strftime('%d/%m/%Y')}"
            break
    _persister(data)


@st.dialog("Confirmer le paiement")
def dlg_payer(rec: dict):
    reg = integrity.regularite(rec["date_echeance"], TODAY)
    if reg != integrity.REG_A_TEMPS:
        st.warning(f"⚠️ Vous régularisez un mois **en {reg}** : {rec['mois']}.")
    st.write(f"**{rec['type']}** — {rec['mois']}")
    st.write(f"Montant : **{_dh(rec['montant'])}**  ·  échéance du **{_fr(rec['date_echeance'])}**")
    c1, c2 = st.columns(2)
    if c1.button("✅ Confirmer", use_container_width=True, type="primary"):
        _appliquer_paiement(rec["n"])
        st.rerun()
    if c2.button("Annuler", use_container_width=True):
        st.rerun()


@st.dialog("Dévalider le paiement")
def dlg_devalider(rec: dict):
    st.write(f"Repasser **{rec['type']} — {rec['mois']}** en « Non payé » ?")
    c1, c2 = st.columns(2)
    if c1.button("↩️ Dévalider", use_container_width=True, type="primary"):
        data = _data()
        for r in data:
            if r["n"] == rec["n"]:
                r["statut"] = integrity.STATUT_NON_PAYE
                r["observations"] = ""
                break
        _persister(data)
        st.rerun()
    if c2.button("Annuler", use_container_width=True):
        st.rerun()


# --------------------------------------------------------------------------- #
#  Composants d'affichage
# --------------------------------------------------------------------------- #
def _badge(rec: dict) -> str:
    if integrity.est_paye(rec):
        return '<span class="badge b-paye">✅ ' + rec["statut"] + "</span>"
    if integrity.est_en_retard(rec, TODAY):
        return '<span class="badge b-retard">🔴 En retard</span>'
    return '<span class="badge b-venir">🟡 À venir</span>'


def _carte(rec: dict, with_actions: bool = True):
    st.markdown(
        f'<div class="carte"><h4>{rec["type"]}</h4>'
        f'<div class="sub">{rec["mois"]} · échéance {_fr(rec["date_echeance"])} '
        f'· rappel {_fr(rec["rappel_j1"])}</div>'
        f'<div class="montant">{_dh(rec["montant"])}</div>{_badge(rec)}</div>',
        unsafe_allow_html=True,
    )
    if with_actions and not integrity.est_paye(rec):
        if st.button("💰 Payer", key=f"pay_{rec['n']}", use_container_width=True):
            dlg_payer(rec)


# --------------------------------------------------------------------------- #
#  Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("💸 Suivi virements & CNSS")
    st.info(f"📅 Mois courant : **{MOIS_COURANT}** (figé)")

    panneau = st.radio("Navigation",
                       ["🔜 À venir", "📅 Mois courant", "📊 Récap & export"],
                       label_visibility="collapsed")

    st.divider()
    with st.container(border=True):
        st.markdown("#### ⚠️ Régularisation / nouveau mois")
        annees = list(range(TODAY.year - 2, TODAY.year + 3))
        ca, cm = st.columns(2)
        an = ca.selectbox("Année", annees, index=annees.index(TODAY.year))
        moi = cm.selectbox("Mois", list(db_gen.MOIS_FR.keys()),
                           index=TODAY.month - 1,
                           format_func=lambda m: db_gen.MOIS_FR[m])
        label_sel = db_gen.mois_label(an, moi)
        if label_sel == MOIS_COURANT:
            st.caption("→ Mois courant : utilisez le panneau « 📅 Mois courant ».")
        elif not db_gen.mois_present(_data(), label_sel):
            if st.button(f"➕ Déclarer {label_sel}", use_container_width=True):
                data, ok, msg = db_gen.ajouter_mois(_data(), an, moi)
                _persister(data)
                st.toast(msg)
                st.rerun()
        else:
            st.caption(f"« {label_sel} » est déjà déclaré — payez ses échéances ci-dessous.")
            for rec in sorted([r for r in _data() if r["mois"] == label_sel],
                              key=lambda r: r["n"]):
                if not integrity.est_paye(rec):
                    if st.button(f"💰 {rec['type']} — {_dh(rec['montant'])}",
                                 key=f"reg_{rec['n']}", use_container_width=True):
                        dlg_payer(rec)
                else:
                    st.caption(f"✅ {rec['type']} — {rec['statut']}")

    st.divider()
    with st.container(border=True):
        st.markdown("#### ⬆️ Importer une base")
        up = st.file_uploader("Fichier data.json", type="json", label_visibility="collapsed")
        mode = st.radio("Mode", ["Fusionner", "Remplacer"], horizontal=True)
        if up is not None and st.button("Importer", use_container_width=True):
            try:
                imported = json.load(up)
                if not isinstance(imported, list):
                    raise ValueError("Le fichier doit contenir une liste d'enregistrements.")
                if mode == "Remplacer":
                    data = imported
                else:  # Fusionner par (mois, type) — l'import complète/actualise
                    par_cle = {db_gen.cle(r): r for r in _data()}
                    for r in imported:
                        par_cle[db_gen.cle(r)] = r
                    data = list(par_cle.values())
                _persister(data)
                st.success(f"Import {mode.lower()} : {len(imported)} enregistrement(s).")
                st.rerun()
            except (json.JSONDecodeError, ValueError) as e:
                st.error(f"Import impossible : {e}")

    st.divider()
    d = st.session_state.get("diag", {})
    with st.expander("🔎 Diagnostic"):
        st.caption(f"Persistance : **{storage.mode_label()}**")
        st.write(f"Total échéances : {d.get('total', 0)}")
        st.write(f"Payées : {d.get('payes', 0)} · Non payées : {d.get('non_payes', 0)}")
        st.write(f"En retard : {d.get('en_retard', 0)}")
        if d.get("doublons") or d.get("rejetes") or d.get("rappels_corriges"):
            st.caption(f"Réparations — doublons {d.get('doublons',0)}, "
                       f"rejets {d.get('rejetes',0)}, rappels {d.get('rappels_corriges',0)}")
        if st.button("🔄 Recharger depuis la source"):
            _charger()
            st.rerun()


# --------------------------------------------------------------------------- #
#  Corps
# --------------------------------------------------------------------------- #
data = _data()

if not data:
    st.header("Bienvenue 👋")
    st.write("Aucune donnée. Déclarez votre **premier mois** pour démarrer le suivi.")
    ca, cm, cb = st.columns([1, 1, 1])
    an = ca.selectbox("Année", list(range(TODAY.year - 2, TODAY.year + 3)),
                      index=2, key="init_an")
    moi = cm.selectbox("Mois", list(db_gen.MOIS_FR.keys()), index=TODAY.month - 1,
                       format_func=lambda m: db_gen.MOIS_FR[m], key="init_moi")
    cb.write("")
    if cb.button("➕ Déclarer ce mois", use_container_width=True, type="primary"):
        newd, ok, msg = db_gen.ajouter_mois(data, an, moi)
        _persister(newd)
        st.rerun()
    st.stop()


# ---- Panneau : À venir -----------------------------------------------------
if panneau == "🔜 À venir":
    st.header("🔜 Paiements à venir")
    a_venir = sorted([r for r in data if not integrity.est_paye(r)],
                     key=lambda r: (r["date_echeance"], r["n"]))[:6]
    if not a_venir:
        st.success("Toutes les échéances déclarées sont payées. ✅")
    else:
        cols = st.columns(3)
        for i, rec in enumerate(a_venir):
            with cols[i % 3]:
                _carte(rec)


# ---- Panneau : Mois courant (figé) ----------------------------------------
elif panneau == "📅 Mois courant":
    st.header(f"📅 {MOIS_COURANT}")
    du_mois = sorted([r for r in data if r["mois"] == MOIS_COURANT], key=lambda r: r["n"])
    if not du_mois:
        st.warning(f"Le mois courant n'est pas encore déclaré.")
        if st.button(f"➕ Déclarer {MOIS_COURANT}", type="primary"):
            newd, ok, msg = db_gen.ajouter_mois(data, TODAY.year, TODAY.month)
            _persister(newd)
            st.rerun()
    else:
        paye = sum(int(r["montant"]) for r in du_mois if integrity.est_paye(r))
        total = sum(int(r["montant"]) for r in du_mois)
        m1, m2, m3 = st.columns(3)
        m1.metric("Payé", _dh(paye))
        m2.metric("Restant", _dh(total - paye))
        m3.metric("Avancement", f"{round(100*paye/total) if total else 0} %")
        st.divider()
        cols = st.columns(2)
        for i, rec in enumerate(du_mois):
            with cols[i % 2]:
                _carte(rec)
                if integrity.est_paye(rec):
                    if st.button("↩️ Dévalider", key=f"dev_{rec['n']}"):
                        dlg_devalider(rec)


# ---- Panneau : Récap & export ---------------------------------------------
else:
    st.header("📊 Récap & export")
    total = len(data)
    payes = [r for r in data if integrity.est_paye(r)]
    montant_paye = sum(int(r["montant"]) for r in payes)
    montant_total = sum(int(r["montant"]) for r in data)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total payé", _dh(montant_paye))
    k2.metric("Restant dû", _dh(montant_total - montant_paye))
    k3.metric("Échéances payées", f"{len(payes)} / {total}")
    k4.metric("Avancement", f"{round(100*len(payes)/total) if total else 0} %")
    st.progress((len(payes) / total) if total else 0.0)

    # Répartition par régularité
    rep = {r: 0 for r in ("à temps", "retard", "avance")}
    for r in payes:
        for k in rep:
            if r["statut"].endswith(k):
                rep[k] += 1
    st.caption(f"Régularité — à temps : {rep['à temps']} · "
               f"retard : {rep['retard']} · avance : {rep['avance']}")

    st.divider()
    c1, c2 = st.columns(2)
    c1.download_button(
        "⬇️ Exporter le recap (payées)",
        data=rapport.build_recap_xlsx(data, only_paid=True),
        file_name="recap_paiements.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
    c2.download_button(
        "⬇️ Exporter la base complète",
        data=rapport.build_recap_xlsx(data, only_paid=False),
        file_name="base_complete.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    st.divider()
    st.dataframe(
        [{"N°": r["n"], "Date échéance": _fr(r["date_echeance"]), "Mois": r["mois"],
          "Type": r["type"], "Montant (DH)": r["montant"], "Statut": r["statut"],
          "Rappel J-1": _fr(r["rappel_j1"]), "Observations": r["observations"]}
         for r in data],
        use_container_width=True, hide_index=True,
    )
