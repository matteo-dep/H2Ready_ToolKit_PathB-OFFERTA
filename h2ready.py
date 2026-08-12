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
# LETTURA DEL FOGLIO
# =============================================================================

@st.cache_data(ttl=30, show_spinner=False)
def _leggi(foglio=None):
    """ttl breve: un tool a valle deve vedere subito i dati appena salvati a monte."""
    conn = st.connection("gsheets", type=GSheetsConnection)
    kwargs = {"ttl": 0}
    if foglio:
        kwargs["worksheet"] = foglio
    df = conn.read(**kwargs)
    df.columns = [str(c).strip() for c in df.columns]
    return df.dropna(how="all")


def _pulisci_id(valore) -> str:
    """Uniforma il codice: toglie spazi e conserva gli zeri iniziali."""
    testo = re.sub(r"[^0-9A-Za-z]", "", str(valore or "").strip())
    return testo


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
        c2.metric("Maturità", livello(riga))
        p = punteggi(riga)
        c3.metric("Profilo", "".join(l for l, s in percorsi_disponibili(riga).items()
                                     if s["aperto"]) or "n.d.")


def scheda_dati(titolo, voci, avvisi=None):
    """Elenco dei dati ereditati dai questionari precedenti.

    voci: lista di (etichetta, valore_formattato, origine)
    """
    with st.expander(titolo, expanded=True):
        if not voci:
            st.info("Nessun dato disponibile dai questionari precedenti: "
                    "i parametri vanno inseriti a mano.")
        else:
            for etichetta, valore_txt, origine in voci:
                st.markdown(f"- **{etichetta}**: {valore_txt}  "
                            f"<span style='opacity:.55;font-size:.85em'>({origine})</span>",
                            unsafe_allow_html=True)
        for tipo, messaggio in (avvisi or []):
            (st.warning if tipo == "warning" else st.info)(messaggio)
        st.caption("Tutti i valori restano modificabili con i controlli sottostanti.")

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

    # Ordina per margine sulla soglia, non per punteggio assoluto: le tre scale
    # non sono omogenee, quindi 10 su C (soglia 8) vale più di 12 su B (soglia 13).
    def _margine(l):
        p = valori.get(l)
        if p is None:
            return -999
        return p - SOGLIE_PERCORSO.get(l, 13.0)
    ordinati = sorted(("A", "B", "C"), key=lambda l: (-_margine(l), l))

    esito = {}
    aperti = 0
    for lettera in ordinati:
        p = valori.get(lettera)
        if p is None:
            esito[lettera] = {"aperto": False, "punteggio": None,
                              "motivo": "Questionario 1.2 non compilato."}
            continue
        soglia = SOGLIE_PERCORSO.get(lettera, 13.0)
        if p < soglia:
            esito[lettera] = {"aperto": False, "punteggio": p,
                              "motivo": f"Punteggio {p:g}, soglia minima {soglia:g}."}
            continue
        if aperti >= regola["max_percorsi"]:
            if regola["max_percorsi"] == 1:
                motivo = ("Il livello L1 consente di sviluppare un solo percorso, "
                          "assegnato a quello con il punteggio più alto.")
            else:
                motivo = (f"Il livello {liv} consente di sviluppare "
                          f"{regola['max_percorsi']} percorsi, assegnati a quelli "
                          "con il punteggio più alto.")
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

@st.cache_data(ttl=300, show_spinner=False)
def _tabella_link(foglio="LINK"):
    """Legge il foglio LINK del master. Colonne attese:
       tool | nome | url | percorso | livello_min | avanzato | ordine
    """
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(worksheet=foglio, ttl=0)
        df.columns = [str(c).strip().lower() for c in df.columns]
        return df.dropna(how="all")
    except Exception:
        return pd.DataFrame()


def url_con_contesto(url, id_istat, lingua=None) -> str:
    """Aggiunge ?id=...&lang=... così il tool successivo non richiede il codice."""
    if not url:
        return ""
    separatore = "&" if "?" in url else "?"
    coda = f"id={_pulisci_id(id_istat)}"
    if lingua:
        coda += f"&lang={lingua}"
    return f"{url}{separatore}{coda}"


def mostra_prossimi_tool(riga, lingua=None, foglio="LINK"):
    """Elenca gli strumenti: attivi come pulsanti, bloccati in grigio col motivo.

    Il foglio LINK ha colonne: tool | nome | url | percorso | categoria | ordine
    dove categoria vale "base", "avanzato" o "fast". Il generatore di Action Plan
    non va inserito nel foglio: e' uno strumento interno al gruppo di progetto.
    """
    tabella = _tabella_link(foglio)
    if tabella.empty:
        st.info("Elenco degli strumenti non configurato: aggiungi il foglio LINK "
                "al file master.")
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
            motivo = (f"Strumento {'H2 FAST' if categoria == 'fast' else 'avanzato'}: "
                      f"non disponibile al livello {liv}.")
        elif autonomia == "richiesta":
            nota = f"  ·  su richiesta a {CONTATTO_PROGETTO}"
        elif categoria == "avanzato" and liv == "L2":
            nota = "  ·  supporto tecnico disponibile"

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
    st.progress(totale / len(fatti), text=f"{totale} di {len(fatti)} strumenti compilati")
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

    if "h2ready_riga" in st.session_state:
        riga = st.session_state["h2ready_riga"]
        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 1, 1])
            c1.markdown(f"**{testo(riga, COL_NOME, 'Comune')}** "
                        f"· ID {testo(riga, COL_ID)}")
            c2.markdown(f"Maturità **{livello(riga)}**")
            if c3.button("Cambia Comune", use_container_width=True):
                del st.session_state["h2ready_riga"]
                st.rerun()
        return riga

    if st.session_state.get("h2ready_manuale"):
        st.warning("Modalità simulazione: i dati non verranno collegati ad alcun Comune.")
        return pd.Series(dtype=object) if consenti_manuale else None

    st.subheader(titolo_tool)
    st.markdown("Per procedere serve il **codice identificativo del Comune**, lo stesso "
                "usato nei questionari 1.1 e 1.2. I parametri già raccolti verranno "
                "caricati automaticamente negli strumenti di calcolo.")

    preimpostato = ""
    try:
        preimpostato = st.query_params.get("id", "")
    except Exception:
        pass

    codice = st.text_input("Codice identificativo", value=preimpostato,
                           placeholder="es. 030025")
    procedi = st.button("Apri lo strumento", type="primary")

    if consenti_manuale:
        if st.button("Procedi senza dati (solo simulazione)"):
            st.session_state["h2ready_manuale"] = True
            st.rerun()

    if not (procedi or (preimpostato and codice == preimpostato and codice)):
        return None

    riga = carica_riga(codice)
    if riga is None:
        st.error("Codice non trovato nel database. Verifica di aver completato il "
                 "questionario 1.1, oppure controlla il codice inserito.")
        return None

    liv = livello(riga)
    if liv == "L0":
        st.error("Il Comune non ha ancora un livello di maturità assegnato: "
                 "completa prima il questionario 1.1.")
        return None

    if percorso in ("A", "B", "C"):
        stato = percorsi_disponibili(riga)[percorso]
        if not stato["aperto"]:
            st.error(f"Percorso {percorso} ({NOMI_PERCORSO[percorso]}) non attivo per "
                     f"questo Comune. {stato['motivo']}")
            st.caption(REGOLE_LIVELLO[liv]["descrizione"])
            return None

    autonomia = accesso_strumento(riga, categoria)
    etichetta = "H2 FAST" if categoria == "fast" else "di dimensionamento avanzato"

    if autonomia == "no":
        st.error(f"Strumento {etichetta}: non disponibile al livello {liv}.")
        st.caption(REGOLE_LIVELLO[liv]["descrizione"])
        return None

    if autonomia == "richiesta" and not _sblocco_concesso(categoria, liv, etichetta):
        return None

    if autonomia == "libero" and categoria == "avanzato" and liv == "L2":
        st.info("Strumento di dimensionamento: al livello L2 è disponibile il supporto "
                f"tecnico del gruppo di progetto ({CONTATTO_PROGETTO}). Puoi procedere "
                "in autonomia, ma per usare i risultati in un atto formale conviene una "
                "verifica congiunta.")

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
    st.warning(f"Strumento {etichetta}: al livello {liv} l'accesso avviene su richiesta "
               f"al gruppo di progetto. Scrivi a **{CONTATTO_PROGETTO}** indicando il "
               "codice del Comune: riceverai il codice di sblocco insieme alle "
               "indicazioni per interpretare i risultati.")

    atteso = None
    try:
        atteso = st.secrets["h2ready"]["codice_sblocco"]
    except Exception:
        atteso = None

    if not atteso:
        st.caption("Sblocco non ancora configurato su questa applicazione.")
        return False

    chiave = f"h2ready_sbloccato_{categoria}"
    if st.session_state.get(chiave):
        return True

    inserito = st.text_input("Codice di sblocco", type="password")
    if st.button("Sblocca lo strumento"):
        if str(inserito).strip() == str(atteso).strip():
            st.session_state[chiave] = True
            return True
        st.error("Codice di sblocco non valido.")
    return False
