# Domain knowledge: LV, GAEB, estimation

Quick reference for people and agents. Uncertain information is marked; when in doubt, check the dataset instead of guessing.

## Friday team notes (conversations with practitioners)

Paraphrased from photographs of two note sheets:

- **Public tenders** are the main source of LVs; platforms such as cosuno.de collect tenders and could supply database input.
- **Plausibility checking matters greatly.** Many errors originate with the client or planner preparing the LV.
- **Variable resource estimation using indexed prices:** material prices fluctuate; use price indices, e.g. from Germany's Federal Statistical Office.
- **Handwriting OCR** for documents such as orders or measurement records.
- **Data flow:** architect creates the GAEB file → contractor receives it. Often accompanied by a PDF specification with **short text** and **long text** for each item.
- **Database X** with machine usage (equipment list) → **quantity takeoff** → **person-hour estimate**.
- **Concrete example:** approximately **€150 per m³ of concrete** (material). Labor: **average wage €25–30/h + about 80% labor overhead + general overhead (X%)**.
- **Adaptive learning** from actual data: learn from completed and billed projects.
- **Construction estimating PDF** (textbook/guide) as a knowledge source.

For detailed structured notes with **12% general overhead** as a guideline, see [notes context](quellen/Challenge_A_Notizen_Kontext.pdf). Deutsche Bahn tenders are another potential source alongside cosuno. One goal from the notes: automatically group similar items (e.g. concrete grades) and focus on the approximately 100 most important items instead of all 9,000 rows.

## 20 capabilities of an estimation AI (summary)

Full source: [AI skills](quellen/Skills%20der%20KI.pdf). Bold entries are relevant to our prototype.

- **Understand documents:** **analyze LVs (item types: provisional, alternative, optional)** · **review contract terms** (VOB/B, supplementary technical conditions, penalties, securities, deadlines) · **turn contradictions and gaps into clarification questions** · **check quantity plausibility**
- **Estimate:** productivity values · labor (average wage + labor overhead) · material (price adjustment, waste) · equipment (BGL) · subcontractors · site overhead · general overhead, risk and profit markups
- **Risk and strategy:** **probability × impact** · **risk allowance in euros instead of a blanket percentage** · construction duration · **Nachtrag potential and the bidder's own exposure** · bid strategy (conservative, market-based, aggressive)
- **Output and quality:** prepare bids · **plausibility checks in €/m², €/m³ and arithmetic checks** · learn from post-project cost analysis
- **Guardrails:** always label estimates; never issue a price without the estimator's approval.

## Terminology

| Term | Meaning |
| --- | --- |
| LV (Leistungsverzeichnis) | Bill of quantities (BoQ): list of tendered work, divided into lots, sections and items |
| GAEB (Gemeinsamer Ausschuss Elektronik im Bauwesen) | German construction electronic data exchange committee; its formats exchange bills of quantities and bids |
| OZ (Ordnungszahl) | Original item number, e.g. `01.02.0030`; its structure is specified in the LV header (e.g. `11PPPPI`) |
| VOB (Vergabe- und Vertragsordnung für Bauleistungen) | German procurement and contract rules for construction work; VOB/A covers procurement and VOB/B contract terms |
| Kurztext / Langtext | Short text = heading (roughly 70 characters maximum); long text = complete, legally relevant work specification |
| Menge, Einheit (ME) | Quantity and unit, e.g. `125,500 m³`; common units: m, m², m³, St (pieces), kg, t, h, psch (lump sum) |
| EP / GP | Einheitspreis / Gesamtpreis: unit price / total item price; **GP = quantity × EP**, rounded to two decimals |
| Normalposition (NP) | Standard item, executed and billed normally |
| Bedarfs-/Eventualposition (EP/BedP) | Provisional item, executed only if needed, often excluded from the total GP; a common source of disputes and speculation |
| Alternativ-/Wahlposition | Alternative or optional item replacing a base item; the client chooses |
| Zulageposition | Surcharge item attached to another item (e.g. exposed concrete surcharge) |
| Pauschalposition (psch) | Lump-sum item, quantity 1; the bidder bears the risk |
| Nachtrag | Claim for additional payment for changed or additional work (VOB/B § 2 paragraphs 5, 6, 8), often caused by incomplete or unclear LVs |
| Bieterfrage | Bidder clarification question to the client during tendering; the cheapest way to resolve uncertainty |
| DIN 276 | Cost groups (KG 300 building structure, KG 400 technical installations, etc.) |
| STLB-Bau / StLB | Standardized work specifications; deviations are a review signal |
| DIN 18195 → DIN 18533 | Waterproofing standard DIN 18195 was replaced in 2017 by DIN 18531–18535; an LV still citing DIN 18195-4 is outdated |
| VOB/A § 7 | Work must be described **clearly and exhaustively**; unusual risks must not be imposed on the bidder |

## GAEB formats

GAEB DA XML (3.x) is the exchange standard. Data exchange phases (DA):

| Extension | Phase | Contents |
| --- | --- | --- |
| `.x81` | LV transfer | Work specification |
| `.x83` | Invitation to bid | LV with quantities, **without prices**; typical estimator input |
| `.x84` | Bid submission | LV with bidder prices |
| `.x85` | Alternative bid | |
| `.x86` | Contract award | |
| `.d83` / `.p83` | GAEB 90 / 2000 | Older fixed-column flat files (`.d8x`) or tagged format (`.p8x`) |

Simplified XML structure (respect namespaces): `GAEB > Award > BoQ > BoQBody > BoQCtgy (recursive sections) > BoQBody > Itemlist > Item`, with `Qty`, `QU` (unit), `UP` (EP), `IT` (GP), `Description > CompleteText > OutlineText` (short text) and `DetailTxt` (long text). In Python, a custom `xml.etree`/`lxml` parser is often more robust than libraries; long texts often contain embedded HTML-like markup.

## Error and risk catalogue (starting point for rules)

**Formal / arithmetic (fixed rules, no LLM required)**

- GP ≠ quantity × EP; section total ≠ sum of items
- Duplicate OZ, gaps or jumps in numbering, incorrect OZ mask
- Zero or missing quantity on a standard item; missing unit; unusual unit for the text (concrete in m², area in pieces)
- Quantity outliers compared with related items (e.g. formwork vs. concrete volume)
- Typos in short text; short and long texts disagree
- Empty long texts, placeholders such as “xxx”, “see drawing”, “as specified by client”

**Content (LLM + heuristics)**

- Vague specifications: “as required”, “approximately”, “provided by client”, “as agreed”, “including all ancillary work”, “at contractor's discretion”
- References to unattached drawings, surveys (especially ground conditions) or standards
- Contradictions between items (concrete grade C25/30 vs. C30/37, different insulation thicknesses)
- **Missing items** by trade: concrete without reinforcement, formwork or curing; earthworks without disposal; demolition without hazardous-material investigation
- Provisional items with large quantities, broad lump sums, hourly work
- Risk shifted to the bidder: missing ground classes/homogeneous zones, undefined dewatering, disposal “as encountered”

**Nachtrag potential** from the bidder's perspective: incomplete or ambiguous items, quantities too low (speculation on increases exceeding 10% under VOB/B § 2 paragraph 3), missing ancillary work, unspecified difficulties.

## Estimation (optional EP suggestions)

```text
EP = labor + material + equipment + subcontractors, plus markups
Labor = productivity [h/unit] × average wage
Average wage ≈ €25–30/h (+ ~80% labor overhead → estimating rate ~€45–55/h)
Markups = site overhead + general overhead (AGK, often 8–12%) + risk and profit (often 3–6%)
Concrete example: material ~€150/m³ + placement (productivity × labor) + equipment (pump) + markups
```

The general-overhead and risk/profit percentages are typical orders of magnitude, not evidenced values from our dataset. Expose them as adjustable product parameters (what-if).
