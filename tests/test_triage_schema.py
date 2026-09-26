import json
import re
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from triage_schema import ROUTE_FOR_CATEGORY, Category, Route, TriageDecision

VALID = {
    "category": "billing",
    "priority": "P2",
    "route": "billing-team",
    "rationale": "Double charge puts money at stake, so P2.",
}


def failed_fields(data: dict) -> set[str]:
    with pytest.raises(ValidationError) as excinfo:
        TriageDecision.model_validate(data)
    return {str(error["loc"][0]) for error in excinfo.value.errors()}


def test_valid_decision():
    decision = TriageDecision.model_validate(VALID)
    assert decision.model_dump() == VALID


def test_valid_decision_from_json():
    assert TriageDecision.model_validate_json(json.dumps(VALID)).route == "billing-team"


@pytest.mark.parametrize("category,route", ROUTE_FOR_CATEGORY.items())
def test_every_policy_pairing_validates(category, route):
    TriageDecision.model_validate({**VALID, "category": category, "route": route})


@pytest.mark.parametrize("priority", ["P1", "P2", "P3", "P4"])
def test_every_priority_validates(priority):
    TriageDecision.model_validate({**VALID, "priority": priority})


def test_pairing_matches_triage_policy():
    policy = (Path(__file__).resolve().parent.parent / "TRIAGE_POLICY.md").read_text(encoding="utf-8")
    table = dict(re.findall(r"^\| ([a-z-]+) \|.*\| ([a-z-]+-team) \|$", policy, flags=re.MULTILINE))
    assert ROUTE_FOR_CATEGORY == table
    assert set(ROUTE_FOR_CATEGORY) == set(get_args(Category))
    assert set(ROUTE_FOR_CATEGORY.values()) == set(get_args(Route))


@pytest.mark.parametrize("field", ["category", "priority", "route", "rationale"])
def test_missing_field_is_rejected(field):
    data = {k: v for k, v in VALID.items() if k != field}
    assert field in failed_fields(data)


def test_extra_field_is_rejected():
    assert "confidence" in failed_fields({**VALID, "confidence": 0.9})


@pytest.mark.parametrize(
    "field,value",
    [
        ("category", "shipping"),
        ("category", "Billing"),
        ("priority", "P5"),
        ("priority", "p2"),
        ("priority", 2),
        ("route", "sales-team"),
        ("rationale", 42),
    ],
)
def test_out_of_set_value_is_rejected(field, value):
    assert failed_fields({**VALID, field: value}) == {field}


def test_category_route_mismatch_names_route():
    with pytest.raises(ValidationError) as excinfo:
        TriageDecision.model_validate({**VALID, "route": "bug-team"})
    errors = excinfo.value.errors()
    assert [e["loc"] for e in errors] == [("route",)]
    assert "billing-team" in errors[0]["msg"]


@pytest.mark.parametrize("rationale", ["", "   ", "\t"])
def test_blank_rationale_is_rejected(rationale):
    assert failed_fields({**VALID, "rationale": rationale}) == {"rationale"}


@pytest.mark.parametrize(
    "rationale",
    ["First line.\nSecond line.", "One.\r\nTwo.", "Trailing newline.\n", "One. Two.", "One.\x85Two.", "One.\vTwo.", "One.\fTwo."],
)
def test_multi_line_rationale_is_rejected(rationale):
    assert failed_fields({**VALID, "rationale": rationale}) == {"rationale"}


def test_invalid_category_with_mismatched_route_names_only_category():
    assert failed_fields({**VALID, "category": "shipping", "route": "bug-team"}) == {"category"}


@pytest.mark.parametrize(
    "change,field",
    [({"confidence": 0.9}, "confidence"), ({"route": "bug-team"}, "route"), ({"priority": 2}, "priority")],
)
def test_json_input_is_rejected_like_dicts(change, field):
    with pytest.raises(ValidationError) as excinfo:
        TriageDecision.model_validate_json(json.dumps({**VALID, **change}))
    assert {str(e["loc"][0]) for e in excinfo.value.errors()} == {field}


def test_decision_cannot_be_changed_after_validation():
    decision = TriageDecision.model_validate(VALID)
    with pytest.raises(ValidationError):
        decision.route = "bug-team"


def test_rationale_with_abbreviations_is_one_line():
    TriageDecision.model_validate({**VALID, "rationale": "Double charge (e.g. on v2.1 invoices) is money at stake, so P2."})
