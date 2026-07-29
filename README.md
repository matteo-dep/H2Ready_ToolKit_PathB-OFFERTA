# H2READY Toolkit — Tool 2.6: produzione di idrogeno verde

App Streamlit sviluppata nel progetto **Interreg Italia-Slovenia H2READY** (APE FVG).

Un unico programma, tre modalità di analisi che condividono lo stesso motore di calcolo:

| Modalità | Si parte da | Si ottiene |
|---|---|---|
| **Domanda** | target di produzione (ton/anno) | potenze e **superfici necessarie** |
| **Superfici** | ettari e m² disponibili | **idrogeno producibile** |
| **Copertura** | entrambi | quota di fabbisogno coperta dal territorio |

Le superfici sono distinte in **a terra / brownfield utility scale**, **tetti** e
**capannoni industriali**, con connessioni elettriche modellate separatamente
(linea diretta o rete pubblica, AT/MT/BT), e la produzione è verificata rispetto
alle condizioni **RED III / RFNBO** dell'Atto Delegato (UE) 2023/1184.

## Struttura del repository
```
app_h2ready.py               # interfaccia: modalità, input, schede di output
core.py                      # motore tecnico ed economico (simulazione, RED III, costi)
i18n.py                      # dizionario multilingua IT / EN / SL
README_metodologia_it.md     # metodologia, caricata nell'expander in pagina
README_metodologia_en.md
README_metodologia_sl.md
dataset_fotovoltaico_produzione.csv
dataset_eolico_produzione.csv
requirements.txt
```

## Dataset di produzione
Vengono cercati automaticamente nella cartella dell'app e nelle sottocartelle
`data/`, `dataset/`, `datasets/`, `db/`. Sono accettati anche i nomi brevi
`dataset_fotovoltaico.csv` e `dataset_eolico.csv`.

Le intestazioni delle colonne devono corrispondere **carattere per carattere**
alle chiavi dei pesi in `core.py`, apostrofi tipografici e spazi compresi. Se il
caricamento fallisce l'app continua con profili sintetici ma lo dichiara con un
messaggio in rosso e apre un pannello di diagnostica che elenca le colonne
attese e non trovate.

## Deploy su Streamlit Community Cloud
1. Push del repository su GitHub.
2. share.streamlit.io → *New app* → repo, branch e `app_h2ready.py`.
3. Impostare Python **3.11 o 3.12** nelle opzioni avanzate: numba pubblica i
   wheel precompilati con qualche mese di ritardo sulle versioni più recenti.
4. Se la build di numba fallisce, rimuovere la riga `numba` da
   `requirements.txt`: l'app ha un fallback in puro Python e continua a
   funzionare (in sidebar è indicata la modalità attiva).

## Esecuzione locale
```bash
pip install -r requirements.txt
streamlit run app_h2ready.py
```

## Architettura di calcolo
La simulazione oraria 8760h è sempre eseguita su un profilo **normalizzato a
1 MW** di potenza rinnovabile installata: gli aggregati energetici che ne
derivano scalano linearmente e vengono riusati da tutte e tre le modalità. La
scansione tecnica (23 taglie di elettrolizzatore) è in cache e dipende solo da
profilo, accumulo e rete; l'economia è aritmetica pura su quegli aggregati.
Muovere un prezzo o un CAPEX non fa ripartire nessuna simulazione.

## Esportazione
Il payload verso il database centrale usa il prefisso `T26_` per le chiavi
comuni e `T26B_` per le superfici, e include il campo `T26_MODALITA` per
distinguere sul foglio le righe generate dai tre approcci.
