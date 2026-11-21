"""#196: answer language of the model, taken from the UI language setting.

The UI writes the cookie ``sprache=de|en`` whenever its language setting changes (``web/lib/einstellungen.tsx``);
an ``X-Sprache`` header wins over the cookie. ``Antwortsprache`` (ASGI middleware in ``main.py``) stores it per
request in a context variable, and ``llm.complete()`` / ``llm.research()`` append ``HINWEIS_DE`` to the system
prompt when it is ``de``. English or no setting leaves every prompt byte-identical.

Threads do not inherit context variables: code that hands model calls to a thread or pool passes
``contextvars.copy_context().run`` (see ``analyse_job.py`` and the review pools). Calls that must keep the source
text (translation, Excel import) run inside ``ohne_hinweis()``.
"""
from contextlib import contextmanager
from contextvars import ContextVar, Token
from http.cookies import CookieError, SimpleCookie

SPRACHEN = ("de", "en")
HINWEIS_DE = (
    "Answer language: German (Deutsch). Write every human-readable text value (titles, reasons, suggestions, "
    "summaries, explanations, descriptions) in German. Keep JSON keys, enum values, IDs, item numbers (OZ), rule "
    "IDs, units, numbers, URLs, product names and standard names (DIN, EN, VOB) exactly unchanged."
)

_SPRACHE: ContextVar[str | None] = ContextVar("antwortsprache", default=None)


def normalisiere(wert: str | None) -> str | None:
    """``de``/``en`` from a cookie or header value such as ``de-DE``; anything else is None."""
    kurz = (wert or "").strip().lower()[:2]
    return kurz if kurz in SPRACHEN else None


def setze(wert: str | None) -> Token:
    return _SPRACHE.set(normalisiere(wert))


def zuruecksetzen(token: Token) -> None:
    _SPRACHE.reset(token)


def aktuell() -> str | None:
    return _SPRACHE.get()


@contextmanager
def ohne_hinweis():
    """Model calls in this block get no language instruction (they must keep or choose their own language)."""
    token = _SPRACHE.set(None)
    try:
        yield
    finally:
        _SPRACHE.reset(token)


def mit_hinweis(system: str) -> str:
    if aktuell() != "de":
        return system
    return f"{system}\n\n{HINWEIS_DE}" if system else HINWEIS_DE


def aus_anfrage(headers: list[tuple[bytes, bytes]]) -> str | None:
    """Language of an ASGI request: ``X-Sprache`` header, else the ``sprache`` cookie."""
    cookie = None
    for name, wert in headers:
        name = name.lower()
        if name == b"x-sprache":
            gefunden = normalisiere(wert.decode("latin-1"))
            if gefunden:
                return gefunden
        elif name == b"cookie":
            try:
                morsel = SimpleCookie(wert.decode("latin-1")).get("sprache")
            except CookieError:
                morsel = None
            if morsel is not None:
                cookie = normalisiere(morsel.value) or cookie
    return cookie


class Antwortsprache:
    """Pure ASGI middleware: sets the answer language for the duration of one HTTP request."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        token = setze(aus_anfrage(scope.get("headers") or []))
        try:
            await self.app(scope, receive, send)
        finally:
            zuruecksetzen(token)
