"""Contract checks for the synthetic estimate scenario package (issue #20).

These tests do not implement ``select_cases`` or ``estimate_scenarios``. They
recompute the documented rules from ``docs/schaetzszenarien.md`` with a small
test oracle and check that ``data/architektur/schaetzszenarien.json`` follows
them. They also check that the expected notes fit the existing ``Note`` and
``HistoryRecord`` models and that the acceptance pools agree with the existing
offline step mock, without changing either.
"""
import json
import re
from collections import Counter
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ai.step_api import SYNTHETIC_LV, HistoryRecord, Note
from app.main import app

ROOT = Path(__file__).resolve().parents[2]
DOC = (ROOT / "docs/schaetzszenarien.md").read_text(encoding="utf-8")
PACKAGE = json.loads((ROOT / "data/architektur/schaetzszenarien.json").read_text(encoding="utf-8"))
RULES = PACKAGE["rules"]
POOLS = PACKAGE["history_pools"]
SCENARIOS = {scenario["id"]: scenario for scenario in PACKAGE["scenarios"]}
LABEL = "Estimate – approval required"
STEP = {"comparable": "historical_adjustment", "what_if": "what_if"}
NOTE_PREFIX = {"comparable": "Note3", "what_if": "Note4"}
RATIO_STEP, VALUE_STEP = Decimal("0.0001"), Decimal("0.01")
client = TestClient(app)


def dec(value) -> Decimal:
    return Decimal(str(value))


def number(value: Decimal | None):
    """JSON form of a rounded decimal: int when whole, else float."""
    if value is None:
        return None
    return int(value) if value == value.to_integral_value() else float(value)


def canonical_unit(unit: str) -> str:
    stripped = unit.strip()
    for canonical, aliases in RULES["unit_aliases"].items():
        if stripped.casefold() in {alias.casefold() for alias in aliases}:
            return canonical
    return stripped


def normalized_tags(tags: list[str]) -> set[str]:
    return {tag.strip().casefold() for tag in tags if tag.strip()}


def exclusion_reason(record: dict, position: dict, mode: str):
    """Test oracle: first documented exclusion reason, or the measurement pair."""
    work = normalized_tags(position["work_tags"])
    same_work = bool(work) and work <= normalized_tags(record["tags"])
    if mode == "comparable" and not same_work:
        return "work_mismatch", None
    if mode == "what_if" and same_work:
        return "comparable_case", None
    estimated = [m for m in record["estimated_values"] if m["metric"] == position["metric"]]
    if not estimated:
        return "missing_estimated_value", None
    if len(estimated) > 1:
        return "ambiguous_measurement", None
    est = estimated[0]
    real = [m for m in record["real_values"]
            if (m["metric"], m["oz"], m.get("title_path", []))
            == (est["metric"], est["oz"], est.get("title_path", []))]
    if not real:
        return "missing_real_value", None
    if len(real) > 1:
        return "ambiguous_measurement", None
    act = real[0]
    if est["value"] is None:
        return "missing_estimated_value", None
    if act["value"] is None:
        return "missing_real_value", None
    target = canonical_unit(position["unit"])
    if canonical_unit(est["unit"]) != target or canonical_unit(act["unit"]) != target:
        return "incompatible_unit", None
    if est["value"] == 0:
        return "zero_estimated_value", None
    if est["value"] < 0 or act["value"] < 0:
        return "negative_value", None
    return None, (est, act)


def recency_key(record: dict):
    return -date.fromisoformat(record["date"]).toordinal(), record["case_id"]


def select_cases(position: dict, history: list[dict], mode: str, limit) -> dict:
    """Test oracle for the documented selection; text fields are checked separately."""
    result = {"mode": mode, "oz": position["oz"], "limit": limit,
              "candidate_count": len(history), "selected": [], "excluded": []}
    low, high = RULES["limit_range"]
    if not isinstance(limit, int) or isinstance(limit, bool) or not low <= limit <= high:
        return {**result, "status": "invalid_limit", "case_count": 0}
    qualifying = []
    for record in sorted(history, key=recency_key):
        reason, pair = exclusion_reason(record, position, mode)
        if reason:
            result["excluded"].append({"case_id": record["case_id"], "date": record["date"],
                                       "reason": reason})
            continue
        est, act = pair
        qualifying.append({
            "case_id": record["case_id"], "date": record["date"], "tags": record["tags"],
            "description": record["description"], "case_oz": est["oz"],
            "title_path": est.get("title_path", []), "estimated_value": est["value"],
            "real_value": act["value"], "unit": canonical_unit(position["unit"]),
            "ratio": number((dec(act["value"]) / dec(est["value"])).quantize(
                RATIO_STEP, ROUND_HALF_EVEN)),
        })
    result["selected"] = qualifying[:limit]
    result["excluded"] += [{"case_id": c["case_id"], "date": c["date"], "reason": "over_limit"}
                           for c in qualifying[limit:]]
    result["excluded"].sort(key=recency_key)
    count = len(result["selected"])
    if not history:
        status = "no_history"
    elif count == 0:
        status = "no_qualifying_cases"
    elif count < RULES["min_cases"]:
        status = "insufficient_cases"
    elif count < RULES["target_cases"][0]:
        status = "small_dataset"
    else:
        status = "sufficient"
    return {**result, "status": status, "case_count": count}


def median(values: list[Decimal]) -> Decimal:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def estimate_scenarios(position: dict, selection: dict, assumptions: dict) -> dict:
    """Test oracle for the documented estimate; text fields are checked separately."""
    missing = []
    status = selection["status"]
    if status in ("invalid_limit", "no_history", "no_qualifying_cases", "insufficient_cases"):
        missing.append(status)
    if status == "small_dataset":
        missing.append("below_target_case_count")
    method_ok = False
    if assumptions["ratio_method"] is None:
        missing.append("ratio_method_not_selected")
    elif assumptions["ratio_method"] not in RULES["ratio_methods"]:
        missing.append("unsupported_ratio_method")
    elif assumptions["selected_by"] != "estimator":
        missing.append("ratio_method_not_approved")
    else:
        method_ok = True
    ratios = [dec(case["ratio"]) for case in selection["selected"]]
    factor = None
    if method_ok and status in ("sufficient", "small_dataset"):
        factor = median(ratios).quantize(RATIO_STEP, ROUND_HALF_EVEN)
    target = canonical_unit(position["unit"])
    baseline = assumptions["baseline"]
    base = None
    if baseline is None or baseline["value"] is None:
        missing.append("missing_baseline")
    elif canonical_unit(baseline["unit"]) != target:
        missing.append("incompatible_baseline_unit")
    else:
        base = dec(baseline["value"])
    estimated = (base * factor).quantize(VALUE_STEP, ROUND_HALF_EVEN) \
        if base is not None and factor is not None else None
    price = assumptions["unit_price"]
    price_ok = False
    if price is None or price["value"] is None:
        missing.append("missing_price")
    elif price["source"] != "estimator" or price["approved"] is not True:
        missing.append("price_not_approved")
    elif price["currency"] != "EUR" or canonical_unit(price["per_unit"]) != target:
        missing.append("incompatible_price_unit")
    else:
        price_ok = True
    euro = (estimated * dec(price["value"])).quantize(VALUE_STEP, ROUND_HALF_EVEN) \
        if price_ok and estimated is not None else None
    mode = selection["mode"]
    return {
        "note_id": f"{NOTE_PREFIX[mode]}:{position['oz']}", "step": STEP[mode], "scenario": mode,
        "oz": position["oz"],
        "status": "estimated" if estimated is not None else
                  "factor_only" if factor is not None else "no_factor",
        "case_ids": [case["case_id"] for case in selection["selected"]],
        "case_count": selection["case_count"], "selection_status": status,
        "ratio_method": assumptions["ratio_method"], "factor": number(factor),
        "ratio_range": [number(min(ratios)), number(max(ratios))] if ratios else None,
        "base_value": number(base),
        "estimated_value": number(estimated), "unit": target,
        "unit_price": price["value"] if price_ok else None, "euro_amount": number(euro),
        "missing_evidence": missing, "approval_required": True, "label": LABEL,
    }


def history_of(scenario: dict) -> list[dict]:
    return POOLS[scenario["history_pool"]]


def without_text(selection: dict) -> dict:
    return {key: value for key, value in selection.items() if key != "selection_reason"}


def test_package_is_synthetic_and_history_fits_existing_record_model():
    assert PACKAGE["synthetic"] is True and PACKAGE["issue"] == 20
    for pool in POOLS.values():
        for record in pool:
            HistoryRecord.model_validate(record)
            assert record["description"].startswith("Synthetic")
            assert re.fullmatch(r"[A-Z]+\d+", record["case_id"])
        ids = [record["case_id"] for record in pool]
        assert len(ids) == len(set(ids))
    assert canonical_unit(" Std ") == "h" and canonical_unit("d") != "h"


def test_documented_rule_lists_match_package():
    for name in ("exclusion_reasons", "selection_statuses", "missing_evidence_codes"):
        for code in RULES[name]:
            assert f"`{code}`" in DOC, code
    assert "select_cases(position, history, mode, limit)" in DOC
    assert "estimate_scenarios(position, cases, assumptions)" in DOC
    assert LABEL in DOC


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS))
def test_expected_selection_follows_documented_rules(scenario_id):
    scenario = SCENARIOS[scenario_id]
    history = history_of(scenario)
    expected = scenario["expected_selection"]
    assert without_text(expected) == select_cases(
        scenario["position"], history, scenario["mode"], scenario["limit"])
    if expected["status"] != "invalid_limit":
        listed = [c["case_id"] for c in expected["selected"]] + \
                 [c["case_id"] for c in expected["excluded"]]
        assert sorted(listed) == sorted(r["case_id"] for r in history)
    keys = [recency_key(c) for c in expected["selected"]]
    assert keys == sorted(keys)


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS))
def test_expected_estimate_follows_documented_rules(scenario_id):
    scenario = SCENARIOS[scenario_id]
    assert scenario["expected_estimate"] == estimate_scenarios(
        scenario["position"], scenario["expected_selection"], scenario["assumptions"])


@pytest.mark.parametrize("scenario_id", sorted(SCENARIOS))
def test_expected_note_projects_onto_existing_note_contract(scenario_id):
    scenario = SCENARIOS[scenario_id]
    estimate, selection = scenario["expected_estimate"], scenario["expected_selection"]
    note = Note.model_validate(scenario["expected_note"])
    assert (note.id, note.step, note.oz) == (estimate["note_id"], estimate["step"], estimate["oz"])
    assert note.manual_review and note.approval_required and note.source == "model_mock"
    assert note.case_ids == estimate["case_ids"] and note.case_count == estimate["case_count"]
    assert note.base_value == estimate["base_value"]
    assert note.estimated_value == estimate["estimated_value"] and note.unit == estimate["unit"]
    assert note.selection_reason == selection["selection_reason"]
    assert [e.reference_id for e in note.evidence] == note.case_ids
    assert all(e.oz == note.oz and e.source == "history" for e in note.evidence)
    for case, evidence in zip(selection["selected"], note.evidence):
        assert case["date"] in evidence.detail and f"case OZ {case['case_oz']}" in evidence.detail
    assert note.text.startswith(LABEL + ".") and f"OZ {note.oz}" in note.text
    assert f"{note.case_count} " in note.text
    for field in (note.selection_reason, note.assumption, note.uncertainty):
        assert field
    for code in estimate["missing_evidence"]:
        assert code in note.text
    texts = " ".join((note.text, note.selection_reason, note.assumption, note.uncertainty))
    if estimate["euro_amount"] is None:
        assert "EUR" not in texts and "€" not in texts
    else:
        assert f"{estimate['euro_amount']:g} EUR" in note.text
    if estimate["scenario"] == "what_if":
        assert "what-if" in note.selection_reason.lower()
        assert note.assumption.startswith("Hypothetical")
        assert "less certain" in note.uncertainty


def test_acceptance_note3_and_note4_use_separate_pools():
    note3 = SCENARIOS["acceptance_note3_comparable"]["expected_estimate"]
    note4 = SCENARIOS["acceptance_note4_what_if"]["expected_estimate"]
    assert (note3["factor"], note3["base_value"], note3["estimated_value"]) == (1.2, 50, 60)
    assert (note4["factor"], note4["base_value"], note4["estimated_value"]) == (1.4, 50, 70)
    assert note3["case_ids"] == ["H1", "H2", "H3"] and note4["case_ids"] == ["W1", "W2", "W3"]
    assert note3["case_count"] == note4["case_count"] == 3
    assert note3["ratio_method"] == note4["ratio_method"] == "median"
    assert note3["euro_amount"] is None and "missing_price" in note3["missing_evidence"]
    assert "below_target_case_count" in note3["missing_evidence"]


def test_documented_edge_selections():
    big = SCENARIOS["selection_25_cases_limit_20"]["expected_selection"]
    assert big["candidate_count"] == 25 and big["case_count"] == 20
    assert Counter(c["reason"] for c in big["excluded"]) == {"over_limit": 5}
    assert big["status"] == "sufficient"
    last, first_out = big["selected"][-1], next(
        c for c in big["excluded"] if c["date"] == big["selected"][-1]["date"])
    assert last["case_id"] < first_out["case_id"]  # tie on date, broken by case_id
    zero = SCENARIOS["selection_zero_cases"]["expected_estimate"]
    assert zero["case_count"] == 0 and zero["factor"] is None
    assert zero["missing_evidence"][0] == "no_history"
    excluded = SCENARIOS["excluded_values_and_units"]
    reasons = {c["case_id"]: c["reason"] for c in excluded["expected_selection"]["excluded"]}
    assert {"zero_estimated_value", "missing_estimated_value", "incompatible_unit",
            "missing_real_value", "work_mismatch", "ambiguous_measurement",
            "negative_value"} <= set(reasons.values())
    assert excluded["expected_estimate"]["factor"] is None
    assert excluded["expected_estimate"]["case_count"] == 2


def test_factor_and_price_need_estimator_approval():
    assert SCENARIOS["ratio_method_not_selected"]["expected_estimate"]["factor"] is None
    unapproved = SCENARIOS["price_not_approved"]["expected_estimate"]
    assert unapproved["estimated_value"] == 60 and unapproved["euro_amount"] is None
    assert "price_not_approved" in unapproved["missing_evidence"]
    assert SCENARIOS["approved_price"]["expected_estimate"]["euro_amount"] == 4800
    factor_only = SCENARIOS["what_if_missing_baseline"]["expected_estimate"]
    assert factor_only["status"] == "factor_only" and factor_only["estimated_value"] is None


@pytest.mark.parametrize("scenario_id", ["acceptance_note3_comparable", "acceptance_note4_what_if"])
def test_acceptance_selection_agrees_with_existing_offline_step_mock(scenario_id):
    scenario = SCENARIOS[scenario_id]
    selected = {c["case_id"] for c in scenario["expected_selection"]["selected"]}
    records = [r for r in history_of(scenario) if r["case_id"] in selected]
    body = client.post("/api/comparison/steps", json={
        "step": scenario["expected_note"]["step"], "lv": SYNTHETIC_LV,
        "history_records": records,
    }).json()
    assert body["status"] == "placeholder"
    mock, expected = body["notes"][-1], scenario["expected_note"]
    for field in ("step", "oz", "case_ids", "case_count", "base_value", "estimated_value", "unit"):
        assert mock[field] == expected[field], field
