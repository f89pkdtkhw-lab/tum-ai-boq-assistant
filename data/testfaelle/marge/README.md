# Margin page test file

`competitor_bids_synthetic.xlsx` is the synthetic demo and test file for the Margin page (`web/app/marge`, `web/components/marge`, logic in `web/lib/marge.ts`). It is **not partner data**: every name and number is made up.

## Use

- In the app: menu ☰ → More → **Margin** → "Choose Excel file" → load this file. The page reads it in the browser; no backend needed. Tick the competitors to compare against, optionally exclude IQR outliers, set the project duration (annual operating costs are pro-rated by months/12) and drag the margin slider. Our price never goes below our own costs.
- Unit test: `web/lib/marge.test.mjs` reads this file and checks the outlier, low confidence and skew cases (`cd web && npm test`).

## Layout

One sheet, one row per bid. 10 competitors over 6 items, plus one "Our company" row per item.

| Column | Meaning |
| --- | --- |
| Provider | Bidder name. `Our company` marks our own row for that item. |
| Item | BoQ item the bid is for (Excavation, Concrete, Reinforcement, Formwork, Masonry, Screed). |
| Unit | Unit of the item (m3, t, m2). |
| Quantity | Item quantity. |
| Unit price | The bidder's unit price (EP); empty on our own rows. |
| Current offer | Line total = Quantity × Unit price; the page sums it per provider. |
| Direct cost | Direct cost per unit. Our rows: our direct cost. Competitor rows: only where the split is disclosed. |
| Operating cost % | Operating costs as % of direct cost. Our rows: our real operating costs (the price floor). |
| Profit margin % | Margin as % of direct cost. Our rows: our minimum margin (2 %). |

## Deliberate cases

- **Outlier:** every `Fuchs Construction` row (about 75–81 % markup, others 15–29 %). The IQR step removes it per item.
- **Cost split given:** `Alpha Bau GmbH`, `Bergmann Hochbau`, `Gruber Bau` (Direct cost, Operating cost %, Profit margin % filled).
- **No cost split:** all other competitors (Cramer & Sons, Delta Tiefbau, Ertl Bau KG, Fuchs Construction, Huber & Partner, Iller Bauunternehmen, Jansen Hoch- und Tiefbau); their markup is back-calculated from Unit price and our Direct cost.
- **Low confidence:** `Screed 50 mm` has only 4 bids (under 5 data points, no IQR).
- **Skew warning:** `Masonry 24 cm`, where mean and median differ by more than 3 points after cleaning.
