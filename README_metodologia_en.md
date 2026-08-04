### 🧭 How the tool works

The tool answers the same question from three different directions. The mode is chosen at the top of the input sheet and only determines **where you start from**: the calculation engine, the hourly simulation and the regulatory checks are identical in all three cases.

| Mode | You enter | You get |
|---|---|---|
| **From hydrogen demand** | Production target (t/year) and desired split across plant types | Required capacity, **surfaces to be found**, hydrogen cost |
| **From available surfaces** | Hectares and square metres actually available | Producible hydrogen, feasible plants, hydrogen cost |
| **Coverage check** | Both | Share of demand covered by the territory and missing surface |

Numerically the three modes are the same equation solved for different unknowns: the hourly simulation always runs on a profile normalised to 1 MW of installed renewable capacity, and results are scaled afterwards. This guarantees that starting from 20 MW of surfaces, or asking for the target those 20 MW produce, yields exactly the same plant — a property verified with zero deviation.

Work proceeds in two steps: fill in the sheet, then press **Start sizing**. The separation is not cosmetic: the simulation runs over 8,760 hours and there is no point re-running it at every slider movement. From the results you return to the sheet with **Edit parameters**, finding all previous choices intact.

---

#### Step 1 — From surface to installable capacity

Surfaces are split into three families because they differ in power density, yield and — above all — connection cost.

| Type | Formula | Default density | Usable share |
|---|---|---|---|
| Ground-mounted / brownfield / utility scale | ha × share × MWp/ha | 0.70 MWp/ha | 90% |
| Roofs | m² × share × kWp/m² / 1000 | 0.18 kWp/m² | 50% |
| Industrial sheds | m² × share × kWp/m² / 1000 | 0.18 kWp/m² | 70% |

The **usable share** discounts what the gross surface cannot host: on the ground, access roads, substations and setback strips; on roofs, north-facing pitches, chimneys, dormers and structural limits; on sheds, skylights, extraction turrets, walkways and crane runways.

The **relative yield** corrects the hourly profile against an optimised ground-mounted field: 96% for pitched roofs (orientations not always optimal) and 93% for sheds (flat coverings with coplanar or low-tilt modules, more sensitive to soiling and temperature). Densities and yields sit among the advanced parameters: they are design values and the defaults hold in the vast majority of cases.

**Wind** does not derive from a surface but from the number of turbines installable on site.

In *demand* mode the same table is used in reverse: from the required capacity back to the surfaces to be found, category by category.

---

#### Step 2 — Existing plant

A real plant already in operation — hydro, biomass, cogeneration — can be added by uploading its **measured hourly profile**. The file needs two columns, the hour from 0 to 8759 and the average power in kW, for all 8,760 rows; write zero where the plant is idle. The template can be downloaded from the tool itself, in Excel or CSV.

Its treatment differs from the other categories for a simple reason: **a real plant does not scale**. The other capacities grow or shrink until the sizing balances; the power station is what it is. It is therefore handled as a fifth category whose share is recomputed so that the resulting capacity stays equal to the declared rating.

In *surfaces* mode the calculation is immediate. In *demand* mode the problem bites its own tail — the combined profile depends on total size, which in turn depends on the profile — and is solved with a fixed point converging in two or three iterations. If the existing plant alone exceeds the target, sizing stops at its rated power and the surplus is declared, rather than shrinking a plant that exists.

On the cost side the plant does not enter CAPEX, being already built and paid for, and pays no connection unless a dedicated cable is laid towards the electrolyser. Its energy, however, is always paid for at its own transfer price: even under self-production it belongs to a third party or is already depreciated.

The tool applies two **plausibility checks**, which warn without blocking. The first compares equivalent hours against the typical range for the declared source: 3,000-4,500 h for run-of-river hydro, 2,000-3,500 for reservoir hydro, 6,000-8,000 for biomass and cogeneration, 1,800-2,500 for wind, 1,000-1,300 for photovoltaics. The second looks for long stretches at zero: beyond 500 consecutive hours this is not seasonality but an outage or a gap in the data, and using it for sizing leads to underestimating production.

---

#### Step 3 — Electrical connection: where the real difference lies

This is where the three families diverge by orders of magnitude. For each type you choose the **way of connecting to the electrolyser**:

- **Dedicated direct line** — cable CAPEX proportional to distance, no transport charges. It is the configuration that allows the BESS to be considered "behind the same connection point" for RED III purposes.
- **Public grid (wheeling)** — you only pay to join at the existing point, but the energy carried bears network charges (€/MWh) for the whole life of the plant.

*Wheeling* is the toll the operator applies to every kilowatt-hour travelling on the public grid. The break-even between the two routes depends almost entirely on distance: below 2-3 kilometres the direct line nearly always wins, above ten it nearly never does.

Cost models applied:

- *Utility scale ground*: above 6 MW connection at **HV** (€730,000 + €300,000/km), below at **MV** (€8,000 + €155,000/km).
- *Sheds*: cost per connection point (MV user substation, default €45,000) times the number of sites, plus MV cable (€155,000/km) if on a direct line.
- *Roofs*: lower cost per connection point (default €9,000) but multiplied by a typically high number of points; the LV/MV cable (€90,000/km) makes a direct line almost always uneconomic, hence the public-grid default.

The result is that 1 MWp spread over ten roofs costs far more in connection than 1 MWp on a single brownfield next to the electrolyser, and the "Connections by site type" table makes it explicit.

---

#### Step 4 — Hourly simulation (8760 h)

Renewable profiles come from the datasets in the repository (weighted averages of representative areas in Northern or Southern Italy), added to the existing plant profile where uploaded. Dispatch follows merit order: renewables direct to the electrolyser, surplus to the battery (90% round-trip efficiency), deficit covered by the battery and — only if enabled — by the grid. Energy that finds no home is **curtailment**.

The hourly balance always closes: energy produced = energy to the electrolyser + curtailment + battery round-trip losses + change in state of charge. Storage losses (10% over the full cycle) are why, with the BESS active, the sum of the first two items falls short of production.

A profile complementary to photovoltaics — hydro produces at night and in the shoulder seasons — raises electrolyser running hours and reduces the storage needed. This is the effect that makes hybridisation attractive, and it reads directly in the hourly chart and in curtailment.

---

#### Step 5 — Electrolyser sizing

Size is expressed as a percentage of installed renewable capacity. In **automatic** mode the tool scans the 10%–120% range and picks the size with the lowest LCOH: a small electrolyser runs many hours but wastes energy, a large one captures the peaks but sits idle. The sensitivity chart shows the trade-off and the green line marks the current choice.

---

#### Step 6 — RED III / RFNBO compliance

The module checks the conditions of Delegated Act (EU) 2023/1184 and computes the **certifiable share of hydrogen**:

1. **Additionality** — new renewable plants, in operation no earlier than 36 months before the electrolyser.
2. **No public support** — no incentives or State aid on the renewable plants. Choosing the *self-production* model with supported plants voids the condition.
3. **Geographic correlation** — plants and electrolyser in the same bidding zone.
4. **Temporal correlation** — monthly until 2029, **hourly from 2030**. With dedicated plants alone the condition holds by construction. If grid integration is enabled:
   - in the monthly scenario, withdrawals can be offset against renewable surplus in the same month (up to the available curtailment);
   - in the hourly scenario the withdrawal cannot be offset and produces **non-compliant** hydrogen, valued at the reduced price;
   - the exception is certified grid supply above 90% renewable share or below 18 gCO₂eq/MJ, which makes the whole withdrawal compliant.
5. **Storage** — the BESS is allowed if placed behind the same connection point as the plants. If part of the generation travels on the public grid the condition fails, but not all production is lost: the tool strips out only the **energy that passed through the battery**, which does not satisfy temporal correlation, leaving the rest certifiable.
6. **Existing plant** — this is the point that surprises most often. A station operating for years **is not additional**, and if it receives incentives it also breaches the second condition. The tool therefore assumes by default that it is not, and strips out the share of hydrogen produced with its energy, using the same criterion applied to non-compliant storage. The *additional plant* checkbox should be ticked only in the real case where the station started operating less than 36 months ago and receives no public support.

This last point deserves being explicit, because its practical consequences are heavy. A **new** run-of-river hydro plant is fully compatible with additionality, and is indeed the ideal partner for photovoltaics thanks to its complementary profile. But if it takes renewable incentives, additionality is voided: on small hydro one must choose between the incentive and RFNBO certification — both are not available.

If any of the first three conditions fails, the entire production is non-certifiable: this is why the panel shows the RFNBO share separately from total production.

---

#### Step 7 — Economics

**CAPEX**: electrolyser, BESS, H2 storage, compression (annualised and capitalised with CRF), electrical connections by site type and — under *self-production* — the renewable plants, with distinct specific costs for ground, roofs and sheds. The existing plant does not appear: it is built and paid for.

**OPEX**: renewable energy bought at CfD under the PPA/CfD model, existing plant energy at its transfer price, transport charges on wheeled energy, cost of grid withdrawals, plus 3% of CAPEX for O&M.

`LCOH = (OPEX + CAPEX × CRF) / kg H2`, with 5% WACC and 20-year lifetime. Revenues distinguish RFNBO hydrogen from non-compliant hydrogen, applying the two prices set in the Market panel.

A **PPA** (*Power Purchase Agreement*) is a multi-year contract to buy energy from a renewable producer at a price fixed in advance. For an electrolyser it solves two problems: it removes price risk — electricity is the dominant item in LCOH, and without a known price the project is not bankable — and it avoids tying up capital, land and permits. In exchange you pay for twenty years for a supply that, under self-production, would be nearly free once depreciated. Comparing the two models is exactly what the Economics tab is for.

**"Pay only absorbed energy" option**: when off, all energy produced is paid for, curtailment included — a conservative assumption. When on, curtailment risk stays with the renewable producer.
