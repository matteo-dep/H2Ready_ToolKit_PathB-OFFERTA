"""
H2READY - modulo condiviso per il concatenamento dei tool.

Va copiato identico in tutti i repository (Tool 1.1, 1.2, 2.x, Action Plan).
Ogni tool lo usa per:
  - chiedere l'ID_ISTAT prima di qualunque calcolo (modalità "blindata")
  - recuperare la riga del Comune dal foglio master
  - precompilare gli slider con i dati già raccolti
  - costruire i link ai tool successivi, filtrati per livello e percorso

USO MINIMO in un tool 2.x:

    import streamlit as st
    import h2ready as H

    st.set_page_config(page_title="Tool 2.6", layout="wide")
    comune = H.blocco_accesso("Tool 2.6 - Produzione H2 verde", percorso="B")
    if comune is None:
        st.stop()          # l'utente non ha ancora inserito un ID valido

    # da qui in poi i dati ci sono: gli slider partono dai valori del Comune
    potenza = st.slider("Elettrolizzatore (MW)", 0.5, 50.0,
                        H.valore(comune, "T25_CAPACITA_RESIDUA_MW", 5.0))

SEGRETI: ogni repository ha bisogno della stessa sezione [connections.gsheets]
nei propri Secrets, perché ogni app Streamlit è isolata.
"""

import re
from urllib.parse import quote

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

# =============================================================================
# CONFIGURAZIONE
# =============================================================================

COL_ID = "ID_ISTAT"
COL_NOME = "NOME_COMUNE"
COL_MATURITA = "T11_LIVELLO_MATURITA"
COL_SCORE = {"A": "T12_SCORE_A", "B": "T12_SCORE_B", "C": "T12_SCORE_C"}

SOGLIE_MATURITA = [(5, 8, "L1"), (9, 14, "L2"), (15, 999, "L3")]

# Punteggio minimo per attivare ciascun percorso, dal questionario 1.2.
# Le soglie sono diverse perché le tre scale non sono omogenee: il valore
# assoluto di un punteggio C non è confrontabile con quello di un punteggio B.
SOGLIE_PERCORSO = {"A": 10.0, "B": 13.0, "C": 8.0}

# Quanti percorsi si aprono per livello, e con quale autonomia sugli strumenti.
# Gli strumenti sono di tre categorie:
#   base        questionari e tool di raccolta (2.1, 2.2, 2.3, 2.5, 2.7)
#   avanzato    dimensionamento tecnico-economico (2.6, 2.8)
#   fast        strumenti H2 FAST, di livello specialistico
# Per ciascuna categoria: "libero" | "richiesta" | "no".
REGOLE_LIVELLO = {
    "L0": {"max_percorsi": 0, "avanzati": "no", "fast": "no",
           "descrizione": "Assessment preliminare non completato: va compilato il "
                          "questionario 1.1."},
    "L1": {"max_percorsi": 1, "avanzati": "richiesta", "fast": "no",
           "descrizione": "Si sviluppa un solo percorso, quello con il punteggio più "
                          "alto. Gli strumenti di dimensionamento sono accessibili su "
                          "richiesta al gruppo di progetto."},
    "L2": {"max_percorsi": 2, "avanzati": "libero", "fast": "richiesta",
           "descrizione": "Si sviluppano fino a due percorsi, quelli con il punteggio "
                          "più alto. Gli strumenti di dimensionamento sono liberi, con "
                          "supporto disponibile; gli strumenti H2 FAST su richiesta."},
    "L3": {"max_percorsi": 3, "avanzati": "libero", "fast": "libero",
           "descrizione": "Si sviluppano tutti i percorsi che superano la soglia, con "
                          "piena autonomia su ogni strumento, H2 FAST compreso."},
}

# Contatto mostrato quando uno strumento è accessibile solo su richiesta.
CONTATTO_PROGETTO = "matteo.depiccoli@ape.fvg.it"

# Compatibilità: i nomi tradotti si ottengono con nome_percorso("A")
NOMI_PERCORSO = {"A": "Domanda e usi finali",
                 "B": "Offerta e produzione",
                 "C": "Transito e logistica"}

# Colonne che testimoniano il completamento di ciascun tool: se almeno una è
# valorizzata, il tool risulta compilato.
TESTIMONI = {
    "1.1": ["T11_LIVELLO_MATURITA"],
    "1.2": ["T12_SCORE_A", "T12_SCORE_B", "T12_SCORE_C"],
    "2.1": ["T21_FABBISOGNO_H2_TON_ANNO", "T21_N_AZIENDE_IDONEE"],
    "2.2": ["T22_FABBISOGNO_H2_TON_ANNO", "T22_N_VEICOLI_ANALIZZATI"],
    "2.3": ["T23_FLAG_RIFUGI", "T23_FLAG_MEZZI_CRITICI", "T23_FLAG_TRENI",
            "T23_FLAG_DEPURATORI", "T23_FLAG_COLD_STORAGE", "T23_FLAG_PORTI_AEROPORTI"],
    "2.4": ["T24_FABBISOGNO_TERMICO_KWH_ANNO"],
    "2.5": ["T25_AREE_IDONEE_MQ", "T25_FER_INSTALLATA_MW"],
    "2.6": ["T26_PRODUZIONE_H2_TON_ANNO", "T26_TAGLIA_ELETTROLIZZATORE_MW"],
    "2.7": ["T27_TGM_CAMION", "T27_SCORE_C1"],
    "2.8": ["T28_CAPACITA_KG_GIORNO", "T28_TAGLIA_HRS"],
}


# =============================================================================
# TESTI (it / en / sl)
# La lingua si imposta con imposta_lingua("sl") oppure passandola a
# blocco_accesso(..., lingua="sl"). Resta valida per tutta la sessione.
# =============================================================================

LINGUA_PREDEFINITA = "it"

TESTI = {
    "percorso_A": {"it": "Domanda e usi finali", "en": "Demand and end uses",
                   "sl": "Povpraševanje in končne rabe"},
    "percorso_B": {"it": "Offerta e produzione", "en": "Supply and production",
                   "sl": "Ponudba in proizvodnja"},
    "percorso_C": {"it": "Transito e logistica", "en": "Transit and logistics",
                   "sl": "Tranzit in logistika"},

    "liv_L0": {"it": "Assessment preliminare non completato: va compilato il questionario 1.1.",
               "en": "Preliminary assessment not completed: questionnaire 1.1 must be filled in.",
               "sl": "Predhodna ocena ni zaključena: izpolniti je treba vprašalnik 1.1."},
    "liv_L1": {"it": "Si sviluppa un solo percorso, quello con il punteggio più alto. Gli "
                     "strumenti di dimensionamento sono accessibili su richiesta al gruppo di progetto.",
               "en": "Only one pathway is developed, the one with the highest score. Sizing "
                     "tools are available on request to the project team.",
               "sl": "Razvije se le ena pot, tista z najvišjo oceno. Orodja za dimenzioniranje "
                     "so na voljo na zahtevo pri projektni skupini."},
    "liv_L2": {"it": "Si sviluppano fino a due percorsi, quelli con il punteggio più alto. Gli "
                     "strumenti di dimensionamento sono liberi, con supporto disponibile; gli "
                     "strumenti H2 FAST su richiesta.",
               "en": "Up to two pathways are developed, those with the highest scores. Sizing "
                     "tools are open, with support available; H2 FAST tools on request.",
               "sl": "Razvijeta se do dve poti, tisti z najvišjima ocenama. Orodja za "
                     "dimenzioniranje so prosto dostopna, s podporo; orodja H2 FAST na zahtevo."},
    "liv_L3": {"it": "Si sviluppano tutti i percorsi che superano la soglia, con piena "
                     "autonomia su ogni strumento, H2 FAST compreso.",
               "en": "All pathways above threshold are developed, with full autonomy on every "
                     "tool, including H2 FAST.",
               "sl": "Razvijejo se vse poti nad pragom, s polno samostojnostjo pri vseh "
                     "orodjih, vključno s H2 FAST."},

    "mot_soglia": {"it": "Punteggio {p}, soglia minima {s}.",
                   "en": "Score {p}, minimum threshold {s}.",
                   "sl": "Ocena {p}, najnižji prag {s}."},
    "mot_uno": {"it": "Il livello L1 consente di sviluppare un solo percorso, assegnato a "
                      "quello con il punteggio più alto.",
                "en": "Level L1 allows only one pathway, assigned to the highest score.",
                "sl": "Raven L1 dopušča le eno pot, dodeljeno najvišji oceni."},
    "mot_max": {"it": "Il livello {l} consente di sviluppare {n} percorsi, assegnati a quelli "
                      "con il punteggio più alto.",
                "en": "Level {l} allows {n} pathways, assigned to the highest scores.",
                "sl": "Raven {l} dopušča {n} poti, dodeljeni najvišjim ocenam."},
    "mot_no12": {"it": "Questionario 1.2 non compilato.",
                 "en": "Questionnaire 1.2 not completed.",
                 "sl": "Vprašalnik 1.2 ni izpolnjen."},

    "acc_intro": {"it": "Per procedere serve il **codice identificativo del Comune**, lo stesso "
                        "usato nei questionari 1.1 e 1.2. I parametri già raccolti verranno "
                        "caricati automaticamente negli strumenti di calcolo.",
                  "en": "To proceed you need the **municipality identification code**, the same "
                        "used in questionnaires 1.1 and 1.2. Data already collected will be "
                        "loaded automatically into the calculation tools.",
                  "sl": "Za nadaljevanje potrebujete **identifikacijsko kodo občine**, isto kot "
                        "v vprašalnikih 1.1 in 1.2. Že zbrani podatki bodo samodejno naloženi "
                        "v orodja za izračun."},
    "acc_codice": {"it": "Codice identificativo", "en": "Identification code",
                   "sl": "Identifikacijska koda"},
    "acc_apri": {"it": "Apri lo strumento", "en": "Open the tool", "sl": "Odpri orodje"},
    "acc_nontrovato": {"it": "Codice non trovato nel database. Verifica di aver completato il "
                             "questionario 1.1, oppure controlla il codice inserito.",
                       "en": "Code not found in the database. Check that questionnaire 1.1 has "
                             "been completed, or verify the code entered.",
                       "sl": "Kode ni v bazi. Preverite, ali je vprašalnik 1.1 izpolnjen, ali "
                             "preverite vneseno kodo."},
    "acc_l0": {"it": "Il Comune non ha ancora un livello di maturità assegnato: completa prima "
                     "il questionario 1.1.",
               "en": "The municipality has no maturity level yet: please complete questionnaire 1.1 first.",
               "sl": "Občina še nima dodeljene ravni zrelosti: najprej izpolnite vprašalnik 1.1."},
    "acc_percorso_ko": {"it": "Percorso {p} ({n}) non attivo per questo Comune. {m}",
                        "en": "Pathway {p} ({n}) is not active for this municipality. {m}",
                        "sl": "Pot {p} ({n}) za to občino ni aktivna. {m}"},
    "acc_errore_foglio": {"it": "Impossibile leggere il foglio dati.",
                          "en": "Unable to read the data sheet.",
                          "sl": "Podatkovnega lista ni mogoče prebrati."},
    "acc_cambia": {"it": "Cambia Comune", "en": "Change municipality", "sl": "Zamenjaj občino"},
    "acc_simulazione": {"it": "Modalità simulazione: i dati non verranno collegati ad alcun Comune.",
                        "en": "Simulation mode: data will not be linked to any municipality.",
                        "sl": "Način simulacije: podatki ne bodo povezani z nobeno občino."},
    "acc_senza_dati": {"it": "Procedi senza dati (solo simulazione)",
                       "en": "Proceed without data (simulation only)",
                       "sl": "Nadaljuj brez podatkov (samo simulacija)"},

    "str_no": {"it": "Strumento {e}: non disponibile al livello {l}.",
               "en": "{e} tool: not available at level {l}.",
               "sl": "Orodje {e}: ni na voljo na ravni {l}."},
    "str_avanzato": {"it": "di dimensionamento avanzato", "en": "advanced sizing",
                     "sl": "za napredno dimenzioniranje"},
    "str_fast": {"it": "H2 FAST", "en": "H2 FAST", "sl": "H2 FAST"},
    "str_supporto": {"it": "Strumento di dimensionamento: al livello L2 è disponibile il supporto "
                           "tecnico del gruppo di progetto ({c}). Puoi procedere in autonomia, ma "
                           "per usare i risultati in un atto formale conviene una verifica congiunta.",
                     "en": "Sizing tool: at level L2 technical support from the project team is "
                           "available ({c}). You may proceed on your own, but a joint review is "
                           "advisable before using the results in a formal document.",
                     "sl": "Orodje za dimenzioniranje: na ravni L2 je na voljo tehnična podpora "
                           "projektne skupine ({c}). Lahko nadaljujete samostojno, vendar je pred "
                           "uporabo rezultatov v uradnem dokumentu priporočljiv skupni pregled."},
    "sbl_richiesta": {"it": "Strumento {e}: al livello {l} l'accesso avviene su richiesta al gruppo "
                            "di progetto. Scrivi a **{c}** indicando il codice del Comune: riceverai "
                            "il codice di sblocco insieme alle indicazioni per interpretare i risultati.",
                      "en": "{e} tool: at level {l} access is granted on request to the project team. "
                            "Write to **{c}** quoting the municipality code: you will receive the "
                            "unlock code together with guidance on interpreting the results.",
                      "sl": "Orodje {e}: na ravni {l} je dostop mogoč na zahtevo pri projektni "
                            "skupini. Pišite na **{c}** in navedite kodo občine: prejeli boste kodo "
                            "za odklep skupaj z navodili za razlago rezultatov."},
    "sbl_non_conf": {"it": "Sblocco non ancora configurato su questa applicazione.",
                     "en": "Unlocking is not configured on this application yet.",
                     "sl": "Odklepanje na tej aplikaciji še ni nastavljeno."},
    "sbl_campo": {"it": "Codice di sblocco", "en": "Unlock code", "sl": "Koda za odklep"},
    "sbl_bottone": {"it": "Sblocca lo strumento", "en": "Unlock the tool", "sl": "Odkleni orodje"},
    "sbl_ko": {"it": "Codice di sblocco non valido.", "en": "Invalid unlock code.",
               "sl": "Neveljavna koda za odklep."},

    "link_no_foglio": {"it": "Elenco degli strumenti non configurato: aggiungi il foglio LINK al "
                             "file master.",
                       "en": "Tool list not configured: add the LINK sheet to the master file.",
                       "sl": "Seznam orodij ni nastavljen: dodajte list LINK v glavno datoteko."},
    "link_richiesta": {"it": "su richiesta a {c}", "en": "on request to {c}",
                       "sl": "na zahtevo pri {c}"},
    "link_supporto": {"it": "supporto tecnico disponibile", "en": "technical support available",
                      "sl": "tehnična podpora na voljo"},

    "avz_progress": {"it": "{n} di {t} strumenti compilati", "en": "{n} of {t} tools completed",
                     "sl": "{n} od {t} orodij izpolnjenih"},
    "int_maturita": {"it": "Maturità", "en": "Maturity", "sl": "Zrelost"},
    "int_profilo": {"it": "Profilo", "en": "Profile", "sl": "Profil"},
    "sch_vuota": {"it": "Nessun dato disponibile dai questionari precedenti: i parametri vanno "
                        "inseriti a mano.",
                  "en": "No data available from previous questionnaires: parameters must be "
                        "entered manually.",
                  "sl": "Iz prejšnjih vprašalnikov ni podatkov: parametre je treba vnesti ročno."},
    "prosegui": {"it": "Prosegui il percorso", "en": "Continue your pathway",
                 "sl": "Nadaljujte svojo pot"},
    "sch_nota": {"it": "Tutti i valori restano modificabili con i controlli sottostanti.",
                 "en": "All values remain editable with the controls below.",
                 "sl": "Vse vrednosti je mogoče spremeniti s spodnjimi kontrolniki."},
}


def imposta_lingua(codice):
    """Fissa la lingua per tutta la sessione. Accetta 'it', 'en', 'sl'."""
    if codice in ("it", "en", "sl"):
        st.session_state["h2ready_lang"] = codice


def lingua_corrente():
    return st.session_state.get("h2ready_lang", LINGUA_PREDEFINITA)


def TT(chiave, **valori):
    """Testo tradotto nella lingua di sessione, con eventuali segnaposto."""
    voce = TESTI.get(chiave, {})
    testo_tradotto = voce.get(lingua_corrente()) or voce.get("it") or chiave
    return testo_tradotto.format(**valori) if valori else testo_tradotto


def nome_percorso(lettera):
    return TT(f"percorso_{lettera}")


def descrizione_livello(liv):
    return TT(f"liv_{liv}")


# =============================================================================
# LETTURA DEL FOGLIO
# =============================================================================

@st.cache_data(ttl=30, show_spinner=False)
def _leggi(foglio=None):
    """ttl breve: un tool a valle deve vedere subito i dati appena salvati a monte."""
    try:
        cfg = st.secrets["connections"]["gsheets"]
        ha_spreadsheet = "spreadsheet" in cfg
    except Exception:
        ha_spreadsheet = False
    if not ha_spreadsheet:
        raise RuntimeError(
            "Foglio dati non configurato su questa applicazione.\n\n"
            "Su share.streamlit.io: Settings -> Secrets, incollare il blocco "
            "[connections.gsheets] con la chiave 'spreadsheet' e le credenziali "
            "del service account. Ogni app ha i propri Secrets: non si ereditano "
            "dalle altre applicazioni del toolkit."
        )
    conn = st.connection("gsheets", type=GSheetsConnection)
    kwargs = {"ttl": 0}
    if foglio:
        kwargs["worksheet"] = foglio
    df = conn.read(**kwargs)
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all")


def _pulisci_id(valore) -> str:
    """Uniforma il codice per il confronto.

    Toglie spazi e punteggiatura, conserva gli zeri iniziali e ignora le
    maiuscole: cosi' "GemonaH2" e "gemona h2" sono lo stesso Comune.
    Se dopo la pulizia non resta nulla - capita con identificativi fatti di soli
    simboli, come "?????" - si confronta la stringa originale, altrimenti quei
    Comuni non sarebbero raggiungibili.
    """
    grezzo = str(valore or "").strip()
    ripulito = re.sub(r"[^0-9A-Za-z]", "", grezzo)
    return (ripulito or grezzo).lower()


def carica_riga(id_istat):
    """Restituisce la riga del Comune, oppure None se il codice non esiste."""
    codice = _pulisci_id(id_istat)
    if not codice:
        return None
    df = _leggi()
    if COL_ID not in df.columns:
        return None
    confronto = df[COL_ID].astype(str).map(_pulisci_id)
    trovate = df[confronto == codice]
    if trovate.empty:
        # tentativo senza zeri iniziali, per chi digita 30025 invece di 030025
        trovate = df[confronto.str.lstrip("0") == codice.lstrip("0")]
    return None if trovate.empty else trovate.iloc[0]

# =============================================================================
# UTILITY SUI VALORI
# =============================================================================

def vuoto(v) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return str(v).strip().lower() in ("", "nan", "none", "n/a", "-", "na", "null")


def numero(v):
    if vuoto(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = re.sub(r"[^\d,.\-]", "", str(v).strip())
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def valore(riga, colonna, predefinito=None, minimo=None, massimo=None):
    """Valore numerico da usare come default di uno slider.

    Se il dato manca restituisce il predefinito; se esiste lo riporta comunque
    dentro l'intervallo dello slider, altrimenti Streamlit solleva un errore.
    """
    if riga is None or colonna not in riga.index:
        return predefinito
    n = numero(riga[colonna])
    if n is None:
        return predefinito
    if minimo is not None:
        n = max(n, minimo)
    if massimo is not None:
        n = min(n, massimo)
    return n


def vero(valore) -> bool:
    """True se il campo esprime un sì, in italiano, inglese o sloveno."""
    return str(valore).strip().lower() in ("si", "sì", "yes", "y", "true", "vero",
                                           "da", "1", "1.0", "x")


def contestazioni(riga) -> str:
    """Il 2.5 restituisce QUALI tecnologie sono contestate, non un sì/no."""
    valore = riga.get("T25_FLAG_CONTESTAZIONI") if riga is not None else None
    if vuoto(valore):
        return ""
    testo_v = str(valore).strip()
    return "" if testo_v.lower() in ("no", "n", "nessuna", "none", "false", "0", "ne") else testo_v


def testo(riga, colonna, predefinito=""):
    if riga is None or colonna not in riga.index or vuoto(riga[colonna]):
        return predefinito
    return str(riga[colonna]).strip()


def vero(valore) -> bool:
    """True se il campo esprime un sì, in italiano, inglese o sloveno."""
    return str(valore).strip().lower() in ("si", "sì", "yes", "y", "true", "vero",
                                           "da", "1", "1.0", "x")


def intestazione_comune(riga, sottotitolo=""):
    """Barra con il nome del Comune, sempre in cima al tool."""
    if riga is None:
        return
    nome = testo(riga, COL_NOME, "Comune")
    with st.container(border=True):
        c1, c2, c3 = st.columns([3, 1, 1])
        c1.markdown(f"### {nome}")
        if sottotitolo:
            c1.caption(sottotitolo)
        c2.metric(TT("int_maturita"), livello(riga))
        c3.metric(TT("int_profilo"), "".join(l for l, s in percorsi_disponibili(riga).items()
                                             if s["aperto"]) or "n.d.")


def scheda_dati(titolo, voci, avvisi=None):
    """Elenco dei dati ereditati dai questionari precedenti.

    voci: lista di (etichetta, valore_formattato, origine)
    """
    with st.expander(titolo, expanded=True):
        if not voci:
            st.info(TT("sch_vuota"))
        else:
            for etichetta, valore_txt, origine in voci:
                st.markdown(f"- **{etichetta}**: {valore_txt}  "
                            f"<span style='opacity:.55;font-size:.85em'>({origine})</span>",
                            unsafe_allow_html=True)
        for tipo, messaggio in (avvisi or []):
            (st.warning if tipo == "warning" else st.info)(messaggio)
        st.caption(TT("sch_nota"))

# =============================================================================
# SELEZIONE AUTOMATICA DELLA MODALITÀ
# =============================================================================

def modalita_2_6(riga):
    """Suggerisce la modalità del Tool 2.6 dai dati già raccolti.

    Restituisce (chiave, motivazione) dove chiave è "domanda", "superfici"
    o "copertura". La scelta resta dell'utente: questo è solo il preselezionato.
    """
    domanda = ((valore(riga, "T21_FABBISOGNO_H2_TON_ANNO", 0) or 0) +
               (valore(riga, "T22_FABBISOGNO_H2_TON_ANNO", 0) or 0))
    superfici = sum(valore(riga, c, 0) or 0 for c in (
        "T25_SUP_BROWNFIELD_MQ", "T25_SUP_TETTI_IND_MQ", "T25_SUP_TETTI_CIV_MQ",
        "T25_SUP_INCOLTE_MQ", "T25_SUP_SAU_MQ", "T25_SUP_SERVITU_MQ"))

    if domanda > 0 and superfici > 0:
        return "copertura", (
            f"Sono disponibili sia una domanda di {domanda:,.1f} t/anno dal percorso A "
            f"sia {superfici/10000:,.1f} ettari di superfici dal questionario 2.5: la "
            "modalità **copertura** misura quanta parte del fabbisogno il territorio "
            "riesce a soddisfare da solo.")
    if domanda > 0:
        return "domanda", (
            f"È nota una domanda di {domanda:,.1f} t/anno dal percorso A, ma non "
            "risultano superfici censite: la modalità **domanda** parte dal fabbisogno "
            "e calcola quanti impianti servirebbero.")
    if superfici > 0:
        return "superfici", (
            f"Sono censiti {superfici/10000:,.1f} ettari di superfici disponibili ma non "
            "una domanda locale: la modalità **superfici** parte da ciò che c'è e "
            "calcola quanto idrogeno se ne ricava.")
    return "domanda", (
        "Non risultano né una domanda dal percorso A né superfici dal questionario 2.5. "
        "Si parte dalla modalità **domanda** inserendo i valori a mano; per un risultato "
        "attendibile conviene però completare prima i tool 2.1, 2.2 e il questionario 2.5.")


# Soglie della selezione automatica del 2.8. Vanno tarate sui casi reali.
TGM_TRANSITO = 1000        # mezzi/giorno oltre i quali il nodo è di puro transito
TGM_MINIMO = 200           # sotto questa soglia il traffico non regge da solo


def modalita_2_8(riga):
    """Suggerisce la vocazione della stazione: transito, hub o valley.

    Le chiavi coincidono con quelle di CONFIGURAZIONI nel Tool 2.8."""
    tgm = valore(riga, "T27_TGM_CAMION", 0) or 0
    afir = vero(riga.get("T27_FLAG_AFIR_GAP")) if riga is not None else False
    hub = vero(riga.get("T27_FLAG_HUB_MERCI")) if riga is not None else False
    retro = vero(riga.get("T27_FLAG_ACCORDI_FILIERA")) if riga is not None else False
    hta = vero(riga.get("T27_FLAG_SINERGIA_HTA")) if riga is not None else False
    produzione = valore(riga, "T26_PRODUZIONE_H2_TON_ANNO", 0) or 0

    # 1. produzione locale o distretto industriale accanto: la stazione si integra
    if hta or produzione > 0:
        dettaglio = []
        if hta:
            dettaglio.append("il nodo confina con un distretto Hard-to-Abate")
        if produzione > 0:
            dettaglio.append(f"il percorso B prevede una produzione locale di "
                             f"{produzione:,.1f} t/anno")
        return "valley", (
            "Configurazione **H2 integrata**: " + " e ".join(dettaglio) +
            ". La stazione può condividere produzione e stoccaggio con l'utenza "
            "industriale invece di costruirseli, il che cambia radicalmente il "
            "conto economico.")

    # 2. hub merci o accordi di filiera: domanda catturata, non intercettata
    if hub or retro:
        return "hub", (
            "Configurazione **hub intermodale**: la presenza di porti, interporti o "
            "accordi di filiera garantisce una domanda concentrata e prevedibile. "
            "La quota di cattura è più alta che su un nodo di solo transito, perché "
            "i mezzi rientrano in deposito.")

    # 3. traffico di attraversamento
    if tgm >= TGM_TRANSITO:
        motivo = f"il traffico rilevato è di {tgm:,.0f} mezzi pesanti al giorno"
        if afir:
            motivo += (" e il sito colma un vuoto della rete AFIR, che impone una "
                       "stazione ogni 200 km")
        return "transito", (
            "Configurazione **transito**: " + motivo + ". La domanda va intercettata "
            "lungo la direttrice, quindi la quota di cattura dipende da quante altre "
            "stazioni insistono sulla stessa tratta.")

    if afir:
        return "transito", (
            f"Configurazione **transito**: il traffico è contenuto ({tgm:,.0f} mezzi al "
            "giorno) ma il sito colma un vuoto della rete AFIR, che impone una stazione "
            "ogni 200 km. È l'obbligo normativo, più che il volume, a giustificare "
            "l'investimento.")

    return "transito", (
        f"Dati insufficienti per una preselezione: il traffico rilevato "
        f"({tgm:,.0f} mezzi/giorno) è sotto la soglia di sostenibilità e non risultano "
        "hub logistici né sinergie industriali. Verificare il questionario 2.7 prima "
        "di procedere.")

# =============================================================================
# LIVELLO, PUNTEGGI, PERCORSI
# =============================================================================

def livello(riga) -> str:
    punteggio = numero(riga[COL_MATURITA]) if riga is not None and COL_MATURITA in riga.index else None
    if punteggio is None:
        return "L0"
    for lo, hi, etichetta in SOGLIE_MATURITA:
        if lo <= punteggio <= hi:
            return etichetta
    return "L0"


def punteggi(riga) -> dict:
    esito = {}
    for lettera, colonna in COL_SCORE.items():
        if riga is not None and colonna in riga.index:
            n = numero(riga[colonna])
            if n is not None:
                esito[lettera] = n
    return esito


def percorsi_disponibili(riga) -> dict:
    """Applica la regola H2READY.

    Il livello di maturità stabilisce QUANTI percorsi si possono sviluppare;
    il punteggio stabilisce QUALI, e nessun percorso si apre sotto la soglia
    minima, nemmeno per un Comune avanzato.

    Restituisce {"A": {"aperto": bool, "punteggio": float, "motivo": str}, ...}
    """
    liv = livello(riga)
    regola = REGOLE_LIVELLO[liv]
    valori = punteggi(riga)

    # Quando il livello limita il numero di percorsi, vincono quelli con il
    # punteggio piu' alto in valore assoluto; a parita' vale l'ordine A, B, C.
    ordinati = sorted(("A", "B", "C"),
                      key=lambda l: (-(valori.get(l) if valori.get(l) is not None else -999), l))

    esito = {}
    aperti = 0
    for lettera in ordinati:
        p = valori.get(lettera)
        if p is None:
            esito[lettera] = {"aperto": False, "punteggio": None,
                              "motivo": TT("mot_no12")}
            continue
        soglia = SOGLIE_PERCORSO.get(lettera, 13.0)
        if p < soglia:
            esito[lettera] = {"aperto": False, "punteggio": p,
                              "motivo": TT("mot_soglia", p=f"{p:g}", s=f"{soglia:g}")}
            continue
        if aperti >= regola["max_percorsi"]:
            if regola["max_percorsi"] == 1:
                motivo = TT("mot_uno")
            else:
                motivo = TT("mot_max", l=liv, n=regola["max_percorsi"])
            esito[lettera] = {"aperto": False, "punteggio": p, "motivo": motivo}
            continue
        esito[lettera] = {"aperto": True, "punteggio": p, "motivo": ""}
        aperti += 1
    return {l: esito[l] for l in ("A", "B", "C")}


def avanzati_consentiti(riga) -> str:
    """'no' | 'richiesta' | 'libero' per gli strumenti di dimensionamento."""
    return REGOLE_LIVELLO[livello(riga)]["avanzati"]


def accesso_strumento(riga, categoria="base") -> str:
    """Autonomia del Comune su una categoria di strumento.

    categoria: "base" | "avanzato" | "fast"
    Restituisce "libero", "richiesta" oppure "no".
    """
    regola = REGOLE_LIVELLO[livello(riga)]
    if categoria == "avanzato":
        return regola["avanzati"]
    if categoria == "fast":
        return regola["fast"]
    return "libero"

# =============================================================================
# LINK AI TOOL SUCCESSIVI
# =============================================================================

@st.cache_data(ttl=60, show_spinner=False)
def _tabella_link(foglio="LINK"):
    """Legge il foglio LINK del master. Colonne attese:
       tool | nome | url | percorso | categoria | ordine

    Non nasconde gli errori: se la scheda non si legge, chi la sta configurando
    deve vedere il motivo, non un elenco vuoto.
    """
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(worksheet=foglio, ttl=0)
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df.dropna(how="all")


def url_con_contesto(url, id_istat, lingua=None) -> str:
    """Aggiunge ?id=...&lang=... così il tool successivo non richiede il codice.

    L'identificativo viaggia nella sua forma originale, solo codificata per
    l'URL: la normalizzazione serve al confronto, non al trasporto. Passare la
    versione ripulita significherebbe consegnare al tool successivo un codice
    diverso da quello che l'utente ha scritto.
    """
    if not url:
        return ""
    separatore = "&" if "?" in url else "?"
    coda = "id=" + quote(str(id_istat or "").strip(), safe="")
    if lingua:
        coda += f"&lang={lingua}"
    return f"{url}{separatore}{coda}"


def mostra_prossimi_tool(riga, lingua=None, foglio="LINK"):
    """Elenca gli strumenti: attivi come pulsanti, bloccati in grigio col motivo.

    Il foglio LINK ha colonne: tool | nome | url | percorso | categoria | ordine
    dove categoria vale "base", "avanzato" o "fast". Il generatore di Action Plan
    non va inserito nel foglio: e' uno strumento interno al gruppo di progetto.
    """
    try:
        tabella = _tabella_link(foglio)
    except Exception as e:
        st.error(f"{TT('link_no_foglio')}\n\n`{e}`")
        return
    if tabella.empty:
        st.info(TT("link_no_foglio"))
        return

    mancanti = [c for c in ("tool", "url") if c not in tabella.columns]
    if mancanti:
        st.error(f"Nel foglio {foglio} mancano le colonne: {', '.join(mancanti)}. "
                 f"Colonne trovate: {', '.join(tabella.columns)}")
        return

    stato = percorsi_disponibili(riga)
    liv = livello(riga)
    fatti = tool_completati(riga)
    id_istat = testo(riga, COL_ID)

    if "ordine" in tabella.columns:
        tabella = tabella.sort_values("ordine")

    for _, r in tabella.iterrows():
        codice = str(r.get("tool", "")).strip()
        nome = str(r.get("nome", codice)).strip()
        percorso = str(r.get("percorso", "")).strip().upper()
        url = str(r.get("url", "")).strip()

        categoria = str(r.get("categoria", "base")).strip().lower()
        if categoria not in ("base", "avanzato", "fast"):
            # compatibilita' con la vecchia colonna "avanzato" a crocetta
            categoria = "avanzato" if str(r.get("avanzato", "")).strip().lower() in (
                "si", "sì", "true", "1", "x") else "base"

        autonomia = accesso_strumento(riga, categoria)
        bloccato, motivo, nota = False, "", ""

        if percorso in ("A", "B", "C") and not stato[percorso]["aperto"]:
            bloccato, motivo = True, stato[percorso]["motivo"]
        elif autonomia == "no":
            bloccato = True
            motivo = TT("str_no", e=TT("str_fast") if categoria == "fast"
                        else TT("str_avanzato"), l=liv)
        elif autonomia == "richiesta":
            nota = "  ·  " + TT("link_richiesta", c=CONTATTO_PROGETTO)
        elif categoria == "avanzato" and liv == "L2":
            nota = "  ·  " + TT("link_supporto")

        etichetta = f"{codice} - {nome}"
        if fatti.get(codice):
            etichetta = "✔ " + etichetta

        if bloccato:
            st.markdown(
                f"<div style='padding:10px 14px;margin-bottom:8px;border-radius:8px;"
                f"background:#F2F3F5;color:#8A94A0;border:1px solid #E3E6EA'>"
                f"<b>{etichetta}</b><br><span style='font-size:.85rem'>{motivo}</span></div>",
                unsafe_allow_html=True)
        else:
            st.link_button(etichetta + nota, url_con_contesto(url, id_istat, lingua),
                           use_container_width=True)



def dopo_salvataggio(riga, lingua=None):
    """Da chiamare subito dopo un'esportazione riuscita.

    Rilegge la riga del Comune e mostra i passi successivi. Senza questo, il
    tool appena completato risulta ancora da compilare, perché la riga in
    sessione è quella caricata all'ingresso e la lettura del foglio è in cache.
    """
    st.cache_data.clear()
    aggiornata = None
    try:
        aggiornata = carica_riga(testo(riga, COL_ID))
    except Exception:
        aggiornata = None
    if aggiornata is not None:
        st.session_state["h2ready_riga"] = aggiornata
        riga = aggiornata

    st.divider()
    st.subheader(TT("prosegui"))
    mostra_prossimi_tool(riga, lingua=lingua)
    return riga


# =============================================================================
# AVANZAMENTO
# =============================================================================

def tool_completati(riga) -> dict:
    """{'2.1': True, '2.2': False, ...} in base alle colonne testimone."""
    esito = {}
    for codice, colonne in TESTIMONI.items():
        esito[codice] = any(c in riga.index and not vuoto(riga[c]) for c in colonne)
    return esito


def mostra_avanzamento(riga):
    fatti = tool_completati(riga)
    totale = sum(1 for v in fatti.values() if v)
    st.progress(totale / len(fatti), text=TT("avz_progress", n=totale, t=len(fatti)))
    colonne = st.columns(5)
    for i, (codice, ok) in enumerate(fatti.items()):
        colonne[i % 5].markdown(f"{'✅' if ok else '⬜'} **{codice}**")

# =============================================================================
# BLOCCO DI ACCESSO
# =============================================================================

def blocco_accesso(titolo_tool, percorso=None, avanzato=False, categoria=None,
                   consenti_manuale=False, lingua=None):
    """Chiede l'ID_ISTAT e restituisce la riga del Comune; None finché manca.

    percorso: "A" | "B" | "C" -> verifica che il Comune vi abbia accesso
    categoria: "base" | "avanzato" | "fast" -> verifica l'autonomia sul livello.
               Se non indicata, avanzato=True equivale a categoria="avanzato".
    consenti_manuale: se True offre di procedere senza dati (solo simulazione)

    Fermando l'esecuzione prima che i widget esistano, i valori del Comune sono
    gia' disponibili quando gli slider vengono creati.
    """
    if categoria is None:
        categoria = "avanzato" if avanzato else "base"
    if lingua:
        imposta_lingua(lingua)

    if "h2ready_riga" in st.session_state:
        riga = st.session_state["h2ready_riga"]
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.markdown(f"**{testo(riga, COL_NOME, 'Comune')}** "
                        f"· ID {testo(riga, COL_ID)}")
            c2.markdown(f"{TT('int_maturita')} **{livello(riga)}**")
            if c3.button(TT("acc_cambia"), use_container_width=True):
                del st.session_state["h2ready_riga"]
                st.rerun()
        return riga

    if st.session_state.get("h2ready_manuale"):
        st.warning(TT("acc_simulazione"))
        return pd.Series(dtype=object) if consenti_manuale else None

    st.subheader(titolo_tool)
    st.markdown(TT("acc_intro"))

    preimpostato = ""
    try:
        preimpostato = st.query_params.get("id", "")
    except Exception:
        pass

    codice = st.text_input(TT("acc_codice"), value=preimpostato,
                           placeholder="es. 030025")
    procedi = st.button(TT("acc_apri"), type="primary")

    if consenti_manuale:
        if st.button(TT("acc_senza_dati")):
            st.session_state["h2ready_manuale"] = True
            st.rerun()

    if not (procedi or (preimpostato and codice == preimpostato and codice)):
        return None

    try:
        riga = carica_riga(codice)
    except Exception as e:
        st.error(f"{TT('acc_errore_foglio')}\n\n{e}")
        return None
    if riga is None:
        st.error(TT("acc_nontrovato"))
        return None

    liv = livello(riga)
    if liv == "L0":
        st.error(TT("acc_l0"))
        return None

    if percorso in ("A", "B", "C"):
        stato = percorsi_disponibili(riga)[percorso]
        if not stato["aperto"]:
            st.error(TT("acc_percorso_ko", p=percorso, n=nome_percorso(percorso),
                        m=stato["motivo"]))
            st.caption(descrizione_livello(liv))
            return None

    autonomia = accesso_strumento(riga, categoria)
    etichetta = TT("str_fast") if categoria == "fast" else TT("str_avanzato")

    if autonomia == "no":
        st.error(TT("str_no", e=etichetta, l=liv))
        st.caption(descrizione_livello(liv))
        return None

    if autonomia == "richiesta" and not _sblocco_concesso(categoria, liv, etichetta):
        return None

    if autonomia == "libero" and categoria == "avanzato" and liv == "L2":
        st.info(TT("str_supporto", c=CONTATTO_PROGETTO))

    st.session_state["h2ready_riga"] = riga
    st.rerun()


def _sblocco_concesso(categoria, liv, etichetta) -> bool:
    """Strumento accessibile solo su richiesta: chiede il codice di sblocco.

    Il codice si imposta nei Secrets dell'app:
        [h2ready]
        codice_sblocco = "..."
    Se il segreto non e' configurato, lo strumento resta chiuso e viene mostrato
    solo il contatto: meglio un blocco netto di un lucchetto che non chiude.
    """
    st.warning(TT("sbl_richiesta", e=etichetta, l=liv, c=CONTATTO_PROGETTO))

    atteso = None
    try:
        atteso = st.secrets["h2ready"]["codice_sblocco"]
    except Exception:
        atteso = None

    if not atteso:
        st.caption(TT("sbl_non_conf"))
        return False

    chiave = f"h2ready_sbloccato_{categoria}"
    if st.session_state.get(chiave):
        return True

    inserito = st.text_input(TT("sbl_campo"), type="password")
    if st.button(TT("sbl_bottone")):
        if str(inserito).strip() == str(atteso).strip():
            st.session_state[chiave] = True
            return True
        st.error(TT("sbl_ko"))
    return False
