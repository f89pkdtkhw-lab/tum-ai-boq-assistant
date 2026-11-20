"""Synthetic PDF fixtures for the PDF import tests.

Everything here is invented; no real or confidential BoQ content. The builder writes plain PDF 1.4
by hand (standard Helvetica fonts, grayscale images, Bézier strokes), so the tests need no PDF
writer dependency. Coordinates are given like pdfplumber reports them: ``top`` from the top edge.
"""
import zlib

WIDTH, HEIGHT = 595.0, 842.0

# Where the drawn textless regions land, so tests can check page and bounding box.
SKETCH_BBOX = (135.0, 350.0, 335.0, 410.0)       # embedded image inside position 1...2, page 1
HANDWRITING_BBOX = (140.0, 640.0, 400.0, 700.0)   # vector strokes inside position 2...1, page 1
LOGO_BBOX = (40.0, 20.0, 100.0, 50.0)             # repeated header logo, must be skipped


def _escape(text: str) -> bytes:
    return text.encode("cp1252").replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _gray_pattern(width: int, height: int) -> bytes:
    """A scribble-like grayscale raster: dark diagonal strokes on white."""
    rows = []
    for y in range(height):
        rows.append(bytes(0 if (x + 2 * y) % 17 < 3 or (3 * x - y) % 23 < 2 else 255 for x in range(width)))
    return b"".join(rows)


class Page:
    def __init__(self):
        self.ops: list[bytes] = []
        self.images: dict[str, tuple[int, int, bytes]] = {}

    def text(self, x: float, top: float, text: str, bold: bool = False, size: float = 10):
        baseline = HEIGHT - top - 0.793 * size  # pdfminer: top = page height - baseline - (size + descent)
        font = b"/F2" if bold else b"/F1"
        self.ops.append(b"BT %s %.2f Tf %.2f %.2f Td (%s) Tj ET" % (font, size, x, baseline, _escape(text)))

    def image(self, bbox, name: str, pixels=(80, 24)):
        x0, top, x1, bottom = bbox
        width, height = pixels
        self.images[name] = (width, height, _gray_pattern(width, height))
        self.ops.append(b"q %.2f 0 0 %.2f %.2f %.2f cm /%s Do Q" % (x1 - x0, bottom - top, x0, HEIGHT - bottom,
                                                                      name.encode()))

    def handwriting(self, bbox):
        """Three wavy Bézier strokes filling ``bbox``, like digital ink saved as vector paths."""
        x0, top, x1, bottom = bbox
        step = (x1 - x0) / 4
        for row in range(3):
            y = HEIGHT - (top + 10 + row * (bottom - top - 20) / 2)
            path = [b"%.2f %.2f m" % (x0, y)]
            for i in range(4):
                a = x0 + i * step
                path.append(b"%.2f %.2f %.2f %.2f %.2f %.2f c" % (a + step / 3, y + 10, a + 2 * step / 3, y - 10,
                                                                 a + step, y))
            self.ops.append(b"q 1.2 w " + b" ".join(path) + b" S Q")


def build(pages: list[Page]) -> bytes:
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")
    pages_ref = add(b"")
    regular = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    bold = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    kids = []
    for page in pages:
        xobjects = []
        for name, (width, height, raw) in page.images.items():
            data = zlib.compress(raw)
            ref = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray "
                      b"/BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n%s\nendstream"
                      % (width, height, len(data), data))
            xobjects.append(b"/%s %d 0 R" % (name.encode(), ref))
        content = b"\n".join(page.ops)
        content_ref = add(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content))
        resources = b"<< /Font << /F1 %d 0 R /F2 %d 0 R >> /XObject << %s >> >>" % (regular, bold, b" ".join(xobjects))
        kids.append(add(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.0f %.0f] /Resources %s /Contents %d 0 R >>"
                        % (pages_ref, WIDTH, HEIGHT, resources, content_ref)))
    objects[catalog - 1] = b"<< /Type /Catalog /Pages %d 0 R >>" % pages_ref
    objects[pages_ref - 1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, catalog, xref)
    return bytes(out)


def _header(page: Page, number: int, carry_over: bool):
    page.image(LOGO_BBOX, "Logo", pixels=(30, 15))
    page.text(128, 30, "Ingenieurbüro Beispiel -- Beispielweg 1 -- 12345 Beispielstadt", size=9)
    page.text(57, 60, "2026 Beispielprojekt LV 001 Rohbau")  # starts like an OZ; must stay a header
    page.text(520, 75, f"Seite: {number}")
    page.text(57, 98, "Position")
    page.text(135, 98, "Menge/Einheit")
    page.text(432, 98, "EP (EUR)")
    page.text(523, 98, "GP (EUR)")
    if carry_over:
        page.text(457, 122, "Übertrag:")
        page.text(501, 122, "____________")


def _quantity(page: Page, top: float, quantity: str | None, unit: str | None, gp: str = "____________"):
    page.text(135, top, " ".join(v for v in (quantity or "___", unit) if v))
    page.text(431, top, "________")
    page.text(501, top, gp)


def mixed_boq() -> bytes:
    """Two text pages with an embedded sketch and vector handwriting, then one scanned page."""
    first = Page()
    _header(first, 1, carry_over=False)
    first.text(57, 150, "1", bold=True)
    first.text(135, 150, "Erdarbeiten", bold=True)
    first.text(57, 168, "Hinweis", bold=True)
    first.text(135, 168, "Vorbemerkung", bold=True)
    first.text(135, 190, "Boden nach DIN 18300 lösen.")
    first.text(57, 220, "1...1", bold=True)
    first.text(135, 220, "Oberboden abtragen", bold=True)
    first.text(135, 245, "Oberboden abtragen und seitlich lagern.")
    first.text(135, 256, "Dicke bis 20 cm.")
    _quantity(first, 285, "120,000", "m²")
    first.text(57, 310, "1...2", bold=True)
    first.text(135, 310, "Fundament nach Skizze", bold=True)
    first.text(135, 335, "Fundament herstellen wie skizziert:")
    first.image(SKETCH_BBOX, "Sketch")
    first.text(135, 425, "Maße vor Ort prüfen.")
    _quantity(first, 450, "7,000", None)
    first.text(57, 475, "1...3", bold=True)
    first.text(135, 475, "Prüfprotokoll Erdung", bold=True)
    _quantity(first, 500, None, None)
    first.text(57, 530, "Summe 1 Erdarbeiten", bold=True)
    first.text(501, 530, "____________")
    first.text(57, 560, "2", bold=True)
    first.text(135, 560, "Betonarbeiten", bold=True)
    first.text(57, 585, "2...1", bold=True)
    first.text(135, 585, "Sichtbeton Treppe", bold=True)
    first.text(57, 597, "Bedarf", size=8)
    first.text(135, 615, "Zulage für Sichtbeton, Ausführung nach Handskizze:")
    first.handwriting(HANDWRITING_BBOX)
    first.text(135, 720, "Sichtbetonklasse SB 2.")
    first.text(457, 800, "Übertrag:")
    first.text(501, 800, "____________")

    second = Page()
    _header(second, 2, carry_over=True)
    second.text(135, 150, "Ausführung nach Merkblatt.")
    _quantity(second, 180, "10,000", "m²", gp="*NEP*")
    second.text(57, 210, "2...2", bold=True)
    second.text(135, 210, "Stahlbeton Decke", bold=True)
    second.text(135, 235, "Beton C25/30 liefern und einbauen.")
    _quantity(second, 260, "3.350,500", "m³")
    second.text(57, 290, "Summe 2 Betonarbeiten", bold=True)
    second.text(501, 290, "____________")
    second.text(248, 330, "ZUSAMMENFASSUNG", bold=True, size=12)
    second.text(57, 360, "1 Erdarbeiten")
    second.text(501, 360, "____________")
    second.text(57, 380, "2 Betonarbeiten")
    second.text(501, 380, "____________")
    second.text(457, 800, "Übertrag:")
    second.text(501, 800, "____________")

    scanned = Page()
    scanned.image((0.0, 0.0, WIDTH, HEIGHT), "Scan", pixels=(60, 85))
    return build([first, second, scanned])


def scanned_only() -> bytes:
    pages = []
    for _ in range(2):
        page = Page()
        page.image((0.0, 0.0, WIDTH, HEIGHT), "Scan", pixels=(60, 85))
        pages.append(page)
    return build(pages)


def letter_without_positions() -> bytes:
    page = Page()
    page.text(60, 120, "Sehr geehrte Damen und Herren,")
    page.text(60, 140, "anbei erhalten Sie die Unterlagen zur Ausschreibung.")
    return build([page])
