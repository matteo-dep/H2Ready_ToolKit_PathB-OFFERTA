### 🧭 Kako orodje deluje

Orodje odgovarja na isto vprašanje s treh različnih strani. Način se izbere na vrhu vnosnega lista in določa le, **od kod se začne**: računski motor, urna simulacija in regulatorna preverjanja so v vseh treh primerih enaki.

| Način | Vnesete | Dobite |
|---|---|---|
| **Iz povpraševanja po vodiku** | Cilj proizvodnje (t/leto) in želena porazdelitev naprav | Potrebne moči, **površine, ki jih je treba najti**, strošek vodika |
| **Iz razpoložljivih površin** | Hektarji in kvadratni metri, ki so dejansko na voljo | Proizvodljiv vodik, izvedljive naprave, strošek vodika |
| **Preverjanje pokritosti** | Oboje | Delež potreb, ki jih pokrije območje, in manjkajoča površina |

Številčno so vsi trije načini ista enačba, rešena glede na različne neznanke: urna simulacija vedno teče na profilu, normaliziranem na 1 MW nameščene moči, rezultati pa se nato preračunajo. To zagotavlja, da izhod iz 20 MW površin ali zahteva po cilju, ki ga teh 20 MW proizvede, dasta natanko isto napravo — lastnost, preverjena z ničelnim odstopanjem.

Delo poteka v dveh korakih: izpolni se list, nato se pritisne **Zaženi dimenzioniranje**. Ločitev ni kozmetična: simulacija teče na 8.760 urah in nima smisla, da se ponovi ob vsakem premiku drsnika. Iz rezultatov se vrnete na list z **Uredi parametre**, pri čemer ostanejo vse prejšnje izbire.

---

#### Korak 1 — Od površine do namestljive moči

Površine so razdeljene v tri družine, ker se razlikujejo po gostoti moči, donosu in predvsem po stroških priključitve.

| Vrsta | Formula | Privzeta gostota | Uporabni delež |
|---|---|---|---|
| Na tleh / brownfield / utility scale | ha × delež × MWp/ha | 0,70 MWp/ha | 90% |
| Strehe | m² × delež × kWp/m² / 1000 | 0,18 kWp/m² | 50% |
| Industrijske hale | m² × delež × kWp/m² / 1000 | 0,18 kWp/m² | 70% |

**Uporabni delež** odšteje tisto, česar bruto površina ne more sprejeti: na tleh dostope, transformatorske postaje in varovalne pasove; na strehah severne strešine, dimnike, frčade in konstrukcijske omejitve; na halah svetlobnike, odzračevalne stolpiče, pohodne poti in tirnice žerjavov.

**Relativni donos** popravi urni profil glede na optimizirano polje na tleh: 96% za poševne strehe (usmeritve niso vedno optimalne) in 93% za hale (ravne kritine z vzporednimi ali malo nagnjenimi moduli, bolj občutljive na umazanijo in temperaturo). Gostote in donosi so med naprednimi parametri: so projektne vrednosti in privzete ustrezajo veliki večini primerov.

**Veter** ne izhaja iz površine, temveč iz števila vetrnic, ki jih je mogoče postaviti.

V načinu *povpraševanje* se ista tabela uporabi obratno: iz potrebnih moči nazaj k površinam, ki jih je treba zagotoviti.

---

#### Korak 2 — Obstoječa naprava

Mogoče je dodati dejansko napravo, ki že obratuje — hidroelektrarno, biomaso, soproizvodnjo — z nalaganjem njenega **izmerjenega urnega profila**. Datoteka potrebuje dva stolpca, uro od 0 do 8759 in povprečno moč v kW, za vseh 8.760 vrstic; kjer naprava miruje, se vpiše nič. Predlogo je mogoče prenesti iz samega orodja, v Excelu ali CSV.

Obravnava se razlikuje od drugih kategorij iz preprostega razloga: **dejanska naprava se ne prilagaja**. Druge moči rastejo ali padajo, dokler se dimenzioniranje ne izide; elektrarna je taka, kot je. Zato je obravnavana kot peta kategorija, katere delež se preračuna tako, da izhodna moč ostane enaka prijavljeni nazivni moči.

V načinu *površine* je izračun neposreden. V načinu *povpraševanje* se problem ugrizne v rep — kombinirani profil je odvisen od skupne velikosti, ta pa od profila — in se reši s fiksno točko, ki konvergira v dveh ali treh iteracijah. Če že sama obstoječa naprava presega cilj, se dimenzioniranje ustavi pri njeni moči in presežek se navede, namesto da bi se zmanjšala elektrarna, ki obstaja.

Na stroškovni strani naprava ne vstopa v CAPEX, saj je že zgrajena in plačana, in ne plača priključitve, razen če se položi namenski kabel do elektrolizerja. Njena energija pa se vedno plača po lastni odkupni ceni: tudi pri lastni proizvodnji gre za napravo tretjih ali že amortizirano.

Orodje uporablja dve **preverjanji verjetnosti**, ki opozorita, a ne blokirata. Prvo primerja ekvivalentne ure s tipičnim razponom za prijavljeni vir: 3.000-4.500 h za pretočno hidroelektrarno, 2.000-3.500 za akumulacijsko, 6.000-8.000 za biomaso in soproizvodnjo, 1.800-2.500 za veter, 1.000-1.300 za fotovoltaiko. Drugo išče dolge odseke pri ničli: nad 500 zaporednih ur to ni sezonskost, temveč zaustavitev naprave ali vrzel v podatkih, in uporaba takega profila vodi k podcenjeni proizvodnji.

---

#### Korak 3 — Električna priključitev: kje je prava razlika

Tu se tri družine razlikujejo za velikostne razrede. Za vsako vrsto se izbere **način priključitve na elektrolizer**:

- **Namenski neposredni vod** — CAPEX kabla sorazmeren z razdaljo, brez stroškov prenosa. To je konfiguracija, ki omogoča, da se BESS šteje za "za istim priključnim mestom" po RED III.
- **Javno omrežje (wheeling)** — plača se le priključitev na obstoječo točko, prenesena energija pa nosi omrežnino (€/MWh) za vso življenjsko dobo naprave.

*Wheeling* je pristojbina, ki jo operater zaračuna za vsako kilovatno uro, ki potuje po javnem omrežju. Prelomna točka med potema je skoraj v celoti odvisna od razdalje: pod 2-3 kilometri skoraj vedno zmaga neposredni vod, nad desetimi skoraj nikoli.

Uporabljeni stroškovni modeli:

- *Utility scale na tleh*: nad 6 MW priključitev na **VN** (730.000 € + 300.000 €/km), pod tem na **SN** (8.000 € + 155.000 €/km).
- *Hale*: strošek na priključno točko (uporabniška SN postaja, privzeto 45.000 €), pomnožen s številom lokacij, plus SN kabel (155.000 €/km) pri neposrednem vodu.
- *Strehe*: nižji strošek na priključno točko (privzeto 9.000 €), a pomnožen s tipično visokim številom točk; NN/SN kabel (90.000 €/km) neposredni vod skoraj vedno naredi neekonomičen, zato je privzeto javno omrežje.

Rezultat je, da 1 MWp, razpršen po desetih strehah, stane pri priključitvi veliko več kot 1 MWp na enem samem brownfieldu ob elektrolizerju, in tabela "Priključitve po vrsti lokacije" to izrecno pokaže.

---

#### Korak 4 — Urna simulacija (8760 h)

Profili obnovljivih virov izhajajo iz naborov podatkov v repozitoriju (uteženih povprečij reprezentativnih območij severne ali južne Italije), prišteti profilu obstoječe naprave, če je naložen. Razporejanje sledi vrstnemu redu: obnovljivi viri neposredno v elektrolizer, presežek v baterijo (izkoristek celotnega cikla 90%), primanjkljaj iz baterije in — le če je omogočeno — iz omrežja. Energija, ki ne najde mesta, je **curtailment**.

Urna bilanca se vedno izide: proizvedena energija = energija v elektrolizer + curtailment + izgube cikla baterije + sprememba stanja napolnjenosti. Izgube shranjevanja (10% na celotnem ciklu) so razlog, da je z aktivnim BESS vsota prvih dveh postavk manjša od proizvodnje.

Profil, ki dopolnjuje fotovoltaiko — hidroelektrarna proizvaja ponoči in v prehodnih letnih časih — poveča obratovalne ure elektrolizerja in zmanjša potrebno shranjevanje. To je učinek, zaradi katerega je hibridizacija zanimiva, in ga je mogoče neposredno razbrati iz urnega grafa in iz curtailmenta.

---

#### Korak 5 — Dimenzioniranje elektrolizerja

Velikost je izražena kot odstotek nameščene moči obnovljivih virov. V **samodejnem** načinu orodje pregleda razpon 10%–120% in izbere velikost z najnižjim LCOH: majhen elektrolizer dela veliko ur, a zapravlja energijo, velik zajame konice, a pogosto miruje. Graf občutljivosti prikazuje kompromis, zelena črta pa označuje trenutno izbiro.

---

#### Korak 6 — Skladnost z RED III / RFNBO

Modul preveri pogoje Delegirane uredbe (EU) 2023/1184 in izračuna **delež vodika, ki ga je mogoče certificirati**:

1. **Dodatnost** — nove naprave, ki so začele obratovati največ 36 mesecev pred elektrolizerjem.
2. **Odsotnost javne podpore** — brez spodbud ali državne pomoči za naprave. Če se izbere model *lastne proizvodnje* s subvencioniranimi napravami, pogoj odpade.
3. **Geografska korelacija** — naprave in elektrolizer v istem trgovalnem območju.
4. **Časovna korelacija** — mesečna do leta 2029, **urna od leta 2030**. Zgolj z namenskimi napravami je pogoj izpolnjen po sami zasnovi. Če se omogoči dopolnjevanje iz omrežja:
   - v mesečnem scenariju je odjem mogoče izravnati s presežkom istega meseca (do razpoložljivega curtailmenta);
   - v urnem scenariju odjema ni mogoče izravnati in proizvede **neskladen** vodik, vrednoten po znižani ceni;
   - izjema je certificirano omrežje z deležem obnovljivih virov nad 90% ali intenzivnostjo pod 18 gCO₂eq/MJ, ki naredi skladen celoten odjem.
5. **Shranjevanje** — BESS je dovoljen, če je nameščen za istim priključnim mestom kot naprave. Če del proizvodnje potuje po javnem omrežju, pogoj ni izpolnjen, a ne odpade celotna proizvodnja: orodje izloči le **energijo, ki je šla skozi baterijo**, ostalo pa ostane certificirljivo.
6. **Obstoječa naprava** — to je točka, ki najpogosteje preseneti. Elektrarna, ki obratuje že leta, **ni dodatna**, in če prejema spodbude, krši tudi drugi pogoj. Orodje zato privzeto predpostavi, da ni, in izloči delež vodika, proizvedenega z njeno energijo, po istem merilu kot pri neskladnem shranjevanju. Potrditveno polje *dodatna naprava* se uporabi le v dejanskem primeru, ko naprava obratuje manj kot 36 mesecev in ne prejema nobene javne podpore.

To zadnjo točko velja izrecno poudariti, ker ima težke praktične posledice. **Nova** pretočna hidroelektrarna je povsem združljiva z dodatnostjo in je celo idealna partnerica fotovoltaike zaradi dopolnjujočega profila. Če pa prejema spodbude za obnovljive vire, dodatnost odpade: pri mali hidroenergiji je treba izbrati med spodbudo in certifikacijo RFNBO — obojega ni mogoče imeti.

Če eden od prvih treh pogojev ni izpolnjen, celotna proizvodnja ni certificirljiva: zato plošča prikazuje delež RFNBO ločeno od skupne proizvodnje.

---

#### Korak 7 — Ekonomika

**CAPEX**: elektrolizer, BESS, shranjevanje H2, stiskanje (letno razporejeno in kapitalizirano s CRF), električne priključitve po vrsti lokacije in — pri modelu *lastne proizvodnje* — naprave, z ločenimi specifičnimi stroški za tla, strehe in hale. Obstoječa naprava se ne pojavi: je zgrajena in plačana.

**OPEX**: energija, kupljena po CfD v modelu PPA/CfD, energija obstoječe naprave po njeni odkupni ceni, stroški prenosa za energijo v wheelingu, strošek odjema iz omrežja, plus 3% CAPEX za obratovanje in vzdrževanje.

`LCOH = (OPEX + CAPEX × CRF) / kg H2`, s 5% WACC in 20-letno življenjsko dobo. Prihodki ločujejo vodik RFNBO od neskladnega, z uporabo obeh cen iz plošče Trg.

**PPA** (*Power Purchase Agreement*) je večletna pogodba za nakup energije od proizvajalca iz obnovljivih virov po vnaprej določeni ceni. Za elektrolizer rešuje dve težavi: odpravi cenovno tveganje — elektrika je prevladujoča postavka LCOH in brez znane cene projekt ni financirljiv — in prepreči vezavo kapitala, zemljišč in dovoljenj. V zameno se dvajset let plačuje dobava, ki bi bila pri lastni proizvodnji po amortizaciji skoraj brezplačna. Primerjava obeh modelov je prav namen zavihka Ekonomika.

**Možnost "plačaj le absorbirano energijo"**: če je izklopljena, se plača vsa proizvedena energija, vključno s curtailmentom — konservativna predpostavka. Če je vklopljena, tveganje curtailmenta ostane pri proizvajalcu.
