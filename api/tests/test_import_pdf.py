"""Placeholder contract; add real import acceptance tests in the format issue."""
import pytest
from app.lv.importer import importiere


def test_pdf_placeholder_is_explicit_instead_of_fabricating_positions():
    with pytest.raises(NotImplementedError, match="not implemented yet"):
        importiere("beispiel.pdf", b"not-a-real-file")
