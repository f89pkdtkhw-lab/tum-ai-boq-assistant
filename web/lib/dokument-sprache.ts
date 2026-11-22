// Document text in the reader's language: item short texts, long texts and titles come from the uploaded file,
// usually German. With English selected they are shown in English (and English files in German) through:
//   1. a built-in construction glossary with German compound splitting (offline, instant), then
//   2. the server's model (/api/uebersetzen) when a key is set – results are cached in the browser.
// The original text stays available (title attribute) so nothing is lost; numbers, units and item numbers are untouched.

export type DokSprache = "de" | "en";

// German → English stems. Compounds are split into these (Stahlbetonwand → Stahlbeton + wand → reinforced concrete wall).
const DE_EN: Record<string, string> = {
  abdichtung: "waterproofing", abwasserleitung: "sewage pipe", abschnitt: "section", abtragen: "removal", alle: "all", aller: "all",
  alu: "aluminium", anlage: "system", anschluss: "connection", anstrich: "paint coat", attika: "parapet", abdeckung: "capping",
  aushub: "excavation", ausführung: "execution", außen: "external", austausch: "replacement", bad: "bathroom", bahn: "membrane",
  baugrube: "building pit", baugruben: "building pit", bauteil: "component", bereich: "area", beton: "concrete", betonarbeiten: "concrete work",
  bewehrung: "reinforcement", bitumen: "bitumen", boden: "floor", bodenklasse: "soil class", bodenplatte: "ground slab", büro: "office",
  bürogebäude: "office building", dach: "roof", dacharbeiten: "roofing work", dachflächen: "roof", decke: "slab", dispersion: "dispersion",
  dämmung: "insulation", dusch: "shower", duschrinne: "shower channel", einbau: "installation", einschl: "incl.", erd: "earth",
  erdarbeiten: "earthworks", estrich: "screed", estricharbeiten: "screed work", fenster: "window", fertigteil: "precast element",
  flach: "flat", flachdach: "flat roof", fliesen: "tiles", fliesenarbeiten: "tiling", fundament: "foundation", gebäude: "building",
  gips: "gypsum", graben: "trench", grundierung: "primer", haus: "house", heiz: "heating", herstellen: "construct", holz: "timber",
  im: "in the", inkl: "incl.", innen: "internal", kalk: "lime", kalkgips: "lime-gypsum", keller: "basement", komplett: "complete",
  kunststoff: "uPVC", liefern: "supply", malerarbeiten: "painting work", matten: "mesh", mauerarbeiten: "masonry work", mauerwerk: "masonry",
  mineralisch: "mineral", montieren: "install", nach: "according to", nebenleistungen: "ancillary work", ober: "top", oberboden: "topsoil",
  perimeter: "perimeter", plan: "drawing", putz: "plaster", putzarbeiten: "plastering", rinne: "channel", sanitär: "plumbing",
  schall: "sound", sockel: "plinth", stahl: "steel", stahlbeton: "reinforced concrete", streifen: "strip", stütze: "column", tapezier: "wallpapering",
  tapezierarbeiten: "wallpapering", tief: "underground", tiefgarage: "underground car park", trenn: "partition", tritt: "impact",
  trittschall: "impact sound", und: "and", verfüllung: "backfill", vlies: "fleece", wand: "wall", wärme: "thermal", wärmedämmung: "thermal insulation",
  waschtisch: "washbasin", wc: "WC", zement: "cement", ziegel: "brick", ks: "sand-lime", flg: "leaf", einflg: "single-leaf", zweiflg: "double-leaf",
  liefern_und: "supply and", nach_plan: "as per drawing", mit: "with", ohne: "without", für: "for", aus: "of", auf: "on", von: "of", zu: "to",
  der: "the", die: "the", das: "the", den: "the", dem: "the", ein: "a", eine: "a", einer: "a", lfd: "running", gem: "acc. to", gemäß: "according to",
  schalung: "formwork", bewehrungsstahl: "reinforcing steel", betonstahl: "reinforcing steel", tür: "door", türen: "doors", treppe: "stair",
  geländer: "railing", rohr: "pipe", leitung: "pipe", kabel: "cable", schacht: "shaft", entwässerung: "drainage", gerüst: "scaffolding",
  baustelleneinrichtung: "site setup", stundenlohnarbeiten: "daywork", zulage: "surcharge", bedarfsposition: "provisional item",
  wahlposition: "alternative item", pauschal: "lump sum", stück: "piece", vorhalten: "provide", entsorgen: "dispose of", abbruch: "demolition",
  rückbau: "dismantling", trockenbau: "drywall", gipskarton: "plasterboard", elektro: "electrical", heizung: "heating", lüftung: "ventilation",
  dämm: "insulating", platte: "board", platten: "boards", belag: "covering", anschlüsse: "connections", schutz: "protection", fuge: "joint",
  fugen: "joints", sohle: "base", kies: "gravel", sand: "sand", schotter: "crushed stone", pflaster: "paving", asphalt: "asphalt",
};
// English → German for the reverse direction (whole words only).
const EN_DE: Record<string, string> = Object.fromEntries(Object.entries(DE_EN).filter(([k]) => !k.includes("_")).map(([de, en]) => [en.toLowerCase(), de]));

const STAEMME = Object.keys(DE_EN).filter((k) => !k.includes("_")).sort((a, b) => b.length - a.length);

/** German compound → parts from the glossary (longest first, allowing a linking -s-/-n-), or null. */
function zerlege(wort: string): string[] | null {
  const w = wort.toLowerCase();
  if (DE_EN[w]) return [w];
  for (const s of STAEMME) {
    if (s.length < 3 || !w.startsWith(s)) continue;
    for (const fuge of ["", "s", "n", "es"]) {
      if (!w.slice(s.length).startsWith(fuge)) continue;
      const rest = w.slice(s.length + fuge.length);
      if (!rest) return [s];
      const teile = zerlege(rest);
      if (teile) return [s, ...teile];
    }
  }
  return null;
}

const DE_HINWEIS = /[äöüß]|\b(und|der|die|das|mit|nach|inkl|herstellen|liefern|arbeiten|im|für)\b|(arbeiten|ung|wand|decke|platte)\b/i;
const EN_HINWEIS = /\b(the|and|with|of|work|supply|install|wall|slab|incl)\b/i;
export function spracheVon(text: string): DokSprache {
  return DE_HINWEIS.test(text) || !EN_HINWEIS.test(text) ? "de" : "en";
}

/** Offline translation from the glossary. Unknown words stay as they are (better than guessing). */
export function glossar(text: string, ziel: DokSprache): string {
  if (!text) return text;
  if (ziel === "en") {
    return text.replace(/[A-Za-zÄÖÜäöüß]+/g, (wort) => {
      const teile = zerlege(wort);
      if (!teile) return wort;
      const en = teile.map((t) => DE_EN[t]).join(" ");
      return wort[0] === wort[0].toUpperCase() && wort.length > 2 ? en[0].toUpperCase() + en.slice(1) : en;
    }).replace(/\s{2,}/g, " ");
  }
  let out = text;
  for (const [en, de] of Object.entries(EN_DE).sort((a, b) => b[0].length - a[0].length)) {
    out = out.replace(new RegExp(`\\b${en.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "gi"), (m) => (m[0] === m[0].toUpperCase() ? de[0].toUpperCase() + de.slice(1) : de));
  }
  return out;
}

// ---- cache + server model ----
const SCHLUESSEL = "lv-uebersetzung-v1";
let cache: Record<string, string> | null = null;
const offen = new Set<string>();
const unterwegs = new Set<string>();
const hoerer = new Set<() => void>();
let timer: ReturnType<typeof setTimeout> | null = null;
let laeuft = false;

function ladeCache(): Record<string, string> {
  if (cache) return cache;
  try { cache = JSON.parse(window.localStorage.getItem(SCHLUESSEL) ?? "{}"); } catch { cache = {}; }
  return cache!;
}
const key = (ziel: DokSprache, text: string) => `${ziel}|${text}`;

/** Asks the server for model translations of the queued texts (batched); without a model key it answers null and the glossary stays. */
function abholen(ziel: DokSprache) {
  // One in-flight batch at a time: a remount during a long Grok Bot wait must not start a second job.
  if (timer || laeuft) return;
  timer = setTimeout(async () => {
    timer = null;
    const texte = [...offen]
      .filter((k) => k.startsWith(`${ziel}|`) && !unterwegs.has(k))
      .map((k) => k.slice(3))
      .filter((t) => !ladeCache()[key(ziel, t)])
      .slice(0, 60);
    texte.forEach((t) => { const k = key(ziel, t); offen.delete(k); unterwegs.add(k); });
    if (!texte.length) return;
    laeuft = true;
    try {
      // No short AbortController: /api/uebersetzen may wait the full grokbot timeout (~15 min).
      const r = await fetch("/backend/api/uebersetzen", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texte, ziel }) });
      if (r.ok) {
        const { uebersetzungen } = await r.json() as { uebersetzungen: (string | null)[] };
        const c = ladeCache();
        let neu = false;
        texte.forEach((t, i) => { if (uebersetzungen[i]) { c[key(ziel, t)] = uebersetzungen[i]!; neu = true; } });
        if (neu) { try { window.localStorage.setItem(SCHLUESSEL, JSON.stringify(c)); } catch { /* memory only */ } hoerer.forEach((h) => h()); }
      }
    } catch { /* offline: glossary only */ }
    finally {
      texte.forEach((t) => unterwegs.delete(key(ziel, t)));
      laeuft = false;
    }
    if ([...offen].some((k) => !unterwegs.has(k) && !ladeCache()[k])) abholen(ziel);
  }, 250);
}

export function abonniere(h: () => void) { hoerer.add(h); return () => { hoerer.delete(h); }; }

/** Text in the target language: cached model translation, else glossary (and the model is asked in the background). */
export function inSprache(text: string | null | undefined, ziel: DokSprache): string {
  if (!text) return text ?? "";
  if (spracheVon(text) === ziel) return text;
  if (typeof window === "undefined") return glossar(text, ziel);
  const c = ladeCache()[key(ziel, text)];
  if (c) return c;
  offen.add(key(ziel, text));
  abholen(ziel);
  return glossar(text, ziel);
}
