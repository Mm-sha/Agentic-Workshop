"""The triage decision every agent run returns: category, priority, route and rationale.

Validate a dict with TriageDecision.model_validate(data), or JSON text with
TriageDecision.model_validate_json(text). Anything invalid raises pydantic's
ValidationError, naming the field that failed.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, ValidationInfo, field_validator

Category = Literal["billing", "bug", "access", "performance", "how-to"]
Priority = Literal["P1", "P2", "P3", "P4"]
Route = Literal["billing-team", "bug-team", "access-team", "performance-team", "how-to-team"]

# One route per category, as in TRIAGE_POLICY.md.
ROUTE_FOR_CATEGORY: dict[str, str] = {
    "billing": "billing-team",
    "bug": "bug-team",
    "access": "access-team",
    "performance": "performance-team",
    "how-to": "how-to-team",
}


class TriageDecision(BaseModel):
    """A triage decision. Only well-formed decisions validate."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    category: Category
    priority: Priority
    route: Route
    rationale: str

    @field_validator("route")
    @classmethod
    def route_matches_category(cls, route: str, info: ValidationInfo) -> str:
        category = info.data.get("category")
        if category is not None and route != ROUTE_FOR_CATEGORY[category]:
            raise ValueError(f"route for category {category!r} must be {ROUTE_FOR_CATEGORY[category]!r}, got {route!r}")
        return route

    @field_validator("rationale")
    @classmethod
    def rationale_is_one_line(cls, rationale: str) -> str:
        if not rationale.strip():
            raise ValueError("rationale must not be empty")
        if rationale.splitlines() != [rationale]:
            raise ValueError("rationale must be a single line")
        return rationale
