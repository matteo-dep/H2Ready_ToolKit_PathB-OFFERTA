### 🧭 How the tool works

The tool answers the same question from three directions. The mode is chosen at the top of the sidebar and determines only **where you start from**: the calculation engine, the hourly simulation and the regulatory checks are identical in all three cases.

| Mode | You enter | You get |
|---|---|---|
| **From hydrogen demand** | Production target (ton/year) and desired plant allocation | Required capacity, **surfaces to be found**, hydrogen cost |
| **From available surfaces** | Hectares and square metres actually available | Producible hydrogen, feasible plants, hydrogen cost |
| **Coverage check** | Both | Share of demand covered locally and missing surface |

Numerically the three modes are the same equation solved for different unknowns: the hourly simulation always runs on a profile normalised to 1 MW of installed renewable capacity, and results are scaled afterwards. This guarantees that starting from 20 MW of surfaces, or asking for the target those 20 MW produce, yields exactly the same plant — a property verified with zero deviation.

---

#### Step 1 — From surface to installable power

Surfaces are split into three families, because they differ in power density, yield and — above all — connection cost.

| Type | Formula | Default density | Usable share |
|---|---|---|---|
| Ground / brownfield | ha × share × MWp/ha | 0.70 MWp/ha | 90% |
| Rooftops | m² × share × kWp/m² / 1000 | 0.18 kWp/m² | 50% |
| Industrial sheds | m² × share × kWp/m² / 1000 | 0.18 kWp/m² | 70% |

The **usable share** discounts what the gross surface cannot host: on the ground, access roads, substations and setbacks; on rooftops, north-facing pitches, chimneys, dormers and structural limits; on sheds, skylights, extraction turrets, walkways and crane runways.

The **relative yield** corrects the hourly profile against an optimised ground array: 96% for pitched roofs (orientation is not always optimal) and 93% for sheds (flat roofs with flush or low-tilt modules, more sensitive to soiling and temperature).

**Wind** is not derived from a surface but from the number of turbines the site can host.

In *demand* mode the same table is used in reverse: from the required capacity the tool derives the surfaces to be found, category by category.

---

#### Step 2 — Electrical connection: where the real difference lies

This is where the three families diverge by orders of magnitude. For each type you choose the **link to the electrolyser**:

- **Dedicated direct line** — cable CAPEX proportional to distance, no wheeling charges. This is the configuration that allows the BESS to be considered "behind the same connection point" for RED III purposes.
- **Public grid (wheeling)** — only the connection to the existing point is paid, but the energy transported bears grid charges (€/MWh) for the whole plant life.

Cost models applied:

- *Utility-scale ground*: above 6 MW, **HV** connection (€730,000 + €300,000/km); below, **MV** (€8,000 + €155,000/km). These are the Tool 2.6 figures.
- *Sheds*: cost per connection point (MV user substation, default €45,000) times the number of sites, plus MV cable (€155,000/km) if a direct line is chosen.
- *Rooftops*: lower cost per connection point (default €9,000) but multiplied by a typically high number of points; the LV/MV cable (€90,000/km) makes a direct line almost always uneconomic, hence the public-grid default.

The result is that 1 MWp spread over ten rooftops costs far more in connection than 1 MWp on a single brownfield next to the electrolyser, and the "Connections by site type" table makes this explicit.

---

#### Step 3 — Hourly simulation (8760 h)

RES profiles come from the datasets in the repository (weighted averages of representative Northern or Southern Italian areas). Dispatch follows a merit order: RES directly to the electrolyser, surplus to the battery (90% round-trip), deficit covered by the battery and — only if enabled — by the grid. Energy with nowhere to go is **curtailment**.


The hourly balance always closes: generated energy = energy to the electrolyser + curtailment + battery round-trip losses + change in state of charge. Storage losses (10% over the full cycle) are why, with BESS active, the first two items sum to less than generation.
---

#### Step 4 — Electrolyser sizing

Size is expressed as a percentage of installed RES power. In **automatic** mode the tool scans 10%–120% and picks the minimum-LCOH size: a small electrolyser runs many hours but wastes energy, a large one captures peaks but stays idle. The sensitivity chart shows the trade-off, with the green line marking the current choice.

---

#### Step 5 — RED III / RFNBO compliance

The module checks the conditions of Delegated Regulation (EU) 2023/1184 and computes the **certifiable hydrogen share**:

1. **Additionality** — new RES plants, commissioned no more than 36 months before the electrolyser.
2. **No public support** — no subsidies or State aid on the RES plants. Choosing *self-generation* with subsidised plants voids this condition.
3. **Geographical correlation** — plants and electrolyser in the same bidding zone.
4. **Temporal correlation** — monthly until 2029, **hourly from 2030**. With dedicated plants only, the condition holds by construction. If grid integration is enabled:
   - under the monthly scenario, withdrawals can be matched with the same month's RES surplus (up to the available curtailment);
   - under the hourly scenario, withdrawals cannot be matched and produce **non-compliant** hydrogen, valued at the reduced price;
   - the exception is a grid certified above 90% RES or below 18 gCO₂eq/MJ, which makes the whole withdrawal compliant.
5. **Storage** — the BESS is admissible if placed behind the same connection point as the plants. If part of the generation is wheeled through the public grid the condition is not met, but the whole output is not voided: the tool carves out only the **energy routed through the battery**, which fails temporal correlation, and leaves the rest certifiable.

If any of the first three conditions fails, the entire output becomes non-certifiable: that is why the panel shows the RFNBO share separately from total production.

---

#### Step 6 — Economics

**CAPEX**: electrolyser, BESS, H2 storage, compression (annualised and capitalised via CRF), electrical connections by site type and — under *self-generation* — the RES plants, with distinct unit costs for ground, rooftops and sheds.

**OPEX**: RES energy bought under CfD in the PPA/CfD model, wheeling charges on grid-transported energy, cost of grid withdrawals, plus 3% of CAPEX for O&M.

`LCOH = (OPEX + CAPEX × CRF) / kg H2`, with 5% WACC and a 20-year lifetime. Revenues distinguish RFNBO hydrogen from non-compliant hydrogen, applying the two prices set in the Market panel.

**"Pay only absorbed energy" option**: if off, all generated energy is paid for including curtailment — a conservative assumption consistent with Tool 2.6. If on, curtailment risk stays with the RES producer.
