"""
H2READY TOOLKIT - Tool 2.6 unificato
app_h2ready.py - Interfaccia: selezione della modalita', input, schede di output.

Progetto Interreg Italia-Slovenia H2READY - APE FVG
Autore: Matteo De Piccoli

Tre modalita' di analisi condividono lo stesso motore (core.py):
  1. DOMANDA    - dal target di idrogeno agli impianti e alle superfici necessarie
  2. SUPERFICI  - dalle superfici disponibili all'idrogeno producibile
  3. COPERTURA  - entrambi, per misurare quanta parte del fabbisogno il territorio copre

La modalita' e' scelta con un radio, non con st.tabs: Streamlit eseguirebbe
il contenuto di tutte le schede, raddoppiando le simulazioni a ogni interazione.
Le schede sono usate solo per l'output, dove i risultati sono gia' calcolati.
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
t = testi(lang)

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

with st.expander(t["readme_expander"]):
    nome_md = f"README_metodologia_{lang}.md"
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), nome_md), "r", encoding="utf-8") as f:
            st.markdown(f.read())
    except FileNotFoundError:
        st.warning(t["readme_missing"].format(f=nome_md))

# ==================================================================
# DATASET
# ==================================================================
profili, esito = core.carica_profili()
if esito["ok"]:
    st.caption(f"{t['data_ok']}: `{esito['file_pv']}` · `{esito['file_wind']}`")
else:
    st.error(t["data_ko"])
    with st.expander(t["data_diag"]):
        if esito["mancanti"]:
            st.write(t["data_diag_cols"])
            st.code("\n".join(esito["mancanti"]))
        if esito["errore"]:
            st.write(f"{t['data_diag_err']} `{esito['errore']}`")
        st.info(t["data_diag_hint"])

# ==================================================================
# MODALITA'
# ==================================================================
st.sidebar.header(t["mode_header"])
modalita = st.sidebar.radio(t["mode_label"], ["domanda", "superfici", "copertura"],
                            format_func=lambda k: t[f"mode_{k}"])
st.info(t[f"mode_help_{modalita}"])

usa_superfici = modalita in ("superfici", "copertura")
usa_domanda = modalita in ("domanda", "copertura")

zona = st.sidebar.selectbox(t["sb_zona"], ["nord", "sud"], format_func=lambda k: t[f"zona_{k}"])

# --- target ---
target_kg = 0.0
if usa_domanda:
    st.sidebar.header(t["sb_target"])
    target_kg = st.sidebar.number_input(t["target_h2"], 1, 1000000, 1000, key="target") * 1000.0

# --- allocazione (solo modalita' domanda pura) ---
if modalita == "domanda":
    st.sidebar.header(t["sb_alloc"])
    st.sidebar.caption(t["alloc_help"])
    q_terra = st.sidebar.slider(t["alloc_terra"], 0, 100, 60, key="q_terra")
    q_tetti = st.sidebar.slider(t["alloc_tetti"], 0, 100, 10, key="q_tetti")
    q_cap = st.sidebar.slider(t["alloc_cap"], 0, 100, 30, key="q_cap")
    q_wind = st.sidebar.slider(t["alloc_wind"], 0, 100, 0, key="q_wind")

MODI_CONN = ["diretta", "rete"]


def _conn_widgets(prefisso, default_mode, def_km, def_c_punto, def_c_km, con_punti):
    """Widget di connessione comuni a tutte le categorie."""
    km = st.slider(t["dist"], 0.1, 30.0, def_km, key=f"{prefisso}_km")
    modo = st.radio(t["conn_mode"], MODI_CONN, index=MODI_CONN.index(default_mode),
                    format_func=lambda k: t[f"conn_{k}"], key=f"{prefisso}_mode")
    c_punto = c_km = 0.0
    if con_punti:
        c_punto = st.number_input(t["c_punto"], 0, 500000, def_c_punto, step=1000, key=f"{prefisso}_cp")
        c_km = st.number_input(t["c_km"], 0, 500000, def_c_km, step=5000, key=f"{prefisso}_ck")
    return km, (modo == "diretta"), c_punto, c_km


# --- A TERRA ---
with st.sidebar.expander(t["sb_terra"], expanded=usa_superfici):
    terra_ha = st.number_input(t["ha"], 0.0, 10000.0, 10.0, step=0.5, key="terra_ha") if usa_superfici else 0.0
    terra_use = st.slider(t["use"], 10, 100, 90, key="terra_use")
    terra_dens = st.slider(t["dens_ha"], 0.3, 1.2, 0.70, step=0.05, key="terra_dens")
    terra_km, terra_dir, _, _ = _conn_widgets("terra", "diretta", 2.0, 0, 0, False)

# --- TETTI ---
with st.sidebar.expander(t["sb_tetti"], expanded=usa_superfici):
    tetti_m2 = st.number_input(t["m2"], 0.0, 5000000.0, 20000.0, step=500.0, key="tetti_m2") if usa_superfici else 0.0
    tetti_use = st.slider(t["use"], 10, 100, 50, key="tetti_use")
    tetti_dens = st.slider(t["dens_m2"], 0.10, 0.25, 0.18, step=0.01, key="tetti_dens")
    tetti_resa = st.slider(t["resa"], 70, 105, 96, key="tetti_resa")
    if usa_superfici:
        tetti_n = st.number_input(t["n_punti"], 0, 1000, 10, key="tetti_n")
        tetti_taglia = None
    else:
        tetti_n = None
        tetti_taglia = st.number_input(t["taglia_media"], 3, 1000, 50, key="tetti_tm")
    tetti_km, tetti_dir, tetti_cp, tetti_ck = _conn_widgets("tetti", "rete", 3.0, 9000, 90000, True)

# --- CAPANNONI ---
with st.sidebar.expander(t["sb_cap"], expanded=usa_superfici):
    cap_m2 = st.number_input(t["m2"], 0.0, 5000000.0, 50000.0, step=1000.0, key="cap_m2") if usa_superfici else 0.0
    cap_use = st.slider(t["use"], 10, 100, 70, key="cap_use")
    cap_dens = st.slider(t["dens_m2"], 0.10, 0.25, 0.18, step=0.01, key="cap_dens")
    cap_resa = st.slider(t["resa"], 70, 105, 93, key="cap_resa")
    if usa_superfici:
        cap_n = st.number_input(t["n_punti"], 0, 500, 3, key="cap_n")
        cap_taglia = None
    else:
        cap_n = None
        cap_taglia = st.number_input(t["taglia_media"], 10, 5000, 500, key="cap_tm")
    cap_km, cap_dir, cap_cp, cap_ck = _conn_widgets("cap", "diretta", 1.5, 45000, 155000, True)

# --- EOLICO ---
with st.sidebar.expander(t["sb_wind"], expanded=False):
    if usa_superfici:
        wind_n = st.number_input(t["wind_n"], 0, 100, 0, key="wind_n")
        wind_p = st.slider(t["wind_p"], 0.5, 8.0, 3.0, step=0.5, key="wind_p")
    else:
        wind_n, wind_p = 0, 3.0
    wind_km = st.slider(t["dist"], 0.1, 30.0, 5.0, key="wind_km")

# --- BESS / ELY ---
st.sidebar.header(t["sb_bess"])
bess_on = st.sidebar.toggle(t["bess_on"], value=True)
bess_ratio = st.sidebar.slider(t["bess_ratio"], 0.0, 5.0, 3.0, step=0.5)

st.sidebar.header(t["sb_ely"])
ely_auto = st.sidebar.radio(t["ely_mode"], [True, False],
                            format_func=lambda k: t["ely_auto"] if k else t["ely_man"])
ely_pct = st.sidebar.slider(t["ely_ratio"], 10, 120, 60, step=5, disabled=ely_auto)

# --- RED III ---
st.sidebar.header(t["sb_red"])
red_mensile = st.sidebar.radio(t["red_scen"], [False, True],
                               format_func=lambda k: t["red_scen_month"] if k else t["red_scen_hour"])
red_add = st.sidebar.checkbox(t["red_add"], value=True)
red_noaid = st.sidebar.checkbox(t["red_noaid"], value=True)
red_zone = st.sidebar.checkbox(t["red_zone"], value=True)
st.sidebar.markdown(f"**{t['red_grid_header']}**")
grid_max_pct = st.sidebar.slider(t["red_grid_max"], 0, 100, 0, step=5)
grid_price = st.sidebar.slider(t["red_grid_price"], 20.0, 300.0, 110.0)
grid_cert = st.sidebar.checkbox(t["red_grid_cert"], value=False)

# --- COSTI ---
st.sidebar.header(t["sb_costi"])
autoprod = st.sidebar.radio(t["energy_model"], [False, True],
                            format_func=lambda k: t["model_own"] if k else t["model_ppa"])
paga_assorbita = st.sidebar.checkbox(t["pay_absorbed"], value=False, help=t["pay_help"])
cfd_pv = st.sidebar.slider("CfD PV (€/MWh)", 30.0, 120.0, 60.0)
cfd_wind = st.sidebar.slider("CfD Wind (€/MWh)", 30.0, 150.0, 80.0)
oneri_rete = st.sidebar.slider(t["wheel"], 0.0, 80.0, 25.0)
capex_ely = st.sidebar.slider("CAPEX Ely (€/kW)", 500, 2000, 1000)
capex_batt = st.sidebar.slider("CAPEX BESS (€/kWh)", 100, 500, 150)
capex_pv_terra = st.sidebar.slider("CAPEX PV terra (€/kW)", 400, 1200, 700)
capex_pv_tetti = st.sidebar.slider("CAPEX PV tetti (€/kW)", 500, 1800, 1000)
capex_pv_cap = st.sidebar.slider("CAPEX PV capannoni (€/kW)", 500, 1600, 850)
capex_wind_kw = st.sidebar.slider("CAPEX Wind (€/kW)", 900, 2500, 1500)

st.sidebar.header(t["sb_stocc"])
stocc_perc = st.sidebar.slider(t["stocc_perc"], 0.0, 50.0, 1.0)
stocc_capex = st.sidebar.slider(t["stocc_capex"], 100, 1500, 600)

st.sidebar.header(t["sb_comp"])
comp_tipo = st.sidebar.selectbox(t["comp_tipo"], ["standard", "booster"],
                                 format_func=lambda k: "Standard (500 bar)" if k == "standard" else "Booster (700 bar)")
inc_comp, cons_comp = (0.24, 2.23) if comp_tipo == "standard" else (0.42, 4.11)

st.sidebar.header(t["sb_mercato"])
prezzo_h2 = st.sidebar.slider(t["prezzo_h2"], 2.0, 20.0, 8.0)
prezzo_h2_nc = st.sidebar.slider(t["prezzo_h2_nc"], 1.0, 15.0, 4.0)

st.sidebar.caption(f"⚙️ {t['numba_on'] if core.NUMBA_OK else t['numba_off']}")

# ==================================================================
# POTENZE E QUOTE
# ==================================================================
if usa_superfici:
    mw_terra = terra_ha * (terra_use / 100.0) * terra_dens
    mw_tetti = tetti_m2 * (tetti_use / 100.0) * tetti_dens / 1000.0
    mw_cap = cap_m2 * (cap_use / 100.0) * cap_dens / 1000.0
    mw_wind = wind_n * wind_p
    taglia_fissa = mw_terra + mw_tetti + mw_cap + mw_wind
    if taglia_fissa <= 0:
        st.warning(t["warn_nosurf"])
        st.stop()
    quote = {"terra": mw_terra / taglia_fissa, "tetti": mw_tetti / taglia_fissa,
             "capannoni": mw_cap / taglia_fissa, "eolico": mw_wind / taglia_fissa}
else:
    somma_q = q_terra + q_tetti + q_cap + q_wind
    if somma_q <= 0:
        st.warning(t["warn_noalloc"])
        st.stop()
    if target_kg <= 0:
        st.warning(t["warn_notarget"])
        st.stop()
    quote = {"terra": q_terra / somma_q, "tetti": q_tetti / somma_q,
             "capannoni": q_cap / somma_q, "eolico": q_wind / somma_q}
    taglia_fissa = None

gen_norm, prof_pv, prof_wind = core.profilo_normalizzato(
    profili, zona, quote, tetti_resa / 100.0, cap_resa / 100.0)

quota_pv = quote["terra"] + quote["tetti"] + quote["capannoni"]
batt_per_mw = bess_ratio * quota_pv if bess_on else 0.0
eff_sistema = core.KWH_KG_ELY + cons_comp

P = {
    "eff_sistema": eff_sistema, "inc_comp": inc_comp,
    "resa_tetti": tetti_resa / 100.0, "resa_cap": cap_resa / 100.0,
    "somma_pv": float(prof_pv.sum()), "somma_wind": float(prof_wind.sum()),
    "bess_on": bess_on, "bess_ratio": bess_ratio,
    "scenario_mensile": red_mensile, "grid_cert": grid_cert,
    "red_add": red_add, "red_noaid": red_noaid, "red_zone": red_zone,
    "autoproduzione": autoprod, "paga_solo_assorbita": paga_assorbita,
    "cfd_pv": cfd_pv, "cfd_wind": cfd_wind, "oneri_rete": oneri_rete, "grid_price": grid_price,
    "capex_ely": capex_ely, "capex_batt": capex_batt, "capex_pv_terra": capex_pv_terra,
    "capex_pv_tetti": capex_pv_tetti, "capex_pv_cap": capex_pv_cap, "capex_wind": capex_wind_kw,
    "perc_stoccaggio": stocc_perc, "capex_stocc": stocc_capex,
    "prezzo_h2": prezzo_h2, "prezzo_h2_nc": prezzo_h2_nc,
    "dens_terra": terra_dens, "use_terra": terra_use,
    "dens_tetti": tetti_dens, "use_tetti": tetti_use,
    "dens_cap": cap_dens, "use_cap": cap_use,
}

S = {
    "terra": {"km": terra_km, "diretta": terra_dir, "n": 1, "taglia_media": None, "c_punto": 0, "c_km": 0},
    "tetti": {"km": tetti_km, "diretta": tetti_dir, "n": tetti_n, "taglia_media": tetti_taglia,
              "c_punto": tetti_cp, "c_km": tetti_ck},
    "capannoni": {"km": cap_km, "diretta": cap_dir, "n": cap_n, "taglia_media": cap_taglia,
                  "c_punto": cap_cp, "c_km": cap_ck},
    "eolico": {"km": wind_km, "diretta": True, "n": 1, "taglia_media": None, "c_punto": 0, "c_km": 0},
}

# ==================================================================
# SCANSIONE TECNICA (cache) E DIMENSIONAMENTO
# ==================================================================
RATIOS = np.round(np.arange(0.10, 1.21, 0.05), 2)
df_tec = core.scan_tecnico(gen_norm, batt_per_mw, grid_max_pct, RATIOS)

if usa_superfici:
    def taglia_fn(riga):
        return taglia_fissa
else:
    def taglia_fn(riga):
        return core.scala_per_domanda(riga, target_kg, eff_sistema)

esiti = core.ottimizza(df_tec, taglia_fn, quote, P, S)
if not esiti:
    st.warning(t["warn_nosurf"])
    st.stop()

ratio_scelto = min(esiti, key=lambda v: v["lcoh"])["ratio"] if ely_auto else ely_pct / 100.0

riga, fer_h_u, grid_h_u, soc_h_u, curt_h_u = core.aggregati_e_dettaglio(
    gen_norm, float(ratio_scelto), batt_per_mw, grid_max_pct)
taglia_fer = taglia_fn(riga)
R = core.valuta(riga, taglia_fer, quote, P, S)

# serie orarie in scala reale
gen_h = gen_norm * taglia_fer
fer_h, grid_h, soc_h, curt_h = (a * taglia_fer for a in (fer_h_u, grid_h_u, soc_h_u, curt_h_u))
h2_h = (fer_h + grid_h) * 1000.0 / eff_sistema

df_sens = pd.DataFrame({"pct": [v["ratio"] * 100 for v in esiti],
                        "lcoh": [v["lcoh"] for v in esiti],
                        "h2": [v["prod_h2"] / 1000 for v in esiti]})

# ==================================================================
# KPI PRINCIPALI
# ==================================================================
st.markdown("---")
k1, k2, k3, k4 = st.columns(4)
k1.metric(t["prod_h2"], f"{R['prod_h2']/1000:,.1f} ton/y")
k2.metric(t["lcoh"], f"€ {R['lcoh']:.2f} /kg")
k3.metric(t["capex"], f"€ {R['capex_tot']/1e6:.2f} MLN")
k4.metric(t["red_share"], f"{R['quota_rfnbo']:.0f}%")

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
        df_m = pd.DataFrame({"m": core.MESI, "FER": fer_h, "Rete": grid_h, "Curtailment": curt_h}) \
            .groupby("m").sum() / 1000.0
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
        rows.append({
            t["col_sito"]: t[f"cat_{d['cat']}"], t["col_mw"]: f"{d['mw']:,.2f}",
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
    st.markdown("\n".join(f"- {'✅' if ok else '❌'} {n}" for n, ok in check)
                + f"\n- ℹ️ **{t['red_c_time']}**: {stato}")
    if not R["ok_bess"] and R["e_disc_ko"] > 0:
        st.caption(t["red_bess_ko"].format(e=R["e_disc_ko"] / 1000.0))

# ==================================================================
# TAB DATI ED EXPORT (Versione Blindata e Corretta)
# ==================================================================
with tab_dati:
    st.markdown(t["riepilogo"])
    
    # 1. Tabella di Riepilogo
    riepilogo = {
        t["mode_label"]: t[f"mode_{modalita}"],
        t["fer_tot"]: f"{taglia_fer:,.2f} MW",
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

    # 2. Download Profilo Orario (8760 ore)
    buf = io.StringIO()
    pd.DataFrame({
        "ora": np.arange(core.ORE),
        "FER_MW": gen_h,
        "Ely_FER_MW": fer_h,
        "Ely_Rete_MW": grid_h,
        "Curtailment_MW": curt_h,
        "BESS_SOC_MWh": soc_h,
        "H2_kg": h2_h
    }).to_csv(buf, index=False)
    
    st.download_button(
        t["dl_hourly"],
        buf.getvalue(),
        file_name="H2READY_profilo_orario.csv",
        mime="text/csv"
    )

    st.markdown("---")
    
    # 3. Sezione Export al Database Centrale
    st.subheader(t["sec_export"])
    codice = st.text_input(t["input_istat"])
    
    if st.button(t["btn_export"]):
        if not codice:
            st.error(t["export_err"])
        else:
            # Conversione esplicita float/int per evitare crash di json.dumps con tipi numpy
            payload = {
                "ID_ISTAT": str(codice),
                "T26_MODALITA": str(modalita),
                "T26_ZONA": str(zona),
                "T26_TARGET_H2_TON": float(round(target_kg / 1000, 2)) if usa_domanda else "N/A",
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
                "T26_PAYBACK_ANNI": float(round(R["payback"], 1)) if float(R["payback"]) < 99 else "N/A",
                "T26_CO2_EVITATA_TON_ANNO": float(round(R["co2"], 0)),
            }
            
            # Aggiunta dati superfici
            if usa_superfici:
                payload.update({
                    "T26B_SUP_TERRA_HA": float(round(terra_ha, 2)),
                    "T26B_SUP_TETTI_M2": float(round(tetti_m2, 0)),
                    "T26B_SUP_CAPANNONI_M2": float(round(cap_m2, 0)),
                })
            else:
                req = core.superfici_richieste(R["mw"], P)
                payload.update({
                    "T26B_SUP_TERRA_HA": float(round(req["ha_terra"], 2)),
                    "T26B_SUP_TETTI_M2": float(round(req["m2_tetti"], 0)),
                    "T26B_SUP_CAPANNONI_M2": float(round(req["m2_capannoni"], 0)),
                })
                
            if modalita == "copertura":
                payload["T26_COPERTURA_PERC"] = float(round(R["prod_h2"] / target_kg * 100, 1)) if target_kg > 0 else 0.0

            # Invio HTTP con gestione automatica degli header JSON
            try:
                headers = {"Content-Type": "application/json"}
                resp = requests.post(
                    WEBHOOK_URL, 
                    data=json.dumps(payload), 
                    headers=headers, 
                    timeout=20
                )
                
                if resp.status_code in [200, 201]:
                    st.success(t["export_ok"])
                    st.balloons()
                else:
                    st.error(t["export_http"].format(c=resp.status_code))
            except Exception as e:
                st.error(t["export_conn"].format(e=e))               
              "BESS_SOC_MWh": soc_h, "H2_kg": h2_h}).to_csv(buf, index=False)
    st.download_button(t["dl_hourly"], buf.getvalue(),
                       file_name="H2READY_profilo_orario.csv", mime="text/csv")

    st.markdown("---")
    st.subheader(t["sec_export"])
    codice = st.text_input(t["input_istat"])
    if st.button(t["btn_export"]):
        if not codice:
            st.error(t["export_err"])
        else:
            payload = {
                "ID_ISTAT": codice,
                "T26_MODALITA": modalita,
                "T26_ZONA": zona,
                "T26_TARGET_H2_TON": round(target_kg / 1000, 2) if usa_domanda else "N/A",
                "T26_PV_TERRA_MW": round(R["mw"]["terra"], 2),
                "T26_PV_TETTI_MW": round(R["mw"]["tetti"], 2),
                "T26_PV_CAPANNONI_MW": round(R["mw"]["capannoni"], 2),
                "T26_EOLICO_MW": round(R["mw"]["eolico"], 2),
                "T26_TAGLIA_FER_INSTALLATA_MW": round(taglia_fer, 2),
                "T26_TAGLIA_ELETTROLIZZATORE_MW": round(R["ely_mw"], 2),
                "T26_CAPACITA_BESS_MWH": round(R["batt_mwh"], 2),
                "T26_PRODUZIONE_H2_TON_ANNO": round(R["prod_h2"] / 1000, 2),
                "T26_QUOTA_RFNBO_PERC": round(R["quota_rfnbo"], 1),
                "T26_CURTAILMENT_PERC": round(R["perc_curt"], 1),
                "T26_CAPEX_CONNESSIONI_EURO": round(R["c_conn"], 0),
                "T26_CAPEX_TOTALE_MLN": round(R["capex_tot"] / 1e6, 2),
                "T26_LCOH_EURO_KG": round(R["lcoh"], 2),
                "T26_PAYBACK_ANNI": round(R["payback"], 1) if R["payback"] < 99 else "N/A",
                "T26_CO2_EVITATA_TON_ANNO": round(R["co2"], 0),
            }
            if usa_superfici:
                payload.update({
                    "T26B_SUP_TERRA_HA": round(terra_ha, 2),
                    "T26B_SUP_TETTI_M2": round(tetti_m2, 0),
                    "T26B_SUP_CAPANNONI_M2": round(cap_m2, 0),
                })
            else:
                req = core.superfici_richieste(R["mw"], P)
                payload.update({
                    "T26B_SUP_TERRA_HA": round(req["ha_terra"], 2),
                    "T26B_SUP_TETTI_M2": round(req["m2_tetti"], 0),
                    "T26B_SUP_CAPANNONI_M2": round(req["m2_capannoni"], 0),
                })
            if modalita == "copertura":
                payload["T26_COPERTURA_PERC"] = round(R["prod_h2"] / target_kg * 100, 1) if target_kg > 0 else 0

            try:
                resp = requests.post(WEBHOOK_URL, data=json.dumps(payload), timeout=20)
                if resp.status_code == 200:
                    st.success(t["export_ok"])
                    st.balloons()
                else:
                    st.error(t["export_http"].format(c=resp.status_code))
            except Exception as e:
                st.error(t["export_conn"].format(e=e))
