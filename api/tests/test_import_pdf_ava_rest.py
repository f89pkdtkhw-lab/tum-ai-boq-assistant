"""#192: AVA printouts with cut-off OZ prefix, Wahl/Grundpositionen, split units and titles repeated
at the top of each page (synthetic words, no partner data)."""
from app.lv import pdf as P

WIDTH = 595.0
HEIGHT = 842.0


def line(text, x, top, page=1, step=45):
    ws = [P._Word(text=t, x0=x + step * i, x1=x + step * i + 30, top=top, bottom=top + 8, font="Arial", size=9.0)
          for i, t in enumerate(text.split())]
    return P._Line(page=page, words=ws, page_width=WIDTH, page_height=HEIGHT)


def qty(text, top, page=1):
    return line(text, 300, top, page, step=60)


def build(items, column):
    events = P._segment(items, column)
    entries = list({id(e): e for _, _, e in events if e is not None and e.kind == "oz"}.values())
    P._classify(entries, [])
    return P._build_lv("t.pdf", entries, [items], [])


def test_leading_dot_oz_is_recognized_with_grund_and_wahlposition():
    items = [line(".1 *** Grundposition 1 .0", 54, 300),
             line("Rohrregister in Modulbauweise", 125, 312),
             qty("496,000 m² . ........................ . ........................", 330),
             line(".2 *** Wahlposition 1.1 zu 1.0", 54, 350),
             line("Handverlegtes Rohr", 125, 362),
             qty("3.300,000 m . ........................ N ur Einh. - Pr .", 380),
             line(".10 Anbindeleitung", 54, 400),
             qty("510,000 m . ........................ . ........................", 412),
             line(".11 *** Bedarfsposition ohne GB", 54, 430),
             line("Monteurstunden", 125, 442),
             qty("1,000 h . ........................ N ur Einh. - Pr .", 454)]
    assert P._oz_column(items) == 54.0
    lv = build(items, 54.0)
    assert [(p.oz, p.typ, p.kurztext, p.menge, p.einheit) for p in lv.positionen] == [
        ("1", "normal", "Rohrregister in Modulbauweise", 496.0, "m²"),
        ("2", "alternativ", "Handverlegtes Rohr", 3300.0, "m"),
        ("10", "normal", "Anbindeleitung", 510.0, "m"),
        ("11", "bedarf", "Monteurstunden", 1.0, "h")]


def test_letter_spaced_unit_is_joined():
    ws = [P._Word(text=t, x0=x, x1=x + 5 * len(t), top=100.0, bottom=108.0, font="Arial", size=9.0)
          for t, x in (("5.000,000", 302), ("m2", 350), ("W", 362), ("o", 368),
                       (".........................", 380), (".........................", 480))]
    q = P._quantity_line(ws, WIDTH)
    assert q["quantity"] == 5000.0 and q["unit"] == "m2Wo"


def test_unit_with_digit_and_suffix_on_bare_quantity_line():
    items = [line("3.2.11 Grabenverbaugerät vorhalten", 44, 300),
             line("Positionsmenge = Produkt aus", 121, 312),
             line("26.500,000 m2d", 121, 324),
             line("3.2.12 Stirnverbau herstellen", 44, 340),
             line("140,000 m2", 121, 352)]
    lv = build(items, 44.0)
    assert [(p.oz, p.menge, p.einheit) for p in lv.positionen] == [("3.2.11", 26500.0, "m2d"), ("3.2.12", 140.0, "m2")]


def test_ep_gp_labels_before_dotted_fields():
    ws = [P._Word(text=t, x0=x, x1=x + 5 * len(t), top=100.0, bottom=108.0, font="Arial", size=9.0)
          for t, x in (("200St", 325), ("EP..........", 377), ("GP", 465), ("..............", 480))]
    q = P._quantity_line(ws, WIDTH)
    assert q["quantity"] == 200.0 and q["unit"] == "St"


def test_title_repeated_on_next_page_keeps_quantity_with_position():
    items = [line("03.02 Bereich Luft", 65, 200),
             line("03.02.1 Verdichtereinheit", 65, 300),
             line("Beschreibung der Einheit", 132, 312),
             line("03.02 Bereich Luft", 65, 150, page=2),
             line("weitere Beschreibung", 132, 200, page=2),
             qty("2St EP.......................... GP ............................", 220, page=2),
             line("03.02.2 Luftfiltereinheit", 65, 300, page=2),
             qty("1St EP.......................... GP ............................", 320, page=2)]
    lv = build(items, 65.0)
    assert [(p.oz, p.menge, p.einheit, p.titel_pfad) for p in lv.positionen] == [
        ("03.02.1", 2.0, "St", ["03.02 Bereich Luft"]), ("03.02.2", 1.0, "St", ["03.02 Bereich Luft"])]


def test_unpriced_numbered_remarks_in_other_format_are_not_positions():
    items = [line("2.3.1 Gewinn", 65, 100),
             line("01.01 Allgemeines", 65, 300),
             line("01.01.1 Baustelleneinrichtung", 65, 320),
             qty("1psch EP.......................... GP ............................", 340),
             line("01.01.2 Fließbild", 65, 360)]
    lv = build(items, 65.0)
    assert [p.oz for p in lv.positionen] == ["01.01.1", "01.01.2"]
