"""#187: quantity lines and markers as AVA printouts produce them (synthetic words, no partner data)."""
from app.lv import pdf as P

WIDTH = 595.0


def words(*items):
    """``(text, x0)`` pairs on one line; x1 = x0 + 5 per character."""
    return [P._Word(text=t, x0=x, x1=x + 5 * len(t), top=100.0, bottom=108.0, font="Arial", size=9.0) for t, x in items]


def parse(*items):
    return P._quantity_line(words(*items), WIDTH)


def test_lone_dots_between_price_fields_are_ignored():
    q = parse(("1,000", 300), ("PSCH", 330), (".", 365), ("........................", 380), (".", 470), ("........................", 480))
    assert q["quantity"] == 1.0 and q["unit"] == "PSCH" and not q["nep"]


def test_digits_split_by_letter_spacing_are_joined():
    q = parse(("3", 300), ("5,000", 306), ("St", 335), (".", 350), ("........................", 380), (".........................", 480))
    assert q["quantity"] == 35.0 and q["unit"] == "St"


def test_split_digits_far_apart_stay_separate():
    assert parse(("3", 100), ("5,000", 300), ("St", 335), ("........................", 380)) is None


def test_only_unit_price_note_marks_the_item_as_bedarf():
    q = parse(("3.300,000", 300), ("m", 350), (".", 360), ("........................", 380),
              ("N", 470), ("ur", 476), ("Einh.", 490), ("-", 515), ("Pr", 520), (".", 532))
    assert q["quantity"] == 3300.0 and q["unit"] == "m" and q["nep"]


def test_unit_glued_to_quantity_and_ep_gp_placeholders():
    q = parse(("2St", 335), ("EP..........................", 380), ("GP............................", 480))
    assert q["quantity"] == 2.0 and q["unit"] == "St"


def test_marker_on_oz_line_becomes_type_and_next_line_the_title():
    def line(text, x, top, page=1):
        ws = [P._Word(text=t, x0=x + 40 * i, x1=x + 40 * i + 30, top=top, bottom=top + 8, font="Arial", size=9.0)
              for i, t in enumerate(text.split())]
        return P._Line(page=page, words=ws, page_width=WIDTH, page_height=842.0)
    items = [line("14.1.20. Untergrund reinigen", 54, 100),
             line("1,000 m2 ........................ ........................", 300, 112),
             line("14.1.30. *** Bedarfsposition ohne GB", 54, 130),
             line("Risse im Estrich schließen", 125, 142),
             line("Risse kraftschlüssig schließen.", 125, 154),
             line("1,000 m . ........................ N ur Einh. - Pr .", 300, 170)]
    events = P._segment(items, 54.0)
    entries = list({id(e): e for _, _, e in events if e is not None and e.kind == "oz"}.values())
    P._classify(entries, [])
    lv = P._build_lv("t.pdf", entries, [items], [])
    bedarf = next(p for p in lv.positionen if p.oz == "14.1.30.")
    assert bedarf.typ == "bedarf" and bedarf.kurztext == "Risse im Estrich schließen"
    assert bedarf.menge == 1.0 and bedarf.einheit == "m" and "kraftschlüssig" in bedarf.langtext


def test_quantity_on_the_oz_line_keeps_the_text_below_as_short_text():
    def line(text, x, top):
        step = 85 if x == 61 else 45  # OZ lines: quantity and prices spread to the right price columns
        ws = [P._Word(text=t, x0=x + step * i, x1=x + step * i + 35, top=top, bottom=top + 8, font="Arial", size=9.0)
              for i, t in enumerate(text.split())]
        return P._Line(page=1, words=ws, page_width=WIDTH, page_height=842.0)
    items = [line("2.1.10 3.200,000 m 1,50 4.800,00", 61, 100), line("Wiederherstellen Wiesenwege", 158, 112),
             line("2.1.20 3.600,000 m² 0,05 180,00", 61, 130), line("Geotextil liefern und verlegen", 158, 142)]
    events = P._segment(items, 61.0)
    entries = list({id(e): e for _, _, e in events if e is not None and e.kind == "oz"}.values())
    P._classify(entries, [])
    lv = P._build_lv("t.pdf", entries, [items], [])
    assert [(p.oz, p.kurztext, p.menge) for p in lv.positionen] == [
        ("2.1.10", "Wiederherstellen Wiesenwege", 3200.0), ("2.1.20", "Geotextil liefern und verlegen", 3600.0)]
