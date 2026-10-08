"""
app.py — Suivi des virements salaires & CNSS (Streamlit, v5).

Authentification mot de passe + rôles, date au jour (fuseau Casablanca),
stockage Drive durci (erreurs visibles + verrou optimiste), régularité au jour.
Voir conception_app_suivi_virements_v5.md.
"""
from __future__ import annotations

import html
import json

import streamlit as st

import auth
import dates
import db_gen
import integrity
import rapport
import storage

st.set_page_config(page_title="Suivi virements & CNSS", page_icon="💸", layout="wide")

# --- Authentification (porte) ---------------------------------------------- #
role = auth.login()
if not role:
    st.stop()

CAN_WRITE = auth.is_admin(role)

st.markdown("""
<style>
.block-container {padding-top: 2rem;}
.carte {border:1px solid #d9dee8; border-radius:12px; padding:14px 16px; margin-bottom:12px;}
.carte h4 {margin:0 0 4px 0; font-size:0.95rem;}
.montant {font-size:1.35rem; font-weight:700;}
.badge {display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.78rem; font-weight:600;}
.b-venir {background:#FFF3CD; color:#8A6D00;}
.b-retard {background:#F8D7DA; color:#842029;}
.b-paye {background:#D1E7DD; color:#0F5132;}
.sub {color:#6c757d; font-size:0.82rem;}
</style>
""", unsafe_allow_html=True)


# --- Chargement + réconciliation ------------------------------------------- #
def _charger():
    today = dates.aujourdhui()
    try:
        data, revision = storage.load()
        st.session_state["readonly"] = False
        st.session_state["drive_error"] = None
    except storage.DriveError as e:
        # Panne Drive : lecture seule, on ne risque pas d'écraser la base distante
        data = st.session_state.get("data", [])
        revision = st.session_state.get("revision")
        st.session_state["readonly"] = True
        st.session_state["drive_error"] = str(e)
    data, report = integrity.reconcile(data, today)
    if report["modifie"] and not st.session_state.get("readonly"):
        ok, revision, err = storage.save(data, revision)
        if not ok:
            st.session_state["readonly"] = True
            st.session_state["drive_error"] = err
    st.session_state["data"] = data
    st.session_state["revision"] = revision
    st.session_state["diag"] = report


if "data" not in st.session_state:
    _charger()


def _data():
    return st.session_state["data"]


def _readonly() -> bool:
    return bool(st.session_state.get("readonly"))


def _persister(data):
    """Réconcilie et sauvegarde avec verrou optimiste. Gère conflit et erreur."""
    today = dates.aujourdhui()
    data, report = integrity.reconcile(data, today)
    ok, revision, err = storage.save(data, st.session_state.get("revision"))
    if not ok and err == "conflit":
        # Quelqu'un a écrit entre-temps : recharger la source, prévenir, ne pas écraser
        st.session_state["revision"] = revision
        _charger()
        st.warning("Conflit d'écriture : la base a changé ailleurs. "
                   "Rechargée — refais ton action si besoin.")
        return
    if not ok:
        st.session_state["readonly"] = True
        st.session_state["drive_error"] = err
        st.error(f"Sauvegarde impossible : {err}. Passage en lecture seule.")
        return
    st.session_state["data"] = data
    st.session_state["revision"] = revision
    st.session_state["diag"] = report


def _fr(iso: str) -> str:
    import datetime as dt
    try:
        return dt.date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso or ""


def _dh(montant) -> str:
    return f"{int(montant):,}".replace(",", " ") + " DH"


# --- Paiement (canal unique, admin) ---------------------------------------- #
def _appliquer_paiement(n: int):
    today = dates.aujourdhui().isoformat()
    data = _data()
    for rec in data:
        if rec["n"] == n:
            reg = integrity.regularite(today, rec["date_echeance"])
            rec["statut"] = integrity.statut_paye(reg)
            rec["date_paiement"] = today
            rec["observations"] = f"Payé le {_fr(today)} ({reg})"
            break
    _persister(data)


@st.dialog("Confirmer le paiement")
def dlg_payer(rec: dict):
    today = dates.aujourdhui().isoformat()
    reg = integrity.regularite(today, rec["date_echeance"])
    if reg != integrity.REG_A_TEMPS:
        st.warning(f"⚠️ Ce paiement sera marqué **{reg}** "
                   f"(échéance {_fr(rec['date_echeance'])}, aujourd'hui {_fr(today)}).")
    st.write(f"**{rec['type']}** — {rec['mois']}")
    st.write(f"Montant : **{_dh(rec['montant'])}**")
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
                r["date_paiement"] = None
                r["observations"] = ""
                break
        _persister(data)
        st.rerun()
    if c2.button("Annuler", use_container_width=True):
        st.rerun()


@st.dialog("Remplacer toute la base")
def dlg_remplacer(imported: list):
    st.warning(f"⚠️ Remplacement **total** de la base par {len(imported)} "
               f"enregistrement(s) importé(s). Les données actuelles seront écrasées.")
    c1, c2 = st.columns(2)
    if c1.button("Remplacer", use_container_width=True, type="primary"):
        _persister(imported)
        st.rerun()
    if c2.button("Annuler", use_container_width=True):
        st.rerun()


# --- Composants ------------------------------------------------------------- #
def _badge(rec: dict, today) -> str:
    if integrity.est_paye(rec):
        return '<span class="badge b-paye">✅ ' + html.escape(rec["statut"]) + "</span>"
    if integrity.est_en_retard(rec, today):
        return '<span class="badge b-retard">🔴 En retard</span>'
    return '<span class="badge b-venir">🟡 À venir</span>'


def _carte(rec: dict, today, actions: bool = True):
    st.markdown(
        f'<div class="carte"><h4>{html.escape(rec["type"])}</h4>'
        f'<div class="sub">{html.escape(rec["mois"])} · échéance {_fr(rec["date_echeance"])} '
        f'· rappel {_fr(rec["rappel_j1"])}</div>'
        f'<div class="montant">{_dh(rec["montant"])}</div>{_badge(rec, today)}</div>',
        unsafe_allow_html=True,
    )
    if actions and CAN_WRITE and not integrity.est_paye(rec):
        if st.button("💰 Payer", key=f"pay_{rec['n']}", use_container_width=True):
            dlg_payer(rec)


# --- Sidebar ---------------------------------------------------------------- #
today = dates.aujourdhui()
MOIS_COURANT = db_gen.mois_label(today.year, today.month)

with st.sidebar:
    st.title("💸 Suivi virements & CNSS")
    st.caption(f"Connecté — rôle : **{role}**")
    auth.logout_button()
    if _readonly():
        st.error("🔒 Lecture seule (erreur de stockage).")
    st.info(f"📅 Mois courant : **{MOIS_COURANT}** (figé)")

    panneau = st.radio("Navigation",
                       ["🔜 À venir", "📅 Mois courant", "🔔 Rappels", "📊 Récap & export"],
                       label_visibility="collapsed")

    if CAN_WRITE and not _readonly():
        st.divider()
        with st.container(border=True):
            st.markdown("#### ⚠️ Régularisation / nouveau mois")
            annees = list(range(today.year - 2, today.year + 3))
            ca, cm = st.columns(2)
            an = ca.selectbox("Année", annees, index=annees.index(today.year))
            moi = cm.selectbox("Mois", list(db_gen.MOIS_FR.keys()), index=today.month - 1,
                               format_func=lambda m: db_gen.MOIS_FR[m])
            label_sel = db_gen.mois_label(an, moi)
            if label_sel == MOIS_COURANT:
                st.caption("→ Utilisez le panneau « 📅 Mois courant ».")
            elif not db_gen.mois_present(_data(), label_sel):
                if st.button(f"➕ Déclarer {label_sel}", use_container_width=True):
                    d, _, msg = db_gen.ajouter_mois(_data(), an, moi)
                    _persister(d)
                    st.toast(msg)
                    st.rerun()
            else:
                st.caption(f"« {label_sel} » déjà déclaré :")
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
                        raise ValueError("Le fichier doit contenir une liste.")
                    if mode == "Remplacer":
                        dlg_remplacer(imported)
                    else:
                        # Fusion : ne JAMAIS rétrograder un payé en non payé
                        par_cle = {db_gen.cle(r): r for r in _data()}
                        for r in imported:
                            k = db_gen.cle(r)
                            anc = par_cle.get(k)
                            if anc and integrity.est_paye(anc) and not integrity.est_paye(r):
                                continue  # on garde le paiement existant
                            par_cle[k] = r
                        _persister(list(par_cle.values()))
                        st.rerun()
                except (json.JSONDecodeError, ValueError) as e:
                    st.error(f"Import impossible : {e}")

    st.divider()
    d = st.session_state.get("diag", {})
    with st.expander("🔎 Diagnostic"):
        st.caption(f"Persistance : **{storage.mode_label()}** · "
                   f"révision : {st.session_state.get('revision') or '—'}")
        if st.session_state.get("drive_error"):
            st.error(st.session_state["drive_error"])
        st.write(f"Total : {d.get('total',0)} · Payées : {d.get('payes',0)} · "
                 f"Non payées : {d.get('non_payes',0)} · En retard : {d.get('en_retard',0)}")
        corr = sum(d.get(k, 0) for k in ("doublons", "rejetes", "rappels_corriges",
                                         "montants_corriges", "mois_corriges", "statuts_corriges"))
        if corr:
            st.caption(f"Réparations au chargement : {corr} "
                       f"(doublons {d.get('doublons',0)}, rejets {d.get('rejetes',0)}, "
                       f"montants {d.get('montants_corriges',0)}, mois {d.get('mois_corriges',0)}, "
                       f"statuts {d.get('statuts_corriges',0)})")
        if st.button("🔄 Recharger depuis la source"):
            _charger()
            st.rerun()


# --- Corps ------------------------------------------------------------------ #
data = _data()

if not data:
    st.header("Bienvenue 👋")
    if not CAN_WRITE:
        st.info("Base vide. Un super admin doit déclarer le premier mois.")
        st.stop()
    st.write("Aucune donnée. Déclarez votre **premier mois** pour démarrer.")
    ca, cm, cb = st.columns(3)
    an = ca.selectbox("Année", list(range(today.year - 2, today.year + 3)), index=2, key="i_an")
    moi = cm.selectbox("Mois", list(db_gen.MOIS_FR.keys()), index=today.month - 1,
                       format_func=lambda m: db_gen.MOIS_FR[m], key="i_moi")
    cb.write("")
    if cb.button("➕ Déclarer ce mois", use_container_width=True, type="primary"):
        newd, _, _ = db_gen.ajouter_mois(data, an, moi)
        _persister(newd)
        st.rerun()
    st.stop()


if panneau == "🔜 À venir":
    st.header("🔜 Paiements à venir")
    non_payes = [r for r in data if not integrity.est_paye(r)]
    echus = sorted([r for r in non_payes if integrity.est_en_retard(r, today)],
                   key=lambda r: r["date_echeance"])
    a_venir = sorted([r for r in non_payes if not integrity.est_en_retard(r, today)],
                     key=lambda r: r["date_echeance"])[:6]
    if echus:
        st.subheader(f"🔴 En retard ({len(echus)})")
        cols = st.columns(3)
        for i, rec in enumerate(echus):
            with cols[i % 3]:
                _carte(rec, today)
    st.subheader("🟡 Prochaines échéances")
    if not a_venir:
        st.success("Aucune échéance à venir non payée. ✅")
    else:
        cols = st.columns(3)
        for i, rec in enumerate(a_venir):
            with cols[i % 3]:
                _carte(rec, today)


elif panneau == "📅 Mois courant":
    st.header(f"📅 {MOIS_COURANT}")
    du_mois = sorted([r for r in data if r["mois"] == MOIS_COURANT], key=lambda r: r["n"])
    if not du_mois:
        st.warning("Le mois courant n'est pas encore déclaré.")
        if CAN_WRITE and st.button(f"➕ Déclarer {MOIS_COURANT}", type="primary"):
            newd, _, _ = db_gen.ajouter_mois(data, today.year, today.month)
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
                _carte(rec, today)
                if CAN_WRITE and integrity.est_paye(rec):
                    if st.button("↩️ Dévalider", key=f"dev_{rec['n']}"):
                        dlg_devalider(rec)


elif panneau == "🔔 Rappels":
    st.header("🔔 Rappels J-1 (échéances non payées)")
    a_rappeler = sorted([r for r in data if not integrity.est_paye(r)],
                        key=lambda r: r["rappel_j1"])
    if not a_rappeler:
        st.success("Aucun rappel en attente.")
    else:
        st.dataframe(
            [{"Rappel J-1": _fr(r["rappel_j1"]), "Échéance": _fr(r["date_echeance"]),
              "Mois": r["mois"], "Type": r["type"], "Montant (DH)": r["montant"],
              "État": "🔴 en retard" if integrity.est_en_retard(r, today) else "🟡 à venir"}
             for r in a_rappeler],
            use_container_width=True, hide_index=True,
        )
    st.download_button(
        "⬇️ Exporter les rappels (.ics)",
        data=rapport.build_ics(data, only_unpaid=True),
        file_name="rappels_salaires_cnss.ics", mime="text/calendar",
        use_container_width=True,
    )


else:  # Récap & export
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

    rep = {r: 0 for r in ("à temps", "retard", "avance")}
    for r in payes:
        for k in rep:
            if r["statut"].endswith(k):
                rep[k] += 1
    st.caption(f"Régularité — à temps : {rep['à temps']} · retard : {rep['retard']} · "
               f"avance : {rep['avance']}")

    st.divider()
    c1, c2, c3 = st.columns(3)
    c1.download_button("⬇️ Recap (payées)", rapport.build_recap_xlsx(data, True),
                       "recap_paiements.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
    c2.download_button("⬇️ Base complète", rapport.build_recap_xlsx(data, False),
                       "base_complete.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
    c3.download_button("⬇️ Rappels (.ics)", rapport.build_ics(data, True),
                       "rappels_salaires_cnss.ics", "text/calendar",
                       use_container_width=True)

    st.divider()
    st.dataframe(
        [{"N°": r["n"], "Date échéance": _fr(r["date_echeance"]), "Mois": r["mois"],
          "Type": r["type"], "Montant (DH)": r["montant"], "Statut": r["statut"],
          "Rappel J-1": _fr(r["rappel_j1"]), "Observations": r["observations"]}
         for r in data],
        use_container_width=True, hide_index=True,
    )
