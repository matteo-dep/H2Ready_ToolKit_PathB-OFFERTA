"""
H2READY TOOLKIT - Tool 2.6 unificato
core.py - Motore tecnico ed economico condiviso dalle tre modalita' di analisi.

Progetto Interreg Italia-Slovenia H2READY - APE FVG
Autore: Matteo De Piccoli

Principio architetturale
------------------------
La simulazione oraria e' SEMPRE eseguita su un profilo normalizzato a 1 MW di
potenza FER installata. Tutti gli aggregati energetici che ne derivano sono
quindi "per MW" e scalano linearmente. Questo permette:

  * modalita' SUPERFICI  -> scala = MW ricavati dalle superfici disponibili
  * modalita' DOMANDA    -> scala = MW necessari a coprire il target di H2
  * modalita' COPERTURA  -> entrambe, confrontate fra loro

con UNA sola scansione tecnica, riutilizzata da tutte e tre. L'economia e'
aritmetica pura sugli aggregati: muovere un prezzo non ricalcola le 8760 ore.

Impianto esistente (categoria "esterno")
----------------------------------------
Un impianto gia' in esercizio - idroelettrico, biomasse, cogenerazione - non
scala con le altre categorie: la sua potenza e' fissa. Viene trattato come una
quinta categoria la cui quota si ricalcola in modo che quota_esterno * taglia
resti pari alla potenza nominale dichiarata. Non ha CAPEX (e' gia' costruito)
ne' costo di connessione (e' gia' connesso); ha un costo dell'energia proprio.

Sul piano normativo l'impianto esistente NON e' addizionale ai sensi dell'Atto
Delegato (UE) 2023/1184 salvo dichiarazione esplicita: la quota di energia che
ne proviene viene scorporata dall'idrogeno certificabile, con lo stesso
criterio gia' usato per l'accumulo non conforme.
"""

import os
import numpy as np
import pandas as pd
import streamlit as st

# ------------------------------------------------------------------
# NUMBA OPZIONALE (fallback puro Python)
# ------------------------------------------------------------------
try:
    from numba import njit
    NUMBA_OK = True
except Exception:
    NUMBA_OK = False

    def njit(*args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            return args[0]

        def _deco(f):
            return f
        return _deco


# ==================================================================
# DATASET DI PRODUZIONE
# ==================================================================
PV_WEIGHTS_NORD = {
    'Lombardia orientale, area Brescia_NORD': 0.2956,
    'Veneto centrale, area Padova_NORD': 0.2313,
    'Emilia-Romagna orientale, area Ferrara,pianura_NORD': 0.2213,
    'Piemonte meridionale, area Cuneo_NORD': 0.1874,
    'Friuli-Venezia Giulia, area Udine_NORD': 0.0644,
}
PV_WEIGHTS_SUD = {
    'Puglia, area Lecce_SUD': 0.3241,
    'Sicilia interna, area Caltanissetta,Enna_SUD': 0.2117,
    'Lazio meridionale, area Latina_SUD': 0.1982,
    'Sardegna, area Oristano,Campidano_SUD': 0.1330,
    'Campania interna, area Benevento_SUD': 0.1330,
}
WIND_WEIGHTS_NORD = {
    'Crinale savonese entroterra ligure_NORD': 0.6020,
    'Appennino emiliano, area Monte Cimone_NORD': 0.2239,
    'Piemonte sud-occidentale , Cuneese_NORD': 0.0945,
    'Veneto orientale , Delta del Po_NORD': 0.0647,
    'Valle d’Aosta , area alpina_NORD': 0.0149,
}
WIND_WEIGHTS_SUD = {
    'Puglia, area Foggia,Daunia_SUD': 0.3093,
    'Sicilia occidentale, area Trapani_SUD': 0.2267,
    'Campania, area Benevento,Avellino_SUD': 0.1950,
    'Basilicata, area Melfi,Potenza_SUD': 0.1489,
    'Calabria, area Crotone,Catanzaro_SUD': 0.1201,
}

PV_FILES = ["dataset_fotovoltaico_produzione.csv", "dataset_fotovoltaico.csv"]
WIND_FILES = ["dataset_eolico_produzione.csv", "dataset_eolico.csv"]
SUBDIRS = ["", "data", "dataset", "datasets", "db"]

ORE = 8760
MESI = pd.date_range("2023-01-01", periods=ORE, freq="h").month.values

# Parametri finanziari di base
WACC, VITA = 0.05, 20
CRF = (WACC * (1 + WACC) ** VITA) / ((1 + WACC) ** VITA - 1)

# Consumo specifico elettrolisi (kWh/kg), al netto della compressione
KWH_KG_ELY = 55.0
# Fattore di emissione evitato rispetto a idrogeno da SMR (kg CO2 / kg H2)
CO2_PER_KG_H2 = 9.3

# Categorie di generazione. "esterno" e' l'impianto gia' in esercizio.
CATEGORIE = ("terra", "tetti", "capannoni", "eolico", "esterno")

# Ore equivalenti tipiche per fonte: servono ai controlli di plausibilita'
# sui profili caricati dall'utente. Fonte: pratica progettuale corrente.
ORE_EQ_TIPICHE = {
    "idro_fluente": (3000, 4500),
    "idro_bacino": (2000, 3500),
    "biomasse": (6000, 8000),
    "cogenerazione": (5000, 8000),
    "eolico": (1800, 2500),
    "fotovoltaico": (1000, 1300),
    "altro": (0, 8760),
}


def trova_file(nomi):
    """Cerca un dataset nella repository: cartella dello script, sottocartelle note, cwd."""
    basi = []
    try:
        basi.append(os.path.dirname(os.path.abspath(__file__)))
    except NameError:
        pass
    basi.append(os.getcwd())
    for base in basi:
        for sub in SUBDIRS:
            for nome in nomi:
                p = os.path.join(base, sub, nome)
                if os.path.isfile(p):
                    return p
    return None


def _serie_pesata(df, pesi, scala=1.0, clip_upper=1.0):
    serie = sum(pd.to_numeric(df[c], errors='coerce').fillna(0.0) * w for c, w in pesi.items())
    return (serie / scala).clip(lower=0.0, upper=clip_upper).astype(float)


def _adatta_8760(arr):
    arr = np.asarray(arr, dtype=float)
    if arr.size >= ORE:
        return arr[:ORE]
    coda = arr[-24:] if arr.size >= 24 else arr
    return np.concatenate([arr, np.tile(coda, ORE)])[:ORE]


def diagnostica_colonne(df, pesi):
    """Colonne attese ma assenti nel dataset: serve al pannello di diagnostica."""
    return [c for c in pesi if c not in df.columns]


@st.cache_data(show_spinner=False)
def carica_profili():
    """Carica i profili orari dalla repository. Restituisce un dizionario di stato."""
    path_pv, path_wind = trova_file(PV_FILES), trova_file(WIND_FILES)
    esito = {"ok": False, "file_pv": "-", "file_wind": "-", "mancanti": [], "errore": None}
    try:
        df_pv = pd.read_csv(path_pv)
        df_wind = pd.read_csv(path_wind)
        mancanti = []
        for nome, pesi, df in [("PV Nord", PV_WEIGHTS_NORD, df_pv), ("PV Sud", PV_WEIGHTS_SUD, df_pv),
                               ("Wind Nord", WIND_WEIGHTS_NORD, df_wind), ("Wind Sud", WIND_WEIGHTS_SUD, df_wind)]:
            for c in diagnostica_colonne(df, pesi):
                mancanti.append(f"{nome}: {c}")
        if mancanti:
            raise KeyError("colonne mancanti")
        esito.update(ok=True, file_pv=os.path.basename(path_pv), file_wind=os.path.basename(path_wind))
        profili = {
            "pv_nord": _adatta_8760(_serie_pesata(df_pv, PV_WEIGHTS_NORD, 1000.0).values),
            "pv_sud": _adatta_8760(_serie_pesata(df_pv, PV_WEIGHTS_SUD, 1000.0).values),
            "wind_nord": _adatta_8760(_serie_pesata(df_wind, WIND_WEIGHTS_NORD).values),
            "wind_sud": _adatta_8760(_serie_pesata(df_wind, WIND_WEIGHTS_SUD).values),
        }
        return profili, esito
    except Exception as e:
        esito["errore"] = str(e)
        if isinstance(e, KeyError):
            esito["mancanti"] = mancanti
        t = np.arange(ORE)
        rng = np.random.default_rng(42)
        profili = {
            "pv_nord": np.clip(np.sin(t * np.pi / 12), 0, 1) * 0.8,
            "pv_sud": np.clip(np.sin(t * np.pi / 12), 0, 1) * 0.9,
            "wind_nord": rng.random(ORE) * 0.5,
            "wind_sud": rng.random(ORE) * 0.7,
        }
        return profili, esito


# ==================================================================
# PROFILO ESTERNO (impianto gia' in esercizio)
# ==================================================================
def leggi_profilo_esterno(file_o_path, potenza_mw=None):
    """Legge un profilo orario da xlsx o csv e lo normalizza per MW installato.

    Accetta il template H2READY (schede PROFILO/ANAGRAFICA) e qualunque file a
    due colonne dove l'ultima contenga la potenza oraria in kW.

    Ritorna (profilo_per_mw, potenza_mw, diagnostica).
    """
    diag = {"ok": False, "messaggi": [], "avvisi": []}

    try:
        nome = getattr(file_o_path, "name", str(file_o_path)).lower()
        if nome.endswith(".csv"):
            df = pd.read_csv(file_o_path)
        else:
            xl = pd.ExcelFile(file_o_path)
            foglio = "PROFILO" if "PROFILO" in xl.sheet_names else xl.sheet_names[0]
            df = pd.read_excel(xl, foglio)
            # Potenza nominale dall'anagrafica, se il template la contiene
            if potenza_mw is None and "ANAGRAFICA" in xl.sheet_names:
                ana = pd.read_excel(xl, "ANAGRAFICA")
                riga = ana[ana.iloc[:, 0].astype(str).str.contains("Potenza nominale", na=False)]
                if not riga.empty:
                    potenza_mw = float(riga.iloc[0, 1])
    except Exception as e:
        diag["messaggi"].append(f"File illeggibile: {e}")
        return None, None, diag

    col = "potenza_kW" if "potenza_kW" in df.columns else df.columns[-1]
    serie = pd.to_numeric(df[col], errors="coerce")

    if serie.isna().any():
        diag["messaggi"].append(f"{int(serie.isna().sum())} celle non numeriche o vuote.")
        return None, None, diag
    if (serie < 0).any():
        diag["messaggi"].append("Sono presenti valori negativi.")
        return None, None, diag
    if len(serie) != ORE:
        diag["messaggi"].append(f"Il file contiene {len(serie)} righe invece di {ORE}.")
        return None, None, diag

    kw = serie.values.astype(float)
    if not potenza_mw or potenza_mw <= 0:
        potenza_mw = float(kw.max()) / 1000.0
        diag["avvisi"].append("Potenza nominale non dichiarata: assunta pari al massimo del profilo.")
    if kw.max() > potenza_mw * 1000.0 * 1.001:
        diag["messaggi"].append(
            f"Il profilo supera la potenza nominale dichiarata ({kw.max()/1000:.2f} > {potenza_mw:.2f} MW).")
        return None, None, diag

    energia_mwh = kw.sum() / 1000.0
    ore_eq = energia_mwh / potenza_mw if potenza_mw > 0 else 0.0
    zeri = int((kw == 0).sum())

    # Il piu' lungo tratto consecutivo a zero: distingue la stagionalita'
    # da un fermo impianto o da un buco nei dati.
    massimo, corrente = 0, 0
    for v in kw:
        corrente = corrente + 1 if v == 0 else 0
        massimo = max(massimo, corrente)

    diag.update(ok=True, potenza_mw=potenza_mw, energia_mwh=energia_mwh,
                ore_eq=ore_eq, ore_zero=zeri, zero_consecutive=massimo,
                potenza_max_mw=kw.max() / 1000.0)
    if massimo >= 500:
        diag["avvisi"].append(
            f"{massimo} ore consecutive a zero ({massimo/24:.0f} giorni): "
            "probabile fermo impianto o dato mancante, non stagionalita'.")

    return np.ascontiguousarray(kw / 1000.0 / potenza_mw, dtype=float), potenza_mw, diag


def quote_con_esterno(quote_rel, potenza_esterno_mw, taglia_totale_mw):
    """Ripartisce la taglia totale fra le nuove categorie e l'impianto esistente.

    quote_rel: frazioni fra terra/tetti/capannoni/eolico, somma 1.
    Garantisce quota_esterno * taglia_totale = potenza_esterno_mw.
    """
    q = {c: 0.0 for c in CATEGORIE}
    if taglia_totale_mw <= 0:
        return q
    q_ext = min(max(potenza_esterno_mw / taglia_totale_mw, 0.0), 1.0)
    for c in ("terra", "tetti", "capannoni", "eolico"):
        q[c] = quote_rel.get(c, 0.0) * (1.0 - q_ext)
    q["esterno"] = q_ext
    return q


# ==================================================================
# DISPACCIAMENTO ORARIO
# ==================================================================
@njit(cache=True)
def _dispatch(gen, ely_mw, batt_mwh, grid_max_mw, eff_batt=0.90):
    """Ordine di merito: FER diretta -> batteria -> rete (se abilitata).
    Ritorna: energia FER all'elettrolizzatore, energia da rete, SOC, curtailment,
    energia scaricata dalla batteria (serve alla verifica RED III sull'accumulo)."""
    n = gen.shape[0]
    e_fer = np.zeros(n)
    e_grid = np.zeros(n)
    soc_out = np.zeros(n)
    curt = np.zeros(n)
    disc = np.zeros(n)
    soc = batt_mwh * 0.2
    se = np.sqrt(eff_batt)
    for t in range(n):
        avail = gen[t]
        if avail >= ely_mw:
            charge = min(avail - ely_mw, (batt_mwh - soc) / se)
            soc += charge * se
            curt[t] = avail - ely_mw - charge
            e_fer[t] = ely_mw
        else:
            discharge = min(ely_mw - avail, soc * se)
            soc -= discharge / se
            disc[t] = discharge
            e_fer[t] = avail + discharge
        deficit = ely_mw - e_fer[t]
        if deficit > 0.0 and grid_max_mw > 0.0:
            e_grid[t] = min(deficit, grid_max_mw)
        soc_out[t] = soc
    return e_fer, e_grid, soc_out, curt, disc


def _match_mensile(e_grid_h, curt_h):
    """Energia da rete compensabile con il surplus FER dello stesso mese (RED III, scenario mensile)."""
    tot = 0.0
    for m in range(1, 13):
        msk = MESI == m
        tot += min(float(e_grid_h[msk].sum()), float(curt_h[msk].sum()))
    return tot


@st.cache_data(show_spinner=False)
def scan_tecnico(gen_norm, batt_per_mw, grid_max_pct, ratios):
    """Scansione tecnica su profilo normalizzato a 1 MW di FER installata.
    Tutti i risultati sono per MW e scalano linearmente. Cache: dipende solo
    dalla forma del profilo, dal BESS e dalla rete - non dai prezzi."""
    righe = []
    for r in ratios:
        gmax = r * grid_max_pct / 100.0
        e_fer_h, e_grid_h, _, curt_h, disc_h = _dispatch(gen_norm, float(r), float(batt_per_mw), float(gmax))
        e_grid = float(e_grid_h.sum())
        righe.append({
            "ratio": float(r),
            "e_fer": float(e_fer_h.sum()),
            "e_grid": e_grid,
            "e_curt": float(curt_h.sum()),
            "e_disc": float(disc_h.sum()),
            "e_grid_ok": _match_mensile(e_grid_h, curt_h) if e_grid > 0 else 0.0,
        })
    return pd.DataFrame(righe)


@st.cache_data(show_spinner=False)
def aggregati_e_dettaglio(gen_norm, ratio, batt_per_mw, grid_max_pct):
    """Simulazione singola sulla taglia scelta, sempre normalizzata a 1 MW di FER.
    Restituisce gli aggregati (per MW) e le serie orarie (per MW): moltiplicando
    queste ultime per i MW installati si ottengono i profili in scala reale."""
    gmax = ratio * grid_max_pct / 100.0
    e_fer_h, e_grid_h, soc_h, curt_h, disc_h = _dispatch(gen_norm, float(ratio), float(batt_per_mw), float(gmax))
    e_grid = float(e_grid_h.sum())
    riga = {
        "ratio": float(ratio),
        "e_fer": float(e_fer_h.sum()),
        "e_grid": e_grid,
        "e_curt": float(curt_h.sum()),
        "e_disc": float(disc_h.sum()),
        "e_grid_ok": _match_mensile(e_grid_h, curt_h) if e_grid > 0 else 0.0,
    }
    return riga, e_fer_h, e_grid_h, soc_h, curt_h


# ==================================================================
# PROFILO NORMALIZZATO E POTENZE
# ==================================================================
def profilo_normalizzato(profili, zona, quote, resa_tetti, resa_cap, ext_norm=None):
    """Profilo di generazione per 1 MW di FER installata.
    quote: dizionario di frazioni (terra, tetti, capannoni, eolico, esterno) con somma 1.
    ext_norm: profilo dell'impianto esistente normalizzato per il SUO MW."""
    pv = profili["pv_nord"] if zona == "nord" else profili["pv_sud"]
    wind = profili["wind_nord"] if zona == "nord" else profili["wind_sud"]
    gen = (pv * quote["terra"]
           + pv * quote["tetti"] * resa_tetti
           + pv * quote["capannoni"] * resa_cap
           + wind * quote["eolico"])
    if ext_norm is not None and quote.get("esterno", 0.0) > 0:
        gen = gen + ext_norm * quote["esterno"]
    return np.ascontiguousarray(gen, dtype=float), pv, wind


def energie_per_categoria(mw, resa_tetti, resa_cap, somma_pv, somma_wind, somma_ext=0.0):
    """Energia annua prodotta da ciascuna categoria (MWh), in forma chiusa."""
    return {
        "terra": mw["terra"] * somma_pv,
        "tetti": mw["tetti"] * resa_tetti * somma_pv,
        "capannoni": mw["capannoni"] * resa_cap * somma_pv,
        "eolico": mw["eolico"] * somma_wind,
        "esterno": mw.get("esterno", 0.0) * somma_ext,
    }


# ==================================================================
# CONNESSIONI ELETTRICHE
# ==================================================================
def connessione_utility(mw, km, diretta):
    """Utility scale a terra / eolico: AT sopra 6 MW, MT sotto."""
    if mw <= 0:
        return 0.0, "-"
    liv = "AT" if mw > 6 else "MT"
    if diretta:
        c = (730000 + 300000 * km) if mw > 6 else (8000 + 155000 * km)
    else:
        c = 730000.0 if mw > 6 else 8000.0
    return c, liv


def connessione_punti(mw, n, km, diretta, c_punto, c_km):
    """Tetti e capannoni: costo per punto di connessione + cavidotto se linea diretta."""
    if mw <= 0 or n <= 0:
        return 0.0, "-"
    liv = "MT" if (mw / n) > 0.2 else "BT"
    c = n * c_punto
    if diretta:
        c += n * km * c_km
    return c, liv


def n_punti(mw, n_dichiarato, taglia_media_kwp):
    """Numero di punti: dichiarato (modalita' superfici) o derivato dalla taglia media."""
    if n_dichiarato is not None:
        return int(n_dichiarato)
    if taglia_media_kwp and taglia_media_kwp > 0:
        return max(1, int(round(mw * 1000.0 / taglia_media_kwp)))
    return 0


def calcola_connessioni(mw, S):
    """Restituisce CAPEX totale connessioni e dettaglio per riga.

    L'impianto esistente e' gia' connesso: se lo si collega all'elettrolizzatore
    con linea diretta si paga il solo cavidotto, altrimenti nulla."""
    n_tetti = n_punti(mw["tetti"], S["tetti"]["n"], S["tetti"]["taglia_media"])
    n_cap = n_punti(mw["capannoni"], S["capannoni"]["n"], S["capannoni"]["taglia_media"])

    c_terra, liv_terra = connessione_utility(mw["terra"], S["terra"]["km"], S["terra"]["diretta"])
    c_tetti, liv_tetti = connessione_punti(mw["tetti"], n_tetti, S["tetti"]["km"], S["tetti"]["diretta"],
                                           S["tetti"]["c_punto"], S["tetti"]["c_km"])
    c_cap, liv_cap = connessione_punti(mw["capannoni"], n_cap, S["capannoni"]["km"], S["capannoni"]["diretta"],
                                       S["capannoni"]["c_punto"], S["capannoni"]["c_km"])
    c_wind, liv_wind = connessione_utility(mw["eolico"], S["eolico"]["km"], True)

    mw_ext = mw.get("esterno", 0.0)
    s_ext = S.get("esterno", {"km": 0.0, "diretta": False, "c_km": 155000})
    if mw_ext > 0 and s_ext.get("diretta"):
        c_ext = s_ext.get("km", 0.0) * s_ext.get("c_km", 155000)
        liv_ext = "AT" if mw_ext > 6 else "MT"
    else:
        c_ext, liv_ext = 0.0, ("rete" if mw_ext > 0 else "-")

    dettaglio = [
        {"cat": "terra", "mw": mw["terra"], "n": 1 if mw["terra"] > 0 else 0, "km": S["terra"]["km"],
         "diretta": S["terra"]["diretta"], "liv": liv_terra, "capex": c_terra},
        {"cat": "tetti", "mw": mw["tetti"], "n": n_tetti, "km": S["tetti"]["km"],
         "diretta": S["tetti"]["diretta"], "liv": liv_tetti, "capex": c_tetti},
        {"cat": "capannoni", "mw": mw["capannoni"], "n": n_cap, "km": S["capannoni"]["km"],
         "diretta": S["capannoni"]["diretta"], "liv": liv_cap, "capex": c_cap},
        {"cat": "eolico", "mw": mw["eolico"], "n": 1 if mw["eolico"] > 0 else 0, "km": S["eolico"]["km"],
         "diretta": True, "liv": liv_wind, "capex": c_wind},
        {"cat": "esterno", "mw": mw_ext, "n": 1 if mw_ext > 0 else 0, "km": s_ext.get("km", 0.0),
         "diretta": bool(s_ext.get("diretta")), "liv": liv_ext, "capex": c_ext},
    ]
    return c_terra + c_tetti + c_cap + c_wind + c_ext, dettaglio


def bess_conforme(mw, S, batt_mwh):
    """RED III: l'accumulo e' ammesso se dietro lo stesso punto di connessione della generazione."""
    if batt_mwh <= 0:
        return True
    for cat in ("terra", "tetti", "capannoni"):
        if mw[cat] > 0 and not S[cat]["diretta"]:
            return False
    return True


# ==================================================================
# ECONOMIA E CONFORMITA' RED III
# ==================================================================
def valuta(riga_tec, taglia_fer, quote, P, S):
    """Aritmetica pura sugli aggregati tecnici: nessuna simulazione oraria.

    riga_tec   : dict/Series con e_fer, e_grid, e_curt, e_grid_ok (per MW di FER)
    taglia_fer : MW complessivi di FER installata, impianto esistente incluso
    quote      : frazioni per categoria (somma 1)
    P          : parametri economici e normativi
    S          : parametri di sito e connessione
    """
    eff = P["eff_sistema"]

    mw = {c: quote.get(c, 0.0) * taglia_fer for c in CATEGORIE}
    mw_pv = mw["terra"] + mw["tetti"] + mw["capannoni"]
    ely_mw = riga_tec["ratio"] * taglia_fer
    batt_mwh = P["bess_ratio"] * mw_pv if P["bess_on"] else 0.0

    e_fer = riga_tec["e_fer"] * taglia_fer
    e_grid = riga_tec["e_grid"] * taglia_fer
    e_curt = riga_tec["e_curt"] * taglia_fer
    e_grid_ok_mese = riga_tec["e_grid_ok"] * taglia_fer
    e_disc = riga_tec["e_disc"] * taglia_fer
    e_tot = e_fer + e_grid
    prod_h2 = e_tot * 1000.0 / eff
    if prod_h2 <= 0:
        return None

    e_cat = energie_per_categoria(mw, P["resa_tetti"], P["resa_cap"],
                                  P["somma_pv"], P["somma_wind"], P.get("somma_ext", 0.0))
    e_prodotta = sum(e_cat.values())

    # --- RED III ---
    if e_grid <= 0:
        e_grid_ok = 0.0
    elif P["grid_cert"]:
        e_grid_ok = e_grid
    elif P["scenario_mensile"]:
        e_grid_ok = e_grid_ok_mese
    else:
        e_grid_ok = 0.0

    ok_bess = bess_conforme(mw, S, batt_mwh)
    prereq = P["red_add"] and P["red_noaid"] and P["red_zone"]
    # Se l'accumulo non e' dietro lo stesso punto di connessione della generazione,
    # non decade l'intera produzione: e' l'energia transitata in batteria a non
    # soddisfare la correlazione temporale, quindi viene scorporata.
    e_disc_ko = 0.0 if ok_bess else e_disc

    # Un impianto gia' in esercizio non e' addizionale ai sensi dell'Atto Delegato
    # 2023/1184 (entrata in esercizio entro 36 mesi, assenza di sostegno pubblico)
    # salvo dichiarazione esplicita. Si scorpora la quota di energia che ne proviene,
    # con lo stesso criterio applicato all'accumulo non conforme.
    ok_esterno = P.get("esterno_addizionale", True) or e_cat["esterno"] <= 0
    if ok_esterno:
        e_esterno_ko = 0.0
    else:
        q_ext = e_cat["esterno"] / e_prodotta if e_prodotta > 0 else 0.0
        e_esterno_ko = e_fer * q_ext

    e_rfnbo = max(e_fer - e_disc_ko - e_esterno_ko + e_grid_ok, 0.0) if prereq else 0.0
    h2_rfnbo = e_rfnbo * 1000.0 / eff
    h2_nc = prod_h2 - h2_rfnbo

    # --- CAPEX ---
    c_ely = ely_mw * 1000 * P["capex_ely"]
    c_batt = batt_mwh * 1000 * P["capex_batt"]
    c_stocc = (prod_h2 * P["perc_stoccaggio"] / 100.0) * P["capex_stocc"]
    c_comp = (P["inc_comp"] * prod_h2) / CRF
    c_conn, dettaglio_conn = calcola_connessioni(mw, S)
    c_fer = 0.0
    if P["autoproduzione"]:
        # L'impianto esistente non entra nel CAPEX: e' gia' costruito e pagato.
        c_fer = (mw["terra"] * 1000 * P["capex_pv_terra"]
                 + mw["tetti"] * 1000 * P["capex_pv_tetti"]
                 + mw["capannoni"] * 1000 * P["capex_pv_cap"]
                 + mw["eolico"] * 1000 * P["capex_wind"])
    capex_tot = c_ely + c_batt + c_stocc + c_comp + c_conn + c_fer

    # --- OPEX ---
    # L'energia dell'impianto esistente si paga sempre: anche in autoproduzione
    # e' un impianto di terzi o gia' ammortizzato, con un proprio prezzo di cessione.
    if P["paga_solo_assorbita"]:
        q_use = (e_fer / e_prodotta) if e_prodotta > 0 else 0.0
        opex_ext = e_cat["esterno"] * q_use * P.get("cfd_esterno", 90.0)
    else:
        opex_ext = e_cat["esterno"] * P.get("cfd_esterno", 90.0)

    if P["autoproduzione"]:
        opex_fer = opex_ext
    else:
        e_pv = e_cat["terra"] + e_cat["tetti"] + e_cat["capannoni"]
        if P["paga_solo_assorbita"]:
            e_nuovi = e_pv + e_cat["eolico"]
            q_pv = e_pv / e_nuovi if e_nuovi > 0 else 0.0
            e_fer_nuovi = e_fer * (e_nuovi / e_prodotta if e_prodotta > 0 else 0.0)
            opex_fer = e_fer_nuovi * (q_pv * P["cfd_pv"] + (1 - q_pv) * P["cfd_wind"]) + opex_ext
        else:
            opex_fer = e_pv * P["cfd_pv"] + e_cat["eolico"] * P["cfd_wind"] + opex_ext

    quota_uso = (e_fer / e_prodotta) if e_prodotta > 0 else 0.0
    e_wheel = sum(e_cat[c] for c in ("terra", "tetti", "capannoni") if not S[c]["diretta"])
    if mw["esterno"] > 0 and not S.get("esterno", {}).get("diretta", False):
        e_wheel += e_cat["esterno"]
    opex_wheel = e_wheel * quota_uso * P["oneri_rete"]
    opex_grid = e_grid * P["grid_price"]
    opex_maint = capex_tot * 0.03
    opex_tot = opex_fer + opex_wheel + opex_grid + opex_maint

    lcoh = (opex_tot + capex_tot * CRF) / prod_h2
    ricavi = h2_rfnbo * P["prezzo_h2"] + h2_nc * P["prezzo_h2_nc"]
    margine = ricavi - opex_tot
    payback = capex_tot / margine if margine > 0 else 99.0

    return {
        "taglia_fer": taglia_fer, "mw": mw, "mw_pv": mw_pv, "ely_mw": ely_mw, "batt_mwh": batt_mwh,
        "ratio": riga_tec["ratio"], "e_fer": e_fer, "e_grid": e_grid, "e_curt": e_curt, "e_tot": e_tot,
        "e_prodotta": e_prodotta, "e_cat": e_cat, "e_grid_ok": e_grid_ok,
        "prod_h2": prod_h2, "h2_rfnbo": h2_rfnbo, "h2_nc": h2_nc,
        "quota_rfnbo": (h2_rfnbo / prod_h2 * 100) if prod_h2 > 0 else 0.0,
        "prereq": prereq, "ok_bess": ok_bess, "e_disc": e_disc, "e_disc_ko": e_disc_ko,
        "ok_esterno": ok_esterno, "e_esterno_ko": e_esterno_ko,
        "c_ely": c_ely, "c_batt": c_batt, "c_stocc": c_stocc, "c_comp": c_comp,
        "c_conn": c_conn, "c_fer": c_fer, "capex_tot": capex_tot, "dettaglio_conn": dettaglio_conn,
        "opex_fer": opex_fer, "opex_wheel": opex_wheel, "opex_grid": opex_grid,
        "opex_maint": opex_maint, "opex_tot": opex_tot,
        "lcoh": lcoh, "ricavi": ricavi, "payback": payback,
        "ore_eq": e_tot / ely_mw if ely_mw > 0 else 0.0,
        "perc_curt": (e_curt / e_prodotta * 100) if e_prodotta > 0 else 0.0,
        "co2": h2_rfnbo * CO2_PER_KG_H2 / 1000.0,
    }


def scala_per_domanda(riga_tec, target_kg, eff):
    """MW di FER necessari a produrre il target di idrogeno, per una data taglia relativa di elettrolizzatore."""
    h2_per_mw = (riga_tec["e_fer"] + riga_tec["e_grid"]) * 1000.0 / eff
    if h2_per_mw <= 0:
        return 0.0
    return target_kg / h2_per_mw


def superfici_richieste(mw, P):
    """Modalita' domanda: superfici necessarie per ospitare le potenze calcolate."""
    ha = mw["terra"] / P["dens_terra"] / (P["use_terra"] / 100.0) if P["dens_terra"] > 0 else 0.0
    m2_tetti = mw["tetti"] * 1000.0 / P["dens_tetti"] / (P["use_tetti"] / 100.0) if P["dens_tetti"] > 0 else 0.0
    m2_cap = mw["capannoni"] * 1000.0 / P["dens_cap"] / (P["use_cap"] / 100.0) if P["dens_cap"] > 0 else 0.0
    return {"ha_terra": ha, "m2_tetti": m2_tetti, "m2_capannoni": m2_cap}


def ottimizza(df_tec, taglia_fer_fn, quote, P, S):
    """Scansiona le taglie di elettrolizzatore e restituisce la lista di scenari valutati."""
    esiti = []
    for _, riga in df_tec.iterrows():
        taglia_fer = taglia_fer_fn(riga)
        if taglia_fer <= 0:
            continue
        v = valuta(riga, taglia_fer, quote, P, S)
        if v:
            esiti.append(v)
    return esiti


def risolvi_domanda(profili, zona, quote_rel, resa_tetti, resa_cap, ext_norm,
                    potenza_esterno_mw, target_kg, batt_per_mw_fn, grid_max_pct,
                    ratios, P, S, iterazioni=12, tolleranza=0.001):
    """Modalita' domanda con impianto esistente: punto fisso sulla taglia totale.

    Senza impianto esistente il problema e' diretto: la taglia scala il profilo.
    Con un impianto di potenza fissa il profilo combinato dipende dalla taglia
    totale, che a sua volta dipende dal profilo. Si itera: converge in due o tre
    passaggi perche' la forma del profilo cambia poco fra un'iterazione e l'altra.

    Ritorna (esiti, quote, gen_norm, pv, wind, n_iterazioni).
    """
    taglia = max(potenza_esterno_mw * 2.0, 1.0)
    esiti, quote, gen_norm, pv, wind = [], {}, None, None, None

    for k in range(1, iterazioni + 1):
        quote = quote_con_esterno(quote_rel, potenza_esterno_mw, taglia)
        gen_norm, pv, wind = profilo_normalizzato(profili, zona, quote, resa_tetti, resa_cap, ext_norm)
        batt_per_mw = batt_per_mw_fn(quote)
        df_tec = scan_tecnico(gen_norm, batt_per_mw, grid_max_pct, ratios)
        # La taglia totale non puo' scendere sotto l'impianto gia' esistente:
        # se questo da solo supera il target, il dimensionamento si ferma li'
        # e la sovrapproduzione va mostrata, non nascosta rimpicciolendolo.
        def _taglia(r):
            return max(scala_per_domanda(r, target_kg, P["eff_sistema"]), potenza_esterno_mw)

        esiti = ottimizza(df_tec, _taglia, quote, P, S)
        if not esiti:
            return [], quote, gen_norm, pv, wind, k
        nuova = min(esiti, key=lambda v: v["lcoh"])["taglia_fer"]
        if abs(nuova - taglia) / max(taglia, 1e-6) < tolleranza:
            taglia = nuova
            break
        taglia = nuova

    return esiti, quote, gen_norm, pv, wind, k
