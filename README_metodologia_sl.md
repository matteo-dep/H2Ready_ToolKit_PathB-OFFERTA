### 🧭 Kako orodje deluje

Orodje odgovarja na isto vprašanje s treh strani. Način se izbere na vrhu stranske vrstice in določa le, **od kod izhajamo**: računski motor, urna simulacija in regulatorna preverjanja so v vseh treh primerih enaki.

| Način | Vnesete | Dobite |
|---|---|---|
| **Iz povpraševanja po vodiku** | Cilj proizvodnje (ton/leto) in želena razporeditev naprav | Potrebne moči, **površine, ki jih je treba zagotoviti**, strošek vodika |
| **Iz razpoložljivih površin** | Dejansko razpoložljivi hektarji in kvadratni metri | Proizvedljiv vodik, izvedljive naprave, strošek vodika |
| **Preverjanje pokritosti** | Oboje | Delež potreb, pokrit lokalno, in manjkajoča površina |

Numerično so trije načini ista enačba, rešena za različne neznanke: urna simulacija vedno teče na profilu, normaliziranem na 1 MW nameščene moči OVE, rezultati pa se nato skalirajo. To zagotavlja, da izhod iz 20 MW površin in cilj, ki ga teh 20 MW proizvede, dasta popolnoma enako napravo — lastnost, preverjena z ničelnim odstopanjem.

---

#### Korak 1 — Od površine do moči

Površine so razdeljene v tri družine, ker se razlikujejo po gostoti moči, izkoristku in predvsem po stroških priključitve.

| Vrsta | Formula | Privzeta gostota | Uporabni delež |
|---|---|---|---|
| Na tleh / degradirana območja | ha × delež × MWp/ha | 0,70 MWp/ha | 90 % |
| Strehe | m² × delež × kWp/m² / 1000 | 0,18 kWp/m² | 50 % |
| Industrijske hale | m² × delež × kWp/m² / 1000 | 0,18 kWp/m² | 70 % |

**Uporabni delež** odšteje tisto, česar bruto površina ne more sprejeti: na tleh dostopne poti, postaje in odmike; na strehah severne strešine, dimnike, frčade in statične omejitve; na halah svetlobnike, odvodne stolpiče, pohodne poti in tirnice žerjavov.

**Relativni izkoristek** popravi urni profil glede na optimizirano polje na tleh: 96 % za poševne strehe (usmeritev ni vedno optimalna) in 93 % za hale (ravne strehe z moduli v ravnini ali z majhnim naklonom, bolj občutljivi na umazanijo in temperaturo).

**Veter** ne izhaja iz površine, ampak iz števila vetrnic, ki jih lokacija prenese.

V načinu *povpraševanja* se ista tabela uporablja obratno: iz potrebnih moči orodje izpelje površine, ki jih je treba zagotoviti, po kategorijah.

---

#### Korak 2 — Električni priključek: tu je prava razlika

Tu se tri družine razlikujejo za velikostne rede. Za vsako vrsto se izbere **način povezave z elektrolizerjem**:

- **Namenski neposredni vod** — CAPEX kabla sorazmeren z razdaljo, brez omrežnine. To je konfiguracija, ki omogoča, da se BESS šteje za "za isto priključno točko" po RED III.
- **Javno omrežje (wheeling)** — plača se le priključek na obstoječo točko, prenesena energija pa nosi omrežnino (€/MWh) skozi vso življenjsko dobo.

Uporabljeni stroškovni modeli:

- *Utility scale na tleh*: nad 6 MW priključek na **VN** (730.000 € + 300.000 €/km), pod tem na **SN** (8.000 € + 155.000 €/km). To so vrednosti iz orodja 2.6.
- *Hale*: strošek na priključno točko (uporabniška postaja SN, privzeto 45.000 €), pomnožen s številom lokacij, plus kabel SN (155.000 €/km) pri neposrednem vodu.
- *Strehe*: nižji strošek na priključno točko (privzeto 9.000 €), a pomnožen s praviloma visokim številom točk; kabel NN/SN (90.000 €/km) skoraj vedno naredi neposredni vod neekonomičen, zato je privzeto javno omrežje.

Rezultat: 1 MWp, razpršen na deset streh, stane pri priključitvi bistveno več kot 1 MWp na enem degradiranem območju ob elektrolizerju — tabela "Priključki po vrsti lokacije" to izrecno pokaže.

---

#### Korak 3 — Urna simulacija (8760 h)

Profili OVE izhajajo iz podatkovnih zbirk v repozitoriju (utežena povprečja reprezentativnih območij severne ali južne Italije). Dispečiranje sledi vrstnemu redu: OVE neposredno v elektrolizer, presežek v baterijo (90 % krožni izkoristek), primanjkljaj iz baterije in — le če je omogočeno — iz omrežja. Energija brez odjema je **curtailment**.


Urna bilanca se vedno izide: proizvedena energija = energija v elektrolizer + curtailment + izgube kroženja baterije + sprememba stanja napolnjenosti. Izgube hrambe (10 % na polnem ciklu) so razlog, da je pri delujočem BESS vsota prvih dveh postavk manjša od proizvodnje.
---

#### Korak 4 — Dimenzioniranje elektrolizerja

Velikost je izražena kot odstotek nameščene moči OVE. V **samodejnem** načinu orodje preišče območje 10–120 % in izbere velikost z najnižjim LCOH: majhen elektrolizer obratuje veliko ur, a zavrže energijo, velik zajame konice, a pogosto miruje. Graf občutljivosti prikazuje kompromis, zelena črta pa trenutno izbiro.

---

#### Korak 5 — Skladnost RED III / RFNBO

Modul preverja pogoje Delegirane uredbe (EU) 2023/1184 in izračuna **delež vodika, ki ga je mogoče certificirati**:

1. **Dodatnost** — nove naprave OVE, ki so začele obratovati največ 36 mesecev pred elektrolizerjem.
2. **Brez javne podpore** — brez subvencij ali državne pomoči za naprave OVE. Izbira *lastne proizvodnje* s subvencioniranimi napravami ta pogoj izniči.
3. **Geografska korelacija** — naprave in elektrolizer v istem trgovalnem območju.
4. **Časovna korelacija** — mesečna do leta 2029, **urna od leta 2030**. Pri izključno namenskih napravah je pogoj izpolnjen po konstrukciji. Če je omogočeno dopolnjevanje iz omrežja:
   - v mesečnem scenariju je odjem mogoče izravnati s presežkom OVE istega meseca (do razpoložljivega curtailmenta);
   - v urnem scenariju odjema ni mogoče izravnati in ustvarja **neskladen** vodik, ovrednoten po nižji ceni;
   - izjema je omrežje s potrdilom o več kot 90 % OVE ali manj kot 18 gCO₂eq/MJ, pri katerem je celoten odjem skladen.
5. **Shranjevanje** — BESS je dopusten, če je nameščen za isto priključno točko kot naprave. Če del proizvodnje teče po javnem omrežju, pogoj ni izpolnjen, vendar celotna proizvodnja ne odpade: orodje izloči le **energijo, ki je šla skozi baterijo** in ne izpolnjuje časovne korelacije, preostanek pa ostane certificirljiv.

Če eden od prvih treh pogojev ni izpolnjen, celotna proizvodnja ni certificirljiva: zato plošča prikazuje delež RFNBO ločeno od skupne proizvodnje.

---

#### Korak 6 — Ekonomika

**CAPEX**: elektrolizer, BESS, shranjevanje H2, kompresija (letno anuitetno prek CRF), električni priključki po vrsti lokacije in — pri modelu *lastne proizvodnje* — naprave OVE z ločenimi specifičnimi stroški za tla, strehe in hale.

**OPEX**: energija OVE, kupljena po CfD v modelu PPA/CfD, omrežnina za preneseno energijo, strošek odjema iz omrežja in 3 % CAPEX za O&M.

`LCOH = (OPEX + CAPEX × CRF) / kg H2`, pri 5 % WACC in 20-letni življenjski dobi. Prihodki ločujejo vodik RFNBO od neskladnega in uporabljajo obe ceni iz plošče Trg.

**Možnost "plačaj le porabljeno energijo"**: če je izklopljena, se plača vsa proizvedena energija, vključno s curtailmentom — konzervativna predpostavka, skladna z orodjem 2.6. Če je vklopljena, tveganje curtailmenta nosi proizvajalec OVE.
