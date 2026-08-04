"""
H2READY TOOLKIT - Tool 2.6 unificato
app_h2ready.py - Interfaccia: scheda di compilazione, dimensionamento, schede di output.

Progetto Interreg Italia-Slovenia H2READY - APE FVG
Autore: Matteo De Piccoli

Tre modalita' di analisi condividono lo stesso motore (core.py):
  1. DOMANDA    - dal target di idrogeno agli impianti e alle superfici necessarie
  2. SUPERFICI  - dalle superfici disponibili all'idrogeno producibile
  3. COPERTURA  - entrambi, per misurare quanta parte del fabbisogno il territorio copre

I parametri si compilano in una scheda e il dimensionamento parte con un bottone:
senza, ogni movimento di uno slider farebbe ripartire la simulazione su 8760 ore.

E' possibile aggiungere il profilo orario misurato di un impianto gia' in esercizio
(idroelettrico, biomasse, cogenerazione), che si somma al fotovoltaico e all'eolico
dimensionati dal tool. Attenzione: un impianto esistente di norma non e' addizionale
ai sensi dell'Atto Delegato (UE) 2023/1184 e riduce la quota di idrogeno certificabile.
"""

import io
import os
import json
import requests
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import core
from i18n import LINGUE, testi

WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbwpP0x0hBnhOadXA43IieWg9EusAuhaafpyeXpyaStssDd7Qo-jwnuOttAllzz8r5JS/exec"

st.set_page_config(page_title="H2READY - Produzione idrogeno verde", layout="wide")

lang = LINGUE[st.sidebar.selectbox(testi("it")["lang_label"], list(LINGUE.keys()))]


class _Testi(dict):
    """Una chiave di traduzione mancante non deve uccidere la pagina.

    E' il difetto che teneva invisibile il blocco di esportazione: un KeyError
    dentro una scheda interrompe il rendering di tutto cio' che segue, senza
    che si capisca perche'. Qui la chiave assente viene mostrata com'e',
    ben visibile fra parentesi uncinate, e la pagina prosegue. Non si usano
    parentesi graffe perche' verrebbero interpretate da .format().
    """

    def __missing__(self, k):
        return "\u27e8" + str(k) + "\u27e9"


t = _Testi(testi(lang))

# ==================================================================
# TESTI AGGIUNTIVI (non presenti in i18n.py)
# ==================================================================
TX = {
    "it": {
        "back": "← Modifica parametri",
        "recap": "**{m}** · zona {z}{e}",
        "back": "← Edit parameters",
        "recap": "**{m}** · zone {z}{e}",
        "back": "← Uredi parametre",
        "recap": "**{m}** · cona {z}{e}",
        "setup": "📝 Scheda di compilazione",
        "setup_hint": "Compila i parametri, poi avvia il dimensionamento. La simulazione gira su 8.760 ore: parte solo quando lo chiedi.",
        "run": "🚀 Avvia dimensionamento",
        "rerun": "🔄 Ricalcola con i nuovi parametri",
        "waiting": "Compila la scheda nella barra laterale e premi **Avvia dimensionamento**.",
        "ext_head": "🏭 Impianto già esistente",
        "ext_on": "Aggiungi un impianto già in esercizio",
        "ext_help": "Idroelettrico, biomasse, cogenerazione: un impianto reale la cui produzione si somma a quella dei nuovi impianti.",
        "ext_file": "Profilo orario (.xlsx o .csv)",
        "ext_file_help": "Due colonne: ora (0-8759) e potenza_kW. Scarica il template dal progetto.",
        "ext_mw": "Potenza nominale [MW]",
        "ext_cfd": "Costo dell'energia [€/MWh] (default: idroelettrico ad acqua fluente)",
        "ext_conn": "Collegato all'elettrolizzatore con linea diretta",
        "ext_km": "Distanza dall'elettrolizzatore [km]",
        "ext_add": "Impianto addizionale ai sensi RED III",
        "ext_add_help": "Da spuntare solo se l'impianto è entrato in esercizio da meno di 36 mesi e non percepisce incentivi. Nella grande maggioranza dei casi un impianto esistente NON lo è.",
        "ext_ok": "✅ Profilo caricato: {mw:.2f} MW · {e:,.0f} MWh/anno · {h:,.0f} ore equivalenti",
        "ext_ko": "❌ Profilo non utilizzabile",
        "ext_warn_h": "⚠️ {h:,.0f} ore equivalenti: fuori dalla forchetta tipica per questa fonte ({a:,.0f}-{b:,.0f} h). Verifica il dato prima di usarlo.",
        "ext_fonte": "Fonte",
        "ext_notadd": "⚠️ **L'impianto esistente non è addizionale**: la quota di idrogeno prodotta con la sua energia non è certificabile RFNBO. È la conseguenza dell'Atto Delegato (UE) 2023/1184, non un limite del modello.",
        "ext_serie": "Impianto esistente (MW)",
        "over": "⚠️ **Il solo impianto esistente supera il target.** Produce {p:,.1f} ton/anno contro le {q:,.1f} richieste ({s:+.0f}%). Il dimensionamento si ferma alla sua potenza: non servono nuovi impianti.",
        "iter": "Punto fisso convergiuto in {k} iterazioni: la taglia totale dipende dal profilo combinato, che a sua volta dipende dalla taglia.",
        "bm_head": "📏 Che cosa significa questa quantità",
        "bm_nahv": "Target NAHV 2030 [ton/anno]",
        "bm_nahv_help": "Lasciare a 0 se il dato ufficiale non è disponibile: la voce non verrà mostrata.",
        "bm_pniec_ind": "dell'obiettivo nazionale 2030 per l'industria",
        "bm_pniec_tot": "dell'obiettivo nazionale 2030 complessivo",
        "bm_nahv_lbl": "del target NAHV 2030",
        "bm_eq": "Equivale al consumo annuo di:",
        "bm_bus": "autobus urbani a idrogeno",
        "bm_truck": "camion pesanti a lungo raggio",
        "bm_forno": "forni industriali di vetreria o ceramica",
        "bm_note": "Riferimenti nazionali: PNIEC 2024, consumi di idrogeno rinnovabile al 2030 (0,115 Mton all'industria, 0,252 Mton complessive). Gli equivalenti fisici sono ordini di grandezza.",
    },
    "en": {
        "setup": "📝 Input sheet", "setup_hint": "Fill in the parameters, then start the sizing. The simulation runs over 8,760 hours: it starts only when you ask.",
        "run": "🚀 Start sizing", "rerun": "🔄 Recalculate with new parameters",
        "waiting": "Fill in the sheet in the sidebar and press **Start sizing**.",
        "ext_head": "🏭 Existing plant", "ext_on": "Add a plant already in operation",
        "ext_help": "Hydro, biomass, cogeneration: a real plant whose output adds to the new ones.",
        "ext_file": "Hourly profile (.xlsx or .csv)",
        "ext_file_help": "Two columns: hour (0-8759) and potenza_kW. Download the project template.",
        "ext_mw": "Rated power [MW]",
        "ext_cfd": "Energy cost [€/MWh] (default: run-of-river hydro)",
        "ext_conn": "Connected to the electrolyser via direct line",
        "ext_km": "Distance from the electrolyser [km]",
        "ext_add": "Plant is additional under RED III",
        "ext_add_help": "Tick only if the plant started operating less than 36 months ago and receives no support. Most existing plants are NOT.",
        "ext_ok": "✅ Profile loaded: {mw:.2f} MW · {e:,.0f} MWh/yr · {h:,.0f} equivalent hours",
        "ext_ko": "❌ Profile unusable",
        "ext_warn_h": "⚠️ {h:,.0f} equivalent hours: outside the typical range for this source ({a:,.0f}-{b:,.0f} h). Check the data first.",
        "ext_fonte": "Source",
        "ext_notadd": "⚠️ **The existing plant is not additional**: hydrogen produced with its energy cannot be certified as RFNBO. This follows Delegated Act (EU) 2023/1184, not a model limitation.",
        "ext_serie": "Existing plant (MW)",
        "over": "⚠️ **The existing plant alone exceeds the target.** It produces {p:,.1f} t/yr against {q:,.1f} required ({s:+.0f}%). Sizing stops at its rated power: no new plants are needed.",
        "iter": "Fixed point converged in {k} iterations: total size depends on the combined profile, which in turn depends on size.",
        "bm_head": "📏 What this quantity means",
        "bm_nahv": "NAHV 2030 target [t/yr]", "bm_nahv_help": "Leave at 0 if the official figure is unavailable: the item will be hidden.",
        "bm_pniec_ind": "of the 2030 national target for industry",
        "bm_pniec_tot": "of the overall 2030 national target",
        "bm_nahv_lbl": "of the NAHV 2030 target",
        "bm_eq": "Equivalent to the annual consumption of:",
        "bm_bus": "urban hydrogen buses", "bm_truck": "long-haul heavy trucks",
        "bm_forno": "industrial glass or ceramic furnaces",
        "bm_note": "National references: PNIEC 2024, renewable hydrogen consumption to 2030 (0.115 Mt industry, 0.252 Mt total). Physical equivalents are orders of magnitude.",
    },
    "sl": {
        "setup": "📝 Vnosni list", "setup_hint": "Izpolnite parametre, nato zaženite dimenzioniranje. Simulacija teče na 8.760 urah: zažene se le na zahtevo.",
        "run": "🚀 Zaženi dimenzioniranje", "rerun": "🔄 Preračunaj z novimi parametri",
        "waiting": "Izpolnite list v stranski vrstici in pritisnite **Zaženi dimenzioniranje**.",
        "ext_head": "🏭 Obstoječa naprava", "ext_on": "Dodaj napravo, ki že obratuje",
        "ext_help": "Hidroelektrarna, biomasa, soproizvodnja: dejanska naprava, katere proizvodnja se prišteje novim.",
        "ext_file": "Urni profil (.xlsx ali .csv)",
        "ext_file_help": "Dva stolpca: ura (0-8759) in potenza_kW. Prenesite predlogo projekta.",
        "ext_mw": "Nazivna moč [MW]",
        "ext_cfd": "Strošek energije [€/MWh] (privzeto: pretočna hidroelektrarna)",
        "ext_conn": "Povezana z elektrolizerjem po neposrednem vodu",
        "ext_km": "Oddaljenost od elektrolizerja [km]",
        "ext_add": "Naprava je dodatna po RED III",
        "ext_add_help": "Označite le, če naprava obratuje manj kot 36 mesecev in ne prejema podpore. Večina obstoječih naprav to NI.",
        "ext_ok": "✅ Profil naložen: {mw:.2f} MW · {e:,.0f} MWh/leto · {h:,.0f} ekvivalentnih ur",
        "ext_ko": "❌ Profil ni uporaben",
        "ext_warn_h": "⚠️ {h:,.0f} ekvivalentnih ur: zunaj običajnega razpona za ta vir ({a:,.0f}-{b:,.0f} h). Preverite podatek.",
        "ext_fonte": "Vir",
        "ext_notadd": "⚠️ **Obstoječa naprava ni dodatna**: vodika, proizvedenega z njeno energijo, ni mogoče certificirati kot RFNBO. To izhaja iz Delegirane uredbe (EU) 2023/1184.",
        "ext_serie": "Obstoječa naprava (MW)",
        "over": "⚠️ **Že sama obstoječa naprava presega cilj.** Proizvede {p:,.1f} t/leto proti zahtevanim {q:,.1f} ({s:+.0f}%). Dimenzioniranje se ustavi pri njeni moči.",
        "iter": "Fiksna točka je konvergirala v {k} iteracijah.",
        "bm_head": "📏 Kaj ta količina pomeni",
        "bm_nahv": "Cilj NAHV 2030 [t/leto]", "bm_nahv_help": "Pustite 0, če uradni podatek ni na voljo.",
        "bm_pniec_ind": "nacionalnega cilja 2030 za industrijo",
        "bm_pniec_tot": "skupnega nacionalnega cilja 2030",
        "bm_nahv_lbl": "cilja NAHV 2030",
        "bm_eq": "Ustreza letni porabi:",
        "bm_bus": "mestnih vodikovih avtobusov", "bm_truck": "težkih tovornjakov na dolge razdalje",
        "bm_forno": "industrijskih steklarskih ali keramičnih peči",
        "bm_note": "Nacionalne reference: PNIEC 2024 (0,115 Mt industrija, 0,252 Mt skupaj). Fizični ekvivalenti so velikostni razredi.",
    },
}
tx = TX.get(lang, TX["it"])

# Riferimenti nazionali documentati (PNIEC 2024, consumi H2 rinnovabile al 2030)
PNIEC_INDUSTRIA_TON = 115_000.0
PNIEC_TOTALE_TON = 252_000.0
# Equivalenti fisici: ordini di grandezza, non valori puntuali
EQ_BUS_TON, EQ_CAMION_TON, EQ_FORNO_TON = 9.0, 8.0, 3000.0


# ==================================================================
# INTESTAZIONE
# ==================================================================
st.title(t["title"])
st.caption(t["credits"])
st.markdown("""
    <p style='font-size: 0.8rem; color: gray;'>
        🌐 Progetto: <a href='https://www.ita-slo.eu/en/h2ready' target='_blank'>Interreg H2Ready</a> |
        🏠 Sito Ente: <a href='https://www.ape.fvg.it/' target='_blank'>APE FVG</a> |
        📧 Contatto: <a href='mailto:matteo.depiccoli@ape.fvg.it'>matteo.depiccoli@ape.fvg.it</a>
    </p>
""", unsafe_allow_html=True)

profili, esito_dati = core.carica_profili()

# ==================================================================
# STATO DELLA PAGINA
# Due fasi: la scheda di compilazione e i risultati. I parametri non
# vivono nei widget ma in un dizionario proprio: quando il modulo esce
# dalla vista Streamlit dimentica i valori dei widget, non quelli in
# session_state sotto una chiave nostra.
# ==================================================================
if "fase" not in st.session_state:
    st.session_state["fase"] = "scheda"
C = st.session_state.get("cfg", {})


def dv(chiave, predefinito):
    """Valore da riproporre: quello gia' scelto, altrimenti il predefinito."""
    return C.get(chiave, predefinito)


def di(chiave, opzioni, predefinito):
    """Indice da riproporre per selectbox e radio."""
    opzioni = list(opzioni)
    v = C.get(chiave, predefinito)
    return opzioni.index(v) if v in opzioni else opzioni.index(predefinito)


MODI_CONN = ["diretta", "rete"]
FONTI_EXT = {
    "idro_fluente": "Idroelettrico ad acqua fluente",
    "idro_bacino": "Idroelettrico a bacino",
    "biomasse": "Biomasse",
    "cogenerazione": "Cogenerazione",
    "eolico": "Eolico",
    "fotovoltaico": "Fotovoltaico",
    "altro": "Altro",
}

# ==================================================================
# FASE 1 - SCHEDA DI COMPILAZIONE
# ==================================================================
if st.session_state["fase"] == "scheda":

    with st.expander(t["readme_expander"]):
        nome_md = f"README_metodologia_{lang}.md"
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), nome_md),
                      "r", encoding="utf-8") as f:
                st.markdown(f.read())
        except FileNotFoundError:
            st.warning(t["readme_missing"].format(f=nome_md))

    if esito_dati["ok"]:
        st.caption(f"{t['data_ok']}: `{esito_dati['file_pv']}` · `{esito_dati['file_wind']}`")
    else:
        st.error(t["data_ko"])
        with st.expander(t["data_diag"]):
            if esito_dati["mancanti"]:
                st.write(t["data_diag_cols"])
                st.code("\n".join(esito_dati["mancanti"]))
            if esito_dati["errore"]:
                st.write(f"{t['data_diag_err']} `{esito_dati['errore']}`")
            st.info(t["data_diag_hint"])

    st.markdown("---")
    st.header(tx["setup"])
    st.caption(tx["setup_hint"])

    # --- Scelte che cambiano la forma della scheda: fuori dal modulo,
    #     perche' devono reagire subito.
    c1, c2 = st.columns([3, 2])
    with c1:
        modalita = st.radio(t["mode_label"], ["domanda", "superfici", "copertura"],
                            index=di("modalita", ["domanda", "superfici", "copertura"], "domanda"),
                            format_func=lambda k: t[f"mode_{k}"], horizontal=True)
    with c2:
        zona = st.selectbox(t["sb_zona"], ["nord", "sud"],
                            index=di("zona", ["nord", "sud"], "nord"),
                            format_func=lambda k: t[f"zona_{k}"])
    st.info(t[f"mode_help_{modalita}"])

    usa_superfici = modalita in ("superfici", "copertura")
    usa_domanda = modalita in ("domanda", "copertura")

    # --- Impianto esistente: il caricamento va validato subito ---
    with st.expander(tx["ext_head"], expanded=bool(dv("ext_on", False))):
        ext_on = st.checkbox(tx["ext_on"], value=dv("ext_on", False), help=tx["ext_help"])
        ext_norm, ext_mw, ext_fonte = None, 0.0, "idro_fluente"
        if ext_on:
            e1, e2, e3 = st.columns([3, 2, 2])
            with e1:
                up = st.file_uploader(tx["ext_file"], type=["xlsx", "csv"], help=tx["ext_file_help"])
            with e2:
                ext_fonte = st.selectbox(tx["ext_fonte"], list(FONTI_EXT.keys()),
                                         index=di("ext_fonte", list(FONTI_EXT.keys()), "idro_fluente"),
                                         format_func=lambda k: FONTI_EXT[k])
            with e3:
                mw_dich = st.number_input(tx["ext_mw"], 0.0, 500.0, dv("ext_mw", 11.0), step=0.5)

            if up is not None:
                st.session_state["ext_raw"] = up.getvalue()
                st.session_state["ext_nome"] = up.name
            raw = st.session_state.get("ext_raw")

            if raw is not None:
                buf_ext = io.BytesIO(raw)
                buf_ext.name = st.session_state.get("ext_nome", "profilo.xlsx")
                ext_norm, ext_mw, ext_diag = core.leggi_profilo_esterno(
                    buf_ext, mw_dich if mw_dich > 0 else None)
                if ext_diag["ok"]:
                    st.success(tx["ext_ok"].format(mw=ext_mw, e=ext_diag["energia_mwh"],
                                                   h=ext_diag["ore_eq"]))
                    a, b = core.ORE_EQ_TIPICHE.get(ext_fonte, (0, 8760))
                    if not (a <= ext_diag["ore_eq"] <= b):
                        st.warning(tx["ext_warn_h"].format(h=ext_diag["ore_eq"], a=a, b=b))
                    for m in ext_diag["avvisi"]:
                        st.warning(m)
                else:
                    st.error(tx["ext_ko"])
                    for m in ext_diag["messaggi"]:
                        st.caption(f"· {m}")
                    ext_norm, ext_mw = None, 0.0

    # --- Il resto in un modulo: nulla si ricalcola finche' non si preme ---
    with st.form("scheda"):
        tab_imp, tab_conn, tab_sys, tab_red, tab_eco = st.tabs(
            ["🏗️ " + t["sec_impianti"], "🔌 " + t["tab_conn"], "⚡ " + t["sb_ely"],
             "📜 " + t["sb_red"], "💶 " + t["sb_costi"]])

        # ---------- impianti ----------
        with tab_imp:
            target_ton, nahv_target = dv("target_ton", 1000), dv("nahv_target", 0)
            if usa_domanda:
                g1, g2 = st.columns(2)
                target_ton = g1.number_input(t["target_h2"], 1, 1000000, int(dv("target_ton", 1000)))
                nahv_target = g2.number_input(tx["bm_nahv"], 0, 1000000, int(dv("nahv_target", 0)),
                                              step=500, help=tx["bm_nahv_help"])

            q_terra = q_tetti = q_cap = q_wind = 0
            if modalita == "domanda":
                st.caption(t["alloc_help"])
                a1, a2, a3, a4 = st.columns(4)
                q_terra = a1.slider(t["alloc_terra"], 0, 100, int(dv("q_terra", 60)))
                q_tetti = a2.slider(t["alloc_tetti"], 0, 100, int(dv("q_tetti", 10)))
                q_cap = a3.slider(t["alloc_cap"], 0, 100, int(dv("q_cap", 30)))
                q_wind = a4.slider(t["alloc_wind"], 0, 100, int(dv("q_wind", 0)))
                st.markdown("---")

            p1, p2, p3 = st.columns(3)
            with p1:
                st.markdown(f"**{t['sb_terra']}**")
                terra_ha = st.number_input(t["ha"], 0.0, 10000.0, dv("terra_ha", 10.0),
                                           step=0.5) if usa_superfici else 0.0
                terra_use = st.slider(t["use"], 10, 100, int(dv("terra_use", 90)), key="k_terra_use")
                terra_dens = st.slider(t["dens_ha"], 0.3, 1.2, dv("terra_dens", 0.70), step=0.05)
            with p2:
                st.markdown(f"**{t['sb_tetti']}**")
                tetti_m2 = st.number_input(t["m2"], 0.0, 5000000.0, dv("tetti_m2", 20000.0),
                                           step=500.0, key="k_tm2") if usa_superfici else 0.0
                tetti_use = st.slider(t["use"], 10, 100, int(dv("tetti_use", 50)), key="k_tetti_use")
                tetti_dens = st.slider(t["dens_m2"], 0.10, 0.25, dv("tetti_dens", 0.18),
                                       step=0.01, key="k_tetti_dens")
                tetti_resa = st.slider(t["resa"], 70, 105, int(dv("tetti_resa", 96)), key="k_tetti_resa")
                if usa_superfici:
                    tetti_n = st.number_input(t["n_punti"], 0, 1000, int(dv("tetti_n", 10)), key="k_tetti_n")
                    tetti_taglia = None
                else:
                    tetti_n = None
                    tetti_taglia = st.number_input(t["taglia_media"], 3, 1000,
                                                   int(dv("tetti_taglia", 50)), key="k_tetti_tm")
            with p3:
                st.markdown(f"**{t['sb_cap']}**")
                cap_m2 = st.number_input(t["m2"], 0.0, 5000000.0, dv("cap_m2", 50000.0),
                                         step=1000.0, key="k_cm2") if usa_superfici else 0.0
                cap_use = st.slider(t["use"], 10, 100, int(dv("cap_use", 70)), key="k_cap_use")
                cap_dens = st.slider(t["dens_m2"], 0.10, 0.25, dv("cap_dens", 0.18),
                                     step=0.01, key="k_cap_dens")
                cap_resa = st.slider(t["resa"], 70, 105, int(dv("cap_resa", 93)), key="k_cap_resa")
                if usa_superfici:
                    cap_n = st.number_input(t["n_punti"], 0, 500, int(dv("cap_n", 3)), key="k_cap_n")
                    cap_taglia = None
                else:
                    cap_n = None
                    cap_taglia = st.number_input(t["taglia_media"], 10, 5000,
                                                 int(dv("cap_taglia", 500)), key="k_cap_tm")

            st.markdown("---")
            w1, w2, w3 = st.columns(3)
            w1.markdown(f"**{t['sb_wind']}**")
            wind_n = w2.number_input(t["wind_n"], 0, 100, int(dv("wind_n", 0))) if usa_superfici else 0
            wind_p = w3.slider(t["wind_p"], 0.5, 8.0, dv("wind_p", 3.0), step=0.5) if usa_superfici else 3.0

        # ---------- connessioni ----------
        with tab_conn:
            def blocco_conn(titolo, pref, modo_def, km_def, cp_def, ck_def, con_punti):
                st.markdown(f"**{titolo}**")
                x1, x2, x3, x4 = st.columns([2, 2, 2, 2])
                km = x1.slider(t["dist"], 0.1, 30.0, dv(f"{pref}_km", km_def), key=f"k_{pref}_km")
                modo = x2.radio(t["conn_mode"], MODI_CONN,
                                index=di(f"{pref}_modo", MODI_CONN, modo_def),
                                format_func=lambda k: t[f"conn_{k}"], key=f"k_{pref}_mode",
                                horizontal=True)
                cp = ck = 0.0
                if con_punti:
                    cp = x3.number_input(t["c_punto"], 0, 500000, int(dv(f"{pref}_cp", cp_def)),
                                         step=1000, key=f"k_{pref}_cp")
                    ck = x4.number_input(t["c_km"], 0, 500000, int(dv(f"{pref}_ck", ck_def)),
                                         step=5000, key=f"k_{pref}_ck")
                return km, modo, cp, ck

            terra_km, terra_modo, _, _ = blocco_conn(t["sb_terra"], "terra", "diretta", 2.0, 0, 0, False)
            st.markdown("---")
            tetti_km, tetti_modo, tetti_cp, tetti_ck = blocco_conn(t["sb_tetti"], "tetti", "rete", 3.0, 9000, 90000, True)
            st.markdown("---")
            cap_km, cap_modo, cap_cp, cap_ck = blocco_conn(t["sb_cap"], "cap", "diretta", 1.5, 45000, 155000, True)
            st.markdown("---")
            wind_km = st.slider(f"{t['sb_wind']} — {t['dist']}", 0.1, 30.0, dv("wind_km", 5.0), key="k_wind_km")
            terra_dir, tetti_dir, cap_dir = (terra_modo == "diretta"), (tetti_modo == "diretta"), (cap_modo == "diretta")

            if ext_on:
                st.markdown("---")
                st.markdown(f"**{tx['ext_head']}**")
                y1, y2, y3, y4 = st.columns(4)
                ext_cfd = y1.number_input(tx["ext_cfd"], 0.0, 400.0, dv("ext_cfd", 90.0), step=5.0)
                ext_dir = y2.checkbox(tx["ext_conn"], value=dv("ext_dir", False))
                ext_km = y3.slider(tx["ext_km"], 0.1, 30.0, dv("ext_km", 2.0))
                ext_add = y4.checkbox(tx["ext_add"], value=dv("ext_add", False), help=tx["ext_add_help"])
            else:
                ext_cfd, ext_dir, ext_km, ext_add = 90.0, False, 0.0, True

        # ---------- elettrolisi, accumulo, stoccaggio, compressione ----------
        with tab_sys:
            s1, s2 = st.columns(2)
            with s1:
                st.markdown(f"**{t['sb_bess']}**")
                bess_on = st.toggle(t["bess_on"], value=dv("bess_on", True))
                bess_ratio = st.slider(t["bess_ratio"], 0.0, 5.0, dv("bess_ratio", 3.0), step=0.5)
                st.markdown(f"**{t['sb_stocc']}**")
                stocc_perc = st.slider(t["stocc_perc"], 0.0, 50.0, dv("stocc_perc", 1.0))
                stocc_capex = st.slider(t["stocc_capex"], 100, 1500, int(dv("stocc_capex", 600)))
            with s2:
                st.markdown(f"**{t['sb_ely']}**")
                ely_auto = st.radio(t["ely_mode"], [True, False],
                                    index=di("ely_auto", [True, False], True),
                                    format_func=lambda k: t["ely_auto"] if k else t["ely_man"],
                                    horizontal=True)
                ely_pct = st.slider(t["ely_ratio"], 10, 120, int(dv("ely_pct", 60)), step=5)
                st.markdown(f"**{t['sb_comp']}**")
                comp_tipo = st.selectbox(t["comp_tipo"], ["standard", "booster"],
                                         index=di("comp_tipo", ["standard", "booster"], "standard"),
                                         format_func=lambda k: "Standard (500 bar)" if k == "standard"
                                         else "Booster (700 bar)")

        # ---------- RED III ----------
        with tab_red:
            r1, r2 = st.columns(2)
            with r1:
                red_mensile = st.radio(t["red_scen"], [False, True],
                                       index=di("red_mensile", [False, True], False),
                                       format_func=lambda k: t["red_scen_month"] if k else t["red_scen_hour"])
                red_add = st.checkbox(t["red_add"], value=dv("red_add", True))
                red_noaid = st.checkbox(t["red_noaid"], value=dv("red_noaid", True))
                red_zone = st.checkbox(t["red_zone"], value=dv("red_zone", True))
            with r2:
                st.markdown(f"**{t['red_grid_header']}**")
                grid_max_pct = st.slider(t["red_grid_max"], 0, 100, int(dv("grid_max_pct", 0)), step=5)
                grid_price = st.slider(t["red_grid_price"], 20.0, 300.0, dv("grid_price", 110.0))
                grid_cert = st.checkbox(t["red_grid_cert"], value=dv("grid_cert", False))

        # ---------- economia ----------
        with tab_eco:
            k1, k2, k3 = st.columns(3)
            with k1:
                st.markdown(f"**{t['energy_model']}**")
                autoprod = st.radio(t["energy_model"], [False, True],
                                    index=di("autoprod", [False, True], False),
                                    format_func=lambda k: t["model_own"] if k else t["model_ppa"],
                                    label_visibility="collapsed")
                paga_assorbita = st.checkbox(t["pay_absorbed"], value=dv("paga_assorbita", False),
                                             help=t["pay_help"])
                cfd_pv = st.slider("CfD PV (€/MWh)", 30.0, 120.0, dv("cfd_pv", 60.0))
                cfd_wind = st.slider("CfD Wind (€/MWh)", 30.0, 150.0, dv("cfd_wind", 80.0))
                oneri_rete = st.slider(t["wheel"], 0.0, 80.0, dv("oneri_rete", 25.0))
            with k2:
                st.markdown("**CAPEX**")
                capex_ely = st.slider("CAPEX Ely (€/kW)", 500, 2000, int(dv("capex_ely", 1000)))
                capex_batt = st.slider("CAPEX BESS (€/kWh)", 100, 500, int(dv("capex_batt", 150)))
                capex_pv_terra = st.slider("CAPEX PV terra (€/kW)", 400, 1200, int(dv("capex_pv_terra", 700)))
                capex_pv_tetti = st.slider("CAPEX PV tetti (€/kW)", 500, 1800, int(dv("capex_pv_tetti", 1000)))
                capex_pv_cap = st.slider("CAPEX PV capannoni (€/kW)", 500, 1600, int(dv("capex_pv_cap", 850)))
                capex_wind_kw = st.slider("CAPEX Wind (€/kW)", 900, 2500, int(dv("capex_wind_kw", 1500)))
            with k3:
                st.markdown(f"**{t['sb_mercato']}**")
                prezzo_h2 = st.slider(t["prezzo_h2"], 2.0, 20.0, dv("prezzo_h2", 8.0))
                prezzo_h2_nc = st.slider(t["prezzo_h2_nc"], 1.0, 15.0, dv("prezzo_h2_nc", 4.0))

        st.markdown("")
        avvia = st.form_submit_button(tx["run"], type="primary", use_container_width=True)

    st.caption(f"⚙️ {t['numba_on'] if core.NUMBA_OK else t['numba_off']}")

    if avvia:
        st.session_state["cfg"] = dict(
            modalita=modalita, zona=zona, target_ton=target_ton, nahv_target=nahv_target,
            q_terra=q_terra, q_tetti=q_tetti, q_cap=q_cap, q_wind=q_wind,
            terra_ha=terra_ha, terra_use=terra_use, terra_dens=terra_dens,
            terra_km=terra_km, terra_modo=terra_modo,
            tetti_m2=tetti_m2, tetti_use=tetti_use, tetti_dens=tetti_dens, tetti_resa=tetti_resa,
            tetti_n=tetti_n, tetti_taglia=tetti_taglia, tetti_km=tetti_km, tetti_modo=tetti_modo,
            tetti_cp=tetti_cp, tetti_ck=tetti_ck,
            cap_m2=cap_m2, cap_use=cap_use, cap_dens=cap_dens, cap_resa=cap_resa,
            cap_n=cap_n, cap_taglia=cap_taglia, cap_km=cap_km, cap_modo=cap_modo,
            cap_cp=cap_cp, cap_ck=cap_ck,
            wind_n=wind_n, wind_p=wind_p, wind_km=wind_km,
            ext_on=ext_on, ext_mw=ext_mw, ext_fonte=ext_fonte, ext_cfd=ext_cfd,
            ext_dir=ext_dir, ext_km=ext_km, ext_add=ext_add,
            bess_on=bess_on, bess_ratio=bess_ratio, ely_auto=ely_auto, ely_pct=ely_pct,
            comp_tipo=comp_tipo, stocc_perc=stocc_perc, stocc_capex=stocc_capex,
            red_mensile=red_mensile, red_add=red_add, red_noaid=red_noaid, red_zone=red_zone,
            grid_max_pct=grid_max_pct, grid_price=grid_price, grid_cert=grid_cert,
            autoprod=autoprod, paga_assorbita=paga_assorbita, cfd_pv=cfd_pv, cfd_wind=cfd_wind,
            oneri_rete=oneri_rete, capex_ely=capex_ely, capex_batt=capex_batt,
            capex_pv_terra=capex_pv_terra, capex_pv_tetti=capex_pv_tetti,
            capex_pv_cap=capex_pv_cap, capex_wind_kw=capex_wind_kw,
            prezzo_h2=prezzo_h2, prezzo_h2_nc=prezzo_h2_nc,
        )
        st.session_state["fase"] = "risultati"
        st.rerun()

    st.stop()

# ==================================================================
# FASE 2 - RISULTATI
# I parametri si rileggono dal dizionario, non dai widget: quelli non
# esistono piu' in questa fase.
# ==================================================================
C = st.session_state["cfg"]

nav1, nav2 = st.columns([1, 4])
if nav1.button(tx["back"], use_container_width=True):
    st.session_state["fase"] = "scheda"
    st.rerun()
nav2.caption(tx["recap"].format(
    m=t[f"mode_{C['modalita']}"], z=t[f"zona_{C['zona']}"],
    e=(f" · {tx['ext_serie']} {C['ext_mw']:.1f} MW" if C["ext_mw"] > 0 else "")))

modalita, zona = C["modalita"], C["zona"]
usa_superfici = modalita in ("superfici", "copertura")
usa_domanda = modalita in ("domanda", "copertura")

target_ton, nahv_target = C["target_ton"], C["nahv_target"]
q_terra, q_tetti, q_cap, q_wind = C["q_terra"], C["q_tetti"], C["q_cap"], C["q_wind"]
terra_ha, terra_use, terra_dens = C["terra_ha"], C["terra_use"], C["terra_dens"]
terra_km, terra_dir = C["terra_km"], C["terra_modo"] == "diretta"
tetti_m2, tetti_use, tetti_dens, tetti_resa = C["tetti_m2"], C["tetti_use"], C["tetti_dens"], C["tetti_resa"]
tetti_n, tetti_taglia, tetti_km = C["tetti_n"], C["tetti_taglia"], C["tetti_km"]
tetti_dir, tetti_cp, tetti_ck = C["tetti_modo"] == "diretta", C["tetti_cp"], C["tetti_ck"]
cap_m2, cap_use, cap_dens, cap_resa = C["cap_m2"], C["cap_use"], C["cap_dens"], C["cap_resa"]
cap_n, cap_taglia, cap_km = C["cap_n"], C["cap_taglia"], C["cap_km"]
cap_dir, cap_cp, cap_ck = C["cap_modo"] == "diretta", C["cap_cp"], C["cap_ck"]
wind_n, wind_p, wind_km = C["wind_n"], C["wind_p"], C["wind_km"]
ext_mw, ext_cfd, ext_dir, ext_km, ext_add = C["ext_mw"], C["ext_cfd"], C["ext_dir"], C["ext_km"], C["ext_add"]
bess_on, bess_ratio, ely_auto, ely_pct = C["bess_on"], C["bess_ratio"], C["ely_auto"], C["ely_pct"]
comp_tipo, stocc_perc, stocc_capex = C["comp_tipo"], C["stocc_perc"], C["stocc_capex"]
red_mensile, red_add, red_noaid, red_zone = C["red_mensile"], C["red_add"], C["red_noaid"], C["red_zone"]
grid_max_pct, grid_price, grid_cert = C["grid_max_pct"], C["grid_price"], C["grid_cert"]
autoprod, paga_assorbita = C["autoprod"], C["paga_assorbita"]
cfd_pv, cfd_wind, oneri_rete = C["cfd_pv"], C["cfd_wind"], C["oneri_rete"]
capex_ely, capex_batt = C["capex_ely"], C["capex_batt"]
capex_pv_terra, capex_pv_tetti, capex_pv_cap = C["capex_pv_terra"], C["capex_pv_tetti"], C["capex_pv_cap"]
capex_wind_kw, prezzo_h2, prezzo_h2_nc = C["capex_wind_kw"], C["prezzo_h2"], C["prezzo_h2_nc"]

# Il profilo dell'impianto esistente si ricostruisce dai byte conservati.
ext_norm = None
if ext_mw > 0 and st.session_state.get("ext_raw") is not None:
    _b = io.BytesIO(st.session_state["ext_raw"])
    _b.name = st.session_state.get("ext_nome", "profilo.xlsx")
    ext_norm, ext_mw, _ = core.leggi_profilo_esterno(_b, ext_mw)

target_kg = float(target_ton) * 1000.0
inc_comp, cons_comp = (0.24, 2.23) if comp_tipo == "standard" else (0.42, 4.11)
eff_sistema = core.KWH_KG_ELY + cons_comp
somma_ext = float(ext_norm.sum()) if ext_norm is not None else 0.0

if usa_superfici:
    mw_terra = terra_ha * (terra_use / 100.0) * terra_dens
    mw_tetti = tetti_m2 * (tetti_use / 100.0) * tetti_dens / 1000.0
    mw_cap = cap_m2 * (cap_use / 100.0) * cap_dens / 1000.0
    mw_wind = wind_n * wind_p
    mw_nuovi = mw_terra + mw_tetti + mw_cap + mw_wind
    if mw_nuovi + ext_mw <= 0:
        st.warning(t["warn_nosurf"])
        st.stop()
    quote_rel = ({"terra": mw_terra / mw_nuovi, "tetti": mw_tetti / mw_nuovi,
                  "capannoni": mw_cap / mw_nuovi, "eolico": mw_wind / mw_nuovi}
                 if mw_nuovi > 0 else {"terra": 0.0, "tetti": 0.0, "capannoni": 0.0, "eolico": 0.0})
    taglia_fissa = mw_nuovi + ext_mw
else:
    somma_q = q_terra + q_tetti + q_cap + q_wind
    if somma_q <= 0:
        st.warning(t["warn_noalloc"])
        st.stop()
    if target_kg <= 0:
        st.warning(t["warn_notarget"])
        st.stop()
    quote_rel = {"terra": q_terra / somma_q, "tetti": q_tetti / somma_q,
                 "capannoni": q_cap / somma_q, "eolico": q_wind / somma_q}
    taglia_fissa = None

P = {
    "eff_sistema": eff_sistema, "inc_comp": inc_comp,
    "resa_tetti": tetti_resa / 100.0, "resa_cap": cap_resa / 100.0,
    "somma_pv": 0.0, "somma_wind": 0.0, "somma_ext": somma_ext,
    "bess_on": bess_on, "bess_ratio": bess_ratio,
    "scenario_mensile": red_mensile, "grid_cert": grid_cert,
    "red_add": red_add, "red_noaid": red_noaid, "red_zone": red_zone,
    "autoproduzione": autoprod, "paga_solo_assorbita": paga_assorbita,
    "cfd_pv": cfd_pv, "cfd_wind": cfd_wind, "cfd_esterno": ext_cfd,
    "oneri_rete": oneri_rete, "grid_price": grid_price,
    "capex_ely": capex_ely, "capex_batt": capex_batt, "capex_pv_terra": capex_pv_terra,
    "capex_pv_tetti": capex_pv_tetti, "capex_pv_cap": capex_pv_cap, "capex_wind": capex_wind_kw,
    "perc_stoccaggio": stocc_perc, "capex_stocc": stocc_capex,
    "prezzo_h2": prezzo_h2, "prezzo_h2_nc": prezzo_h2_nc,
    "dens_terra": terra_dens, "use_terra": terra_use,
    "dens_tetti": tetti_dens, "use_tetti": tetti_use,
    "dens_cap": cap_dens, "use_cap": cap_use,
    "esterno_addizionale": bool(ext_add),
}

S = {
    "terra": {"km": terra_km, "diretta": terra_dir, "n": 1, "taglia_media": None, "c_punto": 0, "c_km": 0},
    "tetti": {"km": tetti_km, "diretta": tetti_dir, "n": tetti_n, "taglia_media": tetti_taglia,
              "c_punto": tetti_cp, "c_km": tetti_ck},
    "capannoni": {"km": cap_km, "diretta": cap_dir, "n": cap_n, "taglia_media": cap_taglia,
                  "c_punto": cap_cp, "c_km": cap_ck},
    "eolico": {"km": wind_km, "diretta": True, "n": 1, "taglia_media": None, "c_punto": 0, "c_km": 0},
    "esterno": {"km": ext_km, "diretta": ext_dir, "n": 1, "taglia_media": None, "c_punto": 0, "c_km": 155000},
}

RATIOS = np.round(np.arange(0.10, 1.21, 0.05), 2)
batt_fn = lambda q: (bess_ratio * (q["terra"] + q["tetti"] + q["capannoni"])) if bess_on else 0.0
n_iter = 1

with st.spinner(""):
    if modalita == "domanda" and ext_mw > 0:
        # Il profilo combinato dipende dalla taglia totale, che dipende dal profilo:
        # si risolve con un punto fisso (vedi core.risolvi_domanda).
        P["somma_pv"] = float((profili["pv_nord"] if zona == "nord" else profili["pv_sud"]).sum())
        P["somma_wind"] = float((profili["wind_nord"] if zona == "nord" else profili["wind_sud"]).sum())
        esiti, quote, gen_norm, prof_pv, prof_wind, n_iter = core.risolvi_domanda(
            profili, zona, quote_rel, tetti_resa / 100.0, cap_resa / 100.0,
            ext_norm, ext_mw, target_kg, batt_fn, grid_max_pct, RATIOS, P, S)
        taglia_fn = lambda r: max(core.scala_per_domanda(r, target_kg, eff_sistema), ext_mw)
    else:
        quote = core.quote_con_esterno(quote_rel, ext_mw, taglia_fissa) if taglia_fissa \
            else {**quote_rel, "esterno": 0.0}
        gen_norm, prof_pv, prof_wind = core.profilo_normalizzato(
            profili, zona, quote, tetti_resa / 100.0, cap_resa / 100.0, ext_norm)
        P["somma_pv"], P["somma_wind"] = float(prof_pv.sum()), float(prof_wind.sum())
        batt_per_mw = batt_fn(quote)
        df_tec = core.scan_tecnico(gen_norm, batt_per_mw, grid_max_pct, RATIOS)
        taglia_fn = (lambda r: taglia_fissa) if taglia_fissa \
            else (lambda r: core.scala_per_domanda(r, target_kg, eff_sistema))
        esiti = core.ottimizza(df_tec, taglia_fn, quote, P, S)

if not esiti:
    st.warning(t["warn_nosurf"])
    st.stop()

P["somma_pv"], P["somma_wind"] = float(prof_pv.sum()), float(prof_wind.sum())
batt_per_mw = batt_fn(quote)
df_tec = core.scan_tecnico(gen_norm, batt_per_mw, grid_max_pct, RATIOS)

ratio_scelto = min(esiti, key=lambda v: v["lcoh"])["ratio"] if ely_auto else ely_pct / 100.0
riga, fer_h_u, grid_h_u, soc_h_u, curt_h_u = core.aggregati_e_dettaglio(
    gen_norm, float(ratio_scelto), batt_per_mw, grid_max_pct)
taglia_fer = taglia_fn(riga)
R = core.valuta(riga, taglia_fer, quote, P, S)

gen_h = gen_norm * taglia_fer
fer_h, grid_h, soc_h, curt_h = (a * taglia_fer for a in (fer_h_u, grid_h_u, soc_h_u, curt_h_u))
h2_h = (fer_h + grid_h) * 1000.0 / eff_sistema
ext_h = ext_norm * R["mw"]["esterno"] if ext_norm is not None else None

df_sens = pd.DataFrame({"pct": [v["ratio"] * 100 for v in esiti],
                        "lcoh": [v["lcoh"] for v in esiti],
                        "h2": [v["prod_h2"] / 1000 for v in esiti]})

# ==================================================================
# AVVISI DI CONTESTO
# ==================================================================
if ext_mw > 0:
    if not ext_add:
        st.warning(tx["ext_notadd"])
    if usa_domanda and R["prod_h2"] > target_kg * 1.01:
        st.warning(tx["over"].format(p=R["prod_h2"] / 1000, q=target_kg / 1000,
                                     s=(R["prod_h2"] / target_kg - 1) * 100))
    if n_iter > 1:
        st.caption(tx["iter"].format(k=n_iter))

# ==================================================================
# KPI PRINCIPALI
# ==================================================================
st.markdown("---")
k1, k2, k3, k4 = st.columns(4)
k1.metric(t["prod_h2"], f"{R['prod_h2']/1000:,.1f} ton/y")
k2.metric(t["lcoh"], f"€ {R['lcoh']:.2f} /kg")
k3.metric(t["capex"], f"€ {R['capex_tot']/1e6:.2f} MLN")
k4.metric(t["red_share"], f"{R['quota_rfnbo']:.0f}%")

# ------------------------------------------------------------------
# BENCHMARK: a che cosa corrisponde questa quantita' di idrogeno
# ------------------------------------------------------------------
if usa_domanda:
    st.subheader(tx["bm_head"])
    ton = R["prod_h2"] / 1000.0
    voci = [(ton / PNIEC_INDUSTRIA_TON * 100, tx["bm_pniec_ind"]),
            (ton / PNIEC_TOTALE_TON * 100, tx["bm_pniec_tot"])]
    if nahv_target > 0:
        voci.insert(0, (ton / nahv_target * 100, tx["bm_nahv_lbl"]))
    cols = st.columns(len(voci))
    for c, (v, lbl) in zip(cols, voci):
        c.metric(lbl, f"{v:.2f}%" if v < 10 else f"{v:.1f}%")

    st.markdown(f"**{tx['bm_eq']}**")
    e1, e2, e3 = st.columns(3)
    e1.metric(tx["bm_bus"], f"{ton/EQ_BUS_TON:,.0f}")
    e2.metric(tx["bm_truck"], f"{ton/EQ_CAMION_TON:,.0f}")
    e3.metric(tx["bm_forno"], f"{ton/EQ_FORNO_TON:,.2f}")
    st.caption(tx["bm_note"])

if modalita == "copertura":
    copertura = R["prod_h2"] / target_kg * 100 if target_kg > 0 else 0.0
    st.subheader(t["sec_copertura"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t["cop_quota"], f"{copertura:.1f}%")
    c2.metric(t["cop_prod"], f"{R['prod_h2']/1000:,.1f} ton/y")
    c3.metric(t["cop_target"], f"{target_kg/1000:,.1f} ton/y")
    deficit = max(target_kg - R["prod_h2"], 0.0)
    c4.metric(t["cop_gap"], f"{deficit/1000:,.1f} ton/y")
    if deficit <= 0:
        st.success(t["cop_ok"].format(m=copertura - 100))
    else:
        st.warning(t["cop_ko"].format(q=copertura))
        k = deficit / R["prod_h2"] if R["prod_h2"] > 0 else 0.0
        extra = []
        if terra_ha > 0:
            extra.append(f"{t['cat_terra']}: +{terra_ha*k:,.1f} ha")
        if tetti_m2 > 0:
            extra.append(f"{t['cat_tetti']}: +{tetti_m2*k:,.0f} m²")
        if cap_m2 > 0:
            extra.append(f"{t['cat_capannoni']}: +{cap_m2*k:,.0f} m²")
        if extra:
            st.caption(f"{t['cop_extra']} — " + " · ".join(extra))

tab_tec, tab_eco, tab_red, tab_dati = st.tabs([t["tab_tec"], t["tab_eco"], t["tab_red"], t["tab_dati"]])

# ==================================================================
# TAB TECNICA
# ==================================================================
with tab_tec:
    st.subheader(t["sec_impianti"])
    a1, a2, a3, a4 = st.columns(4)
    a1.metric(t["cat_terra"], f"{R['mw']['terra']:,.2f} MWp")
    a2.metric(t["cat_tetti"], f"{R['mw']['tetti']:,.2f} MWp")
    a3.metric(t["cat_capannoni"], f"{R['mw']['capannoni']:,.2f} MWp")
    a4.metric(t["fer_tot"], f"{taglia_fer:,.2f} MW", f"+ {R['mw']['eolico']:,.1f} MW {t['cat_eolico']}")
    if R["mw"]["esterno"] > 0:
        st.info(f"{tx['ext_serie']}: **{R['mw']['esterno']:,.2f} MW** · "
                f"{R['e_cat']['esterno']/1000:,.2f} GWh/y "
                f"({R['e_cat']['esterno']/R['e_prodotta']*100:.0f}% "
                f"{'della generazione' if lang == 'it' else 'of generation'})")

    if not usa_superfici:
        st.markdown("---")
        st.subheader(t["sec_superfici_req"])
        req = core.superfici_richieste(R["mw"], P)
        b1, b2, b3 = st.columns(3)
        b1.metric(t["cat_terra"], f"{req['ha_terra']:,.1f} ha")
        b2.metric(t["cat_tetti"], f"{req['m2_tetti']:,.0f} m²")
        b3.metric(t["cat_capannoni"], f"{req['m2_capannoni']:,.0f} m²")

    st.markdown("---")
    st.subheader(t["sec_h2"])
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t["ely_size"], f"{R['ely_mw']:,.2f} MW", f"{R['ratio']*100:.0f}% FER")
    c2.metric(t["ore_anno"], f"{R['ore_eq']:,.0f} h/y", f"CF {R['ore_eq']/8760*100:.1f}%")
    c3.metric(t["prod_h2"], f"{R['prod_h2']/1000:,.1f} ton/y", f"{R['prod_h2']/365:,.0f} kg/g")
    c4.metric(t["stocc_massa"], f"{(R['prod_h2']*stocc_perc/100)/1000:,.2f} ton")

    st.markdown("---")
    st.subheader(t["sec_energia"])
    e_pv = sum(R["e_cat"][k] for k in ("terra", "tetti", "capannoni"))
    d1, d2, d3, d4 = st.columns(4)
    d1.metric(t["e_pv"], f"{e_pv/1000:,.2f} GWh/y")
    d2.metric(t["e_wind"], f"{R['e_cat']['eolico']/1000:,.2f} GWh/y")
    d3.metric(t["e_fer_abs"], f"{R['e_fer']/1000:,.2f} GWh/y")
    d4.metric(t["e_grid"], f"{R['e_grid']/1000:,.2f} GWh/y",
              f"{R['e_grid']/R['e_tot']*100:.1f}%" if R["e_tot"] > 0 else "0%")

    st.markdown("<br>", unsafe_allow_html=True)
    f1, f2, f3, f4 = st.columns(4)
    f1.metric(t["bess_cap"], f"{R['batt_mwh']:,.1f} MWh")
    f2.metric(t["curt"], f"{R['e_curt']/1000:,.2f} GWh/y", f"-{R['perc_curt']:.1f}%", delta_color="inverse")
    f3.metric(t["comp_cons"], f"{cons_comp:,.2f} kWh/kg")
    f4.metric(t["eff_sistema"], f"{eff_sistema:,.2f} kWh/kg")

    st.markdown("---")
    st.subheader(t["sec_rese"])
    q_h2 = R["prod_h2"] / R["e_prodotta"] if R["e_prodotta"] > 0 else 0.0
    sup = core.superfici_richieste(R["mw"], P) if not usa_superfici else {
        "ha_terra": terra_ha, "m2_tetti": tetti_m2, "m2_capannoni": cap_m2}
    g1, g2, g3, g4 = st.columns(4)
    g1.metric(t["y_ha"], f"{R['e_cat']['terra']*q_h2/sup['ha_terra']:,.0f} kg/ha/y" if sup["ha_terra"] > 0 else "-")
    g2.metric(t["y_m2_tetti"], f"{R['e_cat']['tetti']*q_h2/sup['m2_tetti']:,.2f} kg/m²/y" if sup["m2_tetti"] > 0 else "-")
    g3.metric(t["y_m2_cap"], f"{R['e_cat']['capannoni']*q_h2/sup['m2_capannoni']:,.2f} kg/m²/y" if sup["m2_capannoni"] > 0 else "-")
    g4.metric(t["y_mw"], f"{R['prod_h2']/taglia_fer:,.0f} kg/MW/y")

    st.markdown("---")
    st.markdown(t["chart_8760"])
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Scattergl(y=gen_h, name="FER (MW)", line=dict(color='#FFC107', width=1)), secondary_y=False)
    if ext_h is not None:
        fig.add_trace(go.Scattergl(y=ext_h, name=tx["ext_serie"],
                                   line=dict(color='#1E88E5', width=1)), secondary_y=False)
    fig.add_trace(go.Scattergl(y=fer_h, name="Ely ← FER (MW)", line=dict(color='#D32F2F', width=2)), secondary_y=False)
    if R["e_grid"] > 0:
        fig.add_trace(go.Scattergl(y=grid_h, name="Ely ← rete (MW)", line=dict(color='#9C27B0', width=1)), secondary_y=False)
    if R["batt_mwh"] > 0:
        fig.add_trace(go.Scattergl(y=soc_h, name="BESS SOC (MWh)", line=dict(color='#4CAF50', dash='dash')), secondary_y=True)
    fig.update_layout(height=420, margin=dict(t=20, b=20), legend=dict(orientation="h", y=1.12))
    st.plotly_chart(fig, width="stretch")

    h1, h2 = st.columns(2)
    with h1:
        st.markdown(t["chart_mese"])
        dati_m = {"m": core.MESI, "FER": fer_h, "Rete": grid_h, "Curtailment": curt_h}
        df_m = pd.DataFrame(dati_m).groupby("m").sum() / 1000.0
        fig_m = px.bar(df_m, barmode="stack", labels={"value": "GWh", "m": ""},
                       color_discrete_map={"FER": "#00897B", "Rete": "#9C27B0", "Curtailment": "#BDBDBD"})
        fig_m.update_layout(height=330, margin=dict(t=20, b=20), legend=dict(orientation="h", y=1.15, title=""))
        st.plotly_chart(fig_m, width="stretch")
    with h2:
        st.markdown(t["chart_sens"])
        fig_s = make_subplots(specs=[[{"secondary_y": True}]])
        fig_s.add_trace(go.Scatter(x=df_sens["pct"], y=df_sens["lcoh"], name="LCOH (€/kg)",
                                   line=dict(color='#D32F2F', width=3)), secondary_y=False)
        fig_s.add_trace(go.Scatter(x=df_sens["pct"], y=df_sens["h2"], name="H2 (ton/y)",
                                   line=dict(color='#1976D2', dash='dot')), secondary_y=True)
        fig_s.add_vline(x=R["ratio"] * 100, line_dash="dash", line_color="green")
        fig_s.update_layout(height=330, margin=dict(t=20, b=20), legend=dict(orientation="h", y=1.15))
        st.plotly_chart(fig_s, width="stretch")

# ==================================================================
# TAB ECONOMIA
# ==================================================================
with tab_eco:
    st.subheader(t["sec_fin"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t["lcoh"], f"€ {R['lcoh']:.2f} / kg")
    m2.metric(t["capex"], f"€ {R['capex_tot']/1e6:.2f} MLN")
    m3.metric(t["payback"], f"{R['payback']:.1f} y" if R["payback"] < 50 else t["loss"])
    m4.metric(t["ricavi"], f"€ {R['ricavi']/1e6:.2f} MLN/y")

    valori = [R["c_ely"], R["c_batt"], R["c_stocc"], R["c_comp"], R["c_conn"], R["c_fer"]]
    p1, p2 = st.columns(2)
    with p1:
        st.markdown(t["pie_title"])
        df_pie = pd.DataFrame({"v": t["voci"], "x": valori})
        df_pie = df_pie[df_pie["x"] > 0]
        fig_pie = px.pie(df_pie, values="x", names="v", hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(height=380, margin=dict(t=10, b=10), showlegend=False)
        st.plotly_chart(fig_pie, width="stretch")
    with p2:
        st.markdown(t["tab_costi"])
        tot = R["capex_tot"] if R["capex_tot"] > 0 else 1.0
        righe = [{t["col_voce"]: v, t["col_costo"]: f"{c:,.0f}", t["col_quota"]: f"{c/tot*100:.1f}%"}
                 for v, c in zip(t["voci"], valori)]
        for lab, val in [(t["opex_fer"], R["opex_fer"]), (t["opex_wheel"], R["opex_wheel"]),
                         (t["opex_grid"], R["opex_grid"]), (t["opex_maint"], R["opex_maint"])]:
            righe.append({t["col_voce"]: lab, t["col_costo"]: f"{val:,.0f}", t["col_quota"]: "-"})
        st.table(pd.DataFrame(righe))

    st.markdown(t["tab_conn"])
    rows = []
    for d in R["dettaglio_conn"]:
        if d["mw"] <= 0:
            continue
        nome = tx["ext_serie"] if d["cat"] == "esterno" else t[f"cat_{d['cat']}"]
        rows.append({
            t["col_sito"]: nome, t["col_mw"]: f"{d['mw']:,.2f}",
            t["col_punti"]: d["n"], t["col_mode"]: t["conn_diretta"] if d["diretta"] else t["conn_rete"],
            t["col_km"]: f"{d['km']:,.1f}", t["col_liv"]: d["liv"], t["col_capex"]: f"{d['capex']:,.0f}",
        })
    if rows:
        st.table(pd.DataFrame(rows))

    st.error(t["disclaimer"])

# ==================================================================
# TAB RED III
# ==================================================================
with tab_red:
    st.subheader(t["sec_red"])
    if not R["prereq"]:
        st.error(t["red_ko"])
    elif R["quota_rfnbo"] > 99.9:
        st.success(t["red_ok"])
    else:
        st.warning(t["red_partial"])

    r1, r2, r3 = st.columns(3)
    r1.metric(t["red_share"], f"{R['quota_rfnbo']:.1f}%", f"{R['h2_rfnbo']/1000:,.1f} ton/y")
    r2.metric(t["red_nc"], f"{R['h2_nc']/1000:,.1f} ton/y")
    r3.metric(t["co2"], f"{R['co2']:,.0f} ton CO₂/y")

    if grid_cert:
        stato = t["red_t_cert"]
    elif R["e_grid"] <= 0:
        stato = t["red_t_all"]
    elif R["e_grid_ok"] >= R["e_grid"] - 1e-6:
        stato = t["red_t_month"]
    else:
        stato = t["red_t_part"]

    check = [(t["red_c_add"], red_add), (t["red_c_aid"], red_noaid),
             (t["red_c_zone"], red_zone), (t["red_c_bess"], R["ok_bess"])]
    if R["mw"]["esterno"] > 0:
        check.append((tx["ext_add"], R["ok_esterno"]))
    st.markdown("\n".join(f"- {'✅' if ok else '❌'} {n}" for n, ok in check)
                + f"\n- ℹ️ **{t['red_c_time']}**: {stato}")
    if not R["ok_bess"] and R["e_disc_ko"] > 0:
        st.caption(t["red_bess_ko"].format(e=R["e_disc_ko"] / 1000.0))
    if not R["ok_esterno"] and R["e_esterno_ko"] > 0:
        st.caption(f"⚠️ {R['e_esterno_ko']/1000:,.2f} GWh/y "
                   f"{'esclusi dalla certificazione perché provenienti dall’impianto esistente' if lang == 'it' else 'excluded from certification: from the existing plant'}.")

# ==================================================================
# TAB DATI ED EXPORT
# ==================================================================
with tab_dati:
    st.markdown(t["riepilogo"])
    riepilogo = {
        t["mode_label"]: t[f"mode_{modalita}"],
        t["fer_tot"]: f"{taglia_fer:,.2f} MW",
        tx["ext_serie"]: f"{R['mw']['esterno']:,.2f} MW",
        t["ely_size"]: f"{R['ely_mw']:,.2f} MW",
        t["bess_cap"]: f"{R['batt_mwh']:,.1f} MWh",
        t["prod_h2"]: f"{R['prod_h2']/1000:,.1f} ton/y",
        t["red_share"]: f"{R['quota_rfnbo']:.1f}%",
        t["curt"]: f"{R['perc_curt']:.1f}%",
        t["lcoh"]: f"€ {R['lcoh']:.2f}/kg",
        t["capex"]: f"€ {R['capex_tot']/1e6:.2f} MLN",
        t["payback"]: f"{R['payback']:.1f} y" if float(R["payback"]) < 50 else t["loss"],
    }
    st.table(pd.DataFrame(riepilogo.items(), columns=[t["col_voce"], "—"]))

    buf = io.StringIO()
    colonne = {"ora": np.arange(core.ORE), "FER_MW": gen_h, "Ely_FER_MW": fer_h,
               "Ely_Rete_MW": grid_h, "Curtailment_MW": curt_h, "BESS_SOC_MWh": soc_h, "H2_kg": h2_h}
    if ext_h is not None:
        colonne["Impianto_esistente_MW"] = ext_h
    pd.DataFrame(colonne).to_csv(buf, index=False)
    st.download_button(t["dl_hourly"], buf.getvalue(),
                       file_name="H2READY_profilo_orario.csv", mime="text/csv")

# ==================================================================
# ESPORTAZIONE NEL DATABASE CENTRALE
# Fuori dalle schede: resta visibile anche se una chiave di traduzione
# manca dentro tab_dati.
# ==================================================================
st.markdown("---")
st.header("💾 Esportazione")

codice = st.text_input("Codice identificativo del Comune (es. 030043):", key="id_istat_export")

if st.button("💾 Esporta nel database centrale", type="primary"):
    if not codice:
        st.error("Inserisci il codice identificativo prima di procedere.")
    else:
        payload = {
            "ID_ISTAT": str(codice),
            "T26_MODALITA": str(modalita),
            "T26_ZONA": str(zona),
            "T26_PV_TERRA_MW": float(round(R["mw"]["terra"], 2)),
            "T26_PV_TETTI_MW": float(round(R["mw"]["tetti"], 2)),
            "T26_PV_CAPANNONI_MW": float(round(R["mw"]["capannoni"], 2)),
            "T26_EOLICO_MW": float(round(R["mw"]["eolico"], 2)),
            "T26_TAGLIA_FER_INSTALLATA_MW": float(round(taglia_fer, 2)),
            "T26_TAGLIA_ELETTROLIZZATORE_MW": float(round(R["ely_mw"], 2)),
            "T26_CAPACITA_BESS_MWH": float(round(R["batt_mwh"], 2)),
            "T26_PRODUZIONE_H2_TON_ANNO": float(round(R["prod_h2"] / 1000, 2)),
            "T26_QUOTA_RFNBO_PERC": float(round(R["quota_rfnbo"], 1)),
            "T26_CURTAILMENT_PERC": float(round(R["perc_curt"], 1)),
            "T26_CAPEX_CONNESSIONI_EURO": float(round(R["c_conn"], 0)),
            "T26_CAPEX_TOTALE_MLN": float(round(R["capex_tot"] / 1e6, 2)),
            "T26_LCOH_EURO_KG": float(round(R["lcoh"], 2)),
            "T26_CO2_EVITATA_TON_ANNO": float(round(R["co2"], 0)),
        }
        if usa_domanda:
            payload["T26_TARGET_H2_TON"] = float(round(target_kg / 1000, 2))
        if float(R["payback"]) < 99:
            payload["T26_PAYBACK_ANNI"] = float(round(R["payback"], 1))
        if usa_superfici:
            payload["T26B_SUP_TERRA_HA"] = float(round(terra_ha, 2))
            payload["T26B_SUP_TETTI_M2"] = float(round(tetti_m2, 0))
            payload["T26B_SUP_CAPANNONI_M2"] = float(round(cap_m2, 0))
        else:
            req_exp = core.superfici_richieste(R["mw"], P)
            payload["T26B_SUP_TERRA_HA"] = float(round(req_exp["ha_terra"], 2))
            payload["T26B_SUP_TETTI_M2"] = float(round(req_exp["m2_tetti"], 0))
            payload["T26B_SUP_CAPANNONI_M2"] = float(round(req_exp["m2_capannoni"], 0))
        if modalita == "copertura" and target_kg > 0:
            payload["T26_COPERTURA_PERC"] = float(round(R["prod_h2"] / target_kg * 100, 1))

        try:
            resp = requests.post(WEBHOOK_URL, data=json.dumps(payload),
                                 headers={"Content-Type": "application/json"}, timeout=60)
            if resp.status_code in (200, 201):
                st.success("✅ Dati trasmessi correttamente al database centrale.")
                st.caption(f"Risposta del server: {resp.text}")
                st.balloons()
            else:
                st.error(f"Errore di sincronizzazione (codice {resp.status_code})")
        except requests.exceptions.ReadTimeout:
            st.warning("⏳ Il server non ha risposto in tempo. Quasi sempre significa che i dati "
                       "sono stati scritti: controlla il foglio prima di ripetere l'invio.")
        except Exception as e:
            st.error(f"Errore di connessione al database: {e}")
