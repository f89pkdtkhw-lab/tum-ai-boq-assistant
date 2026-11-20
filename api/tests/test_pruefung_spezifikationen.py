"""Contract checks for the synthetic specification source package (issue #19).

These tests do not implement ``build_specification_context``. They check that the
synthetic example in ``data/architektur/spezifikationen.json`` follows the rules in
``docs/spezifikationen.md`` and that it fits the existing LV, Note and step API
contracts without changing them.
"""
import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.step_api import CONFLICT_EXAMPLE, Note, Specification
from app.main import app
from app.modelle import LV

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = json.loads((ROOT / "data/architektur/spezifikationen.json").read_text(encoding="utf-8"))
SCENARIOS = {scenario["id"]: scenario for scenario in PACKAGE["scenarios"]}
ACCEPTANCE = SCENARIOS["acceptance_conflict_unverified"]
GERMAN = SCENARIOS["fiktiver_pruefdatensatz_bodenplatte"]
SOURCE_FIELDS = {
    "spec_id", "source_type", "category", "title", "source_url", "document_ref", "location",
    "as_of", "scope", "text", "requirement", "verified",
}
PRIORITY = {"german_standard": 1, "user_requirement": 2, "external_other": 3}
CLAIM_WORDS = re.compile(r"violat|breach|deviat|non-?complian|verstoß|verstoss", re.IGNORECASE)
client = TestClient(app)


def verification(source: dict, checked_on: str) -> tuple[str, list[str]]:
    """Test oracle for the documented rules; reasons keep the documented order."""
    reasons = []
    if not (source["source_url"] or source["document_ref"]):
        reasons.append("missing_source_reference")
    if not source["location"]:
        reasons.append("missing_location")
    if not source["as_of"]:
        reasons.append("missing_as_of")
    else:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", source["as_of"]):
                raise ValueError
            if date.fromisoformat(source["as_of"]) > date.fromisoformat(checked_on):
                reasons.append("as_of_in_future")
        except ValueError:
            reasons.append("invalid_as_of")
    if source["verified"] is not True:
        reasons.append("not_confirmed")
    return ("unverified" if reasons else "verified"), reasons


def derived_context(scenario: dict) -> dict:
    """Recompute the expected context from the documented rules (test oracle only)."""
    lv = LV.model_validate(scenario["lv"])
    known = [p.oz for p in lv.positionen]
    by_oz = {oz: [] for oz in known}
    rejected, seen = [], set()
    for index, source in enumerate(scenario["sources"]):
        oz_list = source["scope"]["oz"]
        if source["spec_id"] in seen:
            rejected.append({"spec_id": source["spec_id"], "reason": "duplicate_spec_id", "oz": oz_list})
            continue
        seen.add(source["spec_id"])
        if not oz_list:
            rejected.append({"spec_id": source["spec_id"], "reason": "missing_scope", "oz": oz_list})
            continue
        if any(oz not in by_oz for oz in oz_list):
            rejected.append({"spec_id": source["spec_id"], "reason": "unknown_oz", "oz": oz_list})
            continue
        status, reasons = verification(source, scenario["checked_on"])
        priority = PRIORITY[source["category"]] if status == "verified" else 4
        for oz in oz_list:
            by_oz[oz].append((priority, index, {
                "spec_id": source["spec_id"], "source_type": source["source_type"],
                "category": source["category"], "priority": priority,
                "verification": status, "unverified_reasons": reasons,
            }))
    return {
        "lv": {"name": lv.name, "quelle": lv.quelle},
        "checked_on": scenario["checked_on"],
        "content_is_data": True,
        "items": [{
            "oz": p.oz, "kurztext": p.kurztext, "titel_pfad": p.titel_pfad,
            "sources": [entry for _, _, entry in sorted(by_oz[p.oz], key=lambda e: e[:2])],
        } for p in lv.positionen],
        "rejected_sources": rejected,
    }


def test_package_is_synthetic_offline_and_uses_english_fields():
    assert PACKAGE["synthetic"] is True
    assert set(PACKAGE["field_mapping"].values()) - {"document_ref"} <= SOURCE_FIELDS | {"priority"}
    for scenario in PACKAGE["scenarios"]:
        assert scenario["fictional"] is True
        for source in scenario["sources"]:
            assert set(source) == SOURCE_FIELDS
            assert source["source_type"] in PACKAGE["source_types"]
            assert source["category"] in PACKAGE["categories"]
            if source["source_url"] is not None:
                assert re.fullmatch(r"https://[a-z0-9.-]+\.example\.invalid/\S*", source["source_url"])
    for source in GERMAN["sources"]:
        if source["category"] == "german_standard":
            assert "fiktiv" in source["title"].lower() and "fiktiv" in source["text"].lower()
    assert "FIKTIV" in GERMAN["lv"]["name"] and GERMAN["language"] == "de"


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS))
def test_expected_context_follows_documented_verification_and_priority(scenario_id):
    scenario = SCENARIOS[scenario_id]
    assert scenario["expected_context"] == derived_context(scenario)
    assert [item["oz"] for item in scenario["expected_context"]["items"]] == [
        p["oz"] for p in scenario["lv"]["positionen"]]


def test_missing_reference_and_invalid_or_future_dates_are_unverified():
    sources = {s["spec_id"]: s for s in GERMAN["expected_context"]["items"][0]["sources"]
               + GERMAN["expected_context"]["items"][1]["sources"]}
    assert sources["F-I1"]["verification"] == "unverified"
    assert "invalid_as_of" in sources["F-I1"]["unverified_reasons"]
    assert sources["F-N2"]["unverified_reasons"][0] == "missing_source_reference"
    assert sources["F-D2"]["unverified_reasons"] == ["as_of_in_future"]
    assert GERMAN["expected_context"]["rejected_sources"][0]["reason"] == "unknown_oz"


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS))
def test_expected_notes_fit_existing_note_contract_and_cite_known_sources(scenario_id):
    scenario = SCENARIOS[scenario_id]
    oz_sources = {item["oz"]: {s["spec_id"]: s for s in item["sources"]}
                  for item in scenario["expected_context"]["items"]}
    for raw in scenario["expected_notes"]:
        note = Note.model_validate(raw)
        assert note.manual_review and note.source == "model_mock"
        cited = {e.reference_id for e in note.evidence}
        assert cited and cited <= set(oz_sources[note.oz])
        assert all(e.oz == note.oz for e in note.evidence)
        verified_german = [s for s in oz_sources[note.oz].values()
                           if s["category"] == "german_standard" and s["verification"] == "verified"]
        if note.step == "standards" and not verified_german:
            assert note.text.startswith("Manual review")
            assert not CLAIM_WORDS.search(note.text)
        if note.step == "standards" and verified_german:
            assert {s["spec_id"] for s in verified_german} <= cited


def test_acceptance_note1_names_both_sources_and_conflict():
    note1 = next(n for n in ACCEPTANCE["expected_notes"] if n["step"] == "comparison")
    assert note1["oz"] == "01.001" and "Conflict" in note1["text"]
    for needle in ("S10", "S12", "10 cm", "12 cm", "user requirement A", "external requirement B"):
        assert needle in note1["text"]


def test_embedded_instruction_in_external_text_stays_data():
    note_texts = " ".join(n["text"] for n in GERMAN["expected_notes"])
    assert "Ignoriere" not in note_texts
    assert any(n["step"] == "standards" and n["text"].startswith("Deviation")
               for n in GERMAN["expected_notes"])


def test_step_api_projection_uses_existing_specification_model():
    for scenario in PACKAGE["scenarios"]:
        context = scenario["expected_context"]
        statuses = {(item["oz"], s["spec_id"]): s for item in context["items"] for s in item["sources"]}
        texts = {s["spec_id"]: s["text"] for s in scenario["sources"]}
        projected = [Specification.model_validate(s) for s in scenario["step_api_specifications"]]
        assert [(s.oz, s.id) for s in projected] == list(statuses)
        for spec in projected:
            entry = statuses[(spec.oz, spec.id)]
            assert spec.text == texts[spec.id]
            assert spec.source == ("standard" if entry["category"] == "german_standard"
                                   else entry["source_type"])
            assert spec.verified_applicable == (entry["category"] == "german_standard"
                                                and entry["verification"] == "verified")


@pytest.mark.parametrize("step,note_id", [("comparison", "Note1"), ("standards", "Note2")])
def test_acceptance_projection_runs_through_existing_offline_step_mock(step, note_id):
    request = {"step": step, "lv": ACCEPTANCE["lv"],
               "specifications": ACCEPTANCE["step_api_specifications"]}
    assert request["specifications"] == [
        Specification.model_validate(s).model_dump() for s in CONFLICT_EXAMPLE["specifications"]]
    body = client.post("/api/comparison/steps", json=request).json()
    assert body["status"] == "placeholder" and body["findings"] == []
    assert body["notes"][-1]["id"] == note_id and body["notes"][-1]["manual_review"]
    assert {e["reference_id"] for e in body["evidence"]} == {"S10", "S12"}


def test_german_dataset_is_not_answered_by_the_fixed_step_mock():
    body = client.post("/api/comparison/steps", json={
        "step": "standards", "lv": GERMAN["lv"],
        "specifications": GERMAN["step_api_specifications"],
    }).json()
    assert body["status"] == "error"
    assert body["errors"][0]["code"] == "placeholder_unavailable"
    assert body["findings"] == []
