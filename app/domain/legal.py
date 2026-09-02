from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class LegalRuleVersion(BaseModel):
    rule_code: str
    jurisdiction: str = "DE"
    valid_from: date
    valid_to: date | None = None
    tax_year: int | None = None
    version: int
    review_status: str = "draft"
    source_url: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)


def select_legal_rule(
    rules: list[LegalRuleVersion], *, rule_code: str, effective_on: date
) -> LegalRuleVersion | None:
    eligible = [
        rule
        for rule in rules
        if rule.rule_code == rule_code
        and rule.review_status == "approved"
        and rule.valid_from <= effective_on
        and (rule.valid_to is None or rule.valid_to >= effective_on)
    ]
    return max(eligible, key=lambda item: (item.valid_from, item.version), default=None)
