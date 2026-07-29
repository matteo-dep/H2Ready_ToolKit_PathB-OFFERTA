### 🧭 Come funziona il tool

Lo strumento risponde alla stessa domanda da tre direzioni diverse. La modalità si sceglie in cima alla barra laterale e determina solo **da dove si parte**: il motore di calcolo, la simulazione oraria e le verifiche normative sono identici in tutti e tre i casi.

| Modalità | Si inserisce | Si ottiene |
|---|---|---|
| **Dalla domanda di idrogeno** | Target di produzione (ton/anno) e ripartizione desiderata degli impianti | Potenze necessarie, **superfici da reperire**, costo dell'idrogeno |
| **Dalle superfici disponibili** | Ettari e metri quadri realmente disponibili | Idrogeno producibile, impianti realizzabili, costo dell'idrogeno |
| **Verifica di copertura** | Entrambi | Quota del fabbisogno coperta dal territorio e superficie mancante |

Sul piano numerico le tre modalità sono la stessa equazione risolta rispetto a incognite diverse: la simulazione oraria viene sempre eseguita su un profilo normalizzato a 1 MW di potenza rinnovabile installata, e i risultati vengono poi scalati. Questo garantisce che partire da 20 MW di superfici o chiedere il target che quei 20 MW producono dia esattamente lo stesso impianto — proprietà verificata con scarto nullo.

---

#### Passo 1 — Da superficie a potenza installabile

Le superfici sono distinte in tre famiglie, perché differiscono per densità di potenza, resa e — soprattutto — costo di connessione.

| Tipologia | Formula | Densità di default | Quota utilizzabile |
|---|---|---|---|
| A terra / brownfield | ha × quota × MWp/ha | 0,70 MWp/ha | 90% |
| Tetti | m² × quota × kWp/m² / 1000 | 0,18 kWp/m² | 50% |
| Capannoni industriali | m² × quota × kWp/m² / 1000 | 0,18 kWp/m² | 70% |

La **quota utilizzabile** sconta ciò che la superficie lorda non può ospitare: a terra accessi, cabine e fasce di rispetto; sui tetti falde esposte a nord, comignoli, abbaini e limiti strutturali; sui capannoni lucernari, torrini di estrazione, camminamenti e vie di corsa dei carriponte.

La **resa relativa** corregge il profilo orario rispetto al campo a terra ottimizzato: 96% per i tetti a falda (orientamenti non sempre ottimali) e 93% per i capannoni (coperture piane con moduli complanari o a bassa inclinazione, più sensibili a sporcamento e temperatura).

L'**eolico** non deriva da una superficie ma dal numero di aerogeneratori installabili nel sito.

In modalità *domanda* la stessa tabella è usata al contrario: dalle potenze necessarie si risale alle superfici da reperire, categoria per categoria.

---

#### Passo 2 — Connessione elettrica: dove sta la differenza vera

È qui che le tre famiglie divergono di ordini di grandezza. Per ogni tipologia si sceglie il **modo di collegamento all'elettrolizzatore**:

- **Linea diretta dedicata** — CAPEX di cavidotto proporzionale alla distanza, nessun onere di trasporto. È la configurazione che consente di considerare il BESS "dietro lo stesso punto di connessione" ai fini RED III.
- **Rete pubblica (wheeling)** — si paga solo l'allaccio al punto esistente, ma l'energia trasportata sconta gli oneri di rete (€/MWh) per tutta la vita dell'impianto.

Modelli di costo applicati:

- *Utility scale a terra*: sopra 6 MW connessione in **AT** (730.000 € + 300.000 €/km), sotto in **MT** (8.000 € + 155.000 €/km). Sono i valori del Tool 2.6.
- *Capannoni*: costo per punto di connessione (cabina utente MT, default 45.000 €) moltiplicato per il numero di siti, più il cavidotto MT (155.000 €/km) se in linea diretta.
- *Tetti*: costo per punto di connessione più basso (default 9.000 €) ma moltiplicato per un numero di punti tipicamente elevato; il cavidotto BT/MT (90.000 €/km) rende quasi sempre antieconomica la linea diretta, per questo il default è la rete pubblica.

Il risultato è che 1 MWp su dieci tetti sparsi costa in connessione molto più di 1 MWp su un unico brownfield adiacente all'elettrolizzatore, e la tabella "Connessioni per tipologia di sito" lo rende esplicito.

---

#### Passo 3 — Simulazione oraria (8760 h)

I profili FER provengono dai dataset presenti nella repository (medie pesate di aree rappresentative del Nord o del Sud Italia). Il dispacciamento segue l'ordine di merito: FER diretta all'elettrolizzatore, surplus in batteria (rendimento round-trip 90%), deficit coperto dalla batteria e — solo se abilitato — dalla rete. L'energia che non trova collocazione è **curtailment**.


Il bilancio orario chiude sempre: energia prodotta = energia all'elettrolizzatore + curtailment + perdite di round-trip della batteria + variazione dello stato di carica. Le perdite di accumulo (10% sul ciclo completo) sono la ragione per cui, con BESS attivo, la somma delle prime due voci è inferiore alla produzione.
---

#### Passo 4 — Dimensionamento dell'elettrolizzatore

La taglia è espressa come percentuale della potenza FER installata. In modalità **automatica** il tool scansiona l'intervallo 10%–120% e sceglie la taglia a minimo LCOH: un elettrolizzatore piccolo lavora molte ore ma spreca energia, uno grande cattura i picchi ma resta fermo. Il grafico di sensitività mostra il compromesso e la linea verde indica la scelta corrente.

---

#### Passo 5 — Conformità RED III / RFNBO

Il modulo verifica le condizioni dell'Atto Delegato (UE) 2023/1184 e calcola la **quota di idrogeno certificabile**:

1. **Addizionalità** — impianti FER nuovi, entrati in esercizio non oltre 36 mesi prima dell'elettrolizzatore.
2. **Assenza di sostegno pubblico** — nessun incentivo o aiuto di Stato sugli impianti FER. Se si sceglie il modello *autoproduzione* con impianti incentivati, la condizione decade.
3. **Correlazione geografica** — impianti ed elettrolizzatore nella stessa zona di offerta.
4. **Correlazione temporale** — mensile fino al 2029, **oraria dal 2030**. Con soli impianti dedicati la condizione è soddisfatta per costruzione. Se si abilita l'integrazione da rete:
   - nello scenario mensile i prelievi sono compensabili con il surplus FER dello stesso mese (fino a concorrenza del curtailment disponibile);
   - nello scenario orario il prelievo non è compensabile e produce idrogeno **non conforme**, valorizzato al prezzo ridotto;
   - fa eccezione la rete certificata con quota FER superiore al 90% o intensità inferiore a 18 gCO₂eq/MJ, che rende conforme l'intero prelievo.
5. **Accumulo** — il BESS è ammesso se collocato dietro lo stesso punto di connessione degli impianti. Se una parte della generazione transita sulla rete pubblica la condizione non è verificata, ma non decade l'intera produzione: il tool scorpora la sola **energia transitata in batteria**, che non soddisfa la correlazione temporale, e lascia certificabile il resto.

Se una delle prime tre condizioni non è soddisfatta, l'intera produzione risulta non certificabile: è la ragione per cui il pannello mostra la quota RFNBO separata dalla produzione totale.

---

#### Passo 6 — Economia

**CAPEX**: elettrolizzatore, BESS, stoccaggio H2, compressione (annualizzata e capitalizzata con CRF), connessioni elettriche per tipologia di sito e — nel modello *autoproduzione* — gli impianti FER, con costi specifici distinti fra terra, tetti e capannoni.

**OPEX**: energia FER acquistata a CfD nel modello PPA/CfD, oneri di trasporto sull'energia in wheeling, costo dei prelievi da rete, più 3% del CAPEX per O&M.

`LCOH = (OPEX + CAPEX × CRF) / kg H2`, con WACC 5% e vita utile 20 anni. I ricavi distinguono l'idrogeno RFNBO da quello non conforme, applicando i due prezzi impostati nel pannello Mercato.

**Opzione "paga solo l'energia assorbita"**: se disattivata si paga tutta l'energia prodotta, curtailment compreso — ipotesi conservativa coerente con il Tool 2.6. Se attivata, il rischio di curtailment resta in capo al produttore FER.
