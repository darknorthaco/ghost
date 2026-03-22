"""Governance policy gate."""

from ghost_governance.policy import policy_change_approved


def test_policy_allows_when_disabled() -> None:
    cfg = {"governance": {"require_human_approval_for_policy_change": False}}
    assert policy_change_approved({}, cfg) is True


def test_policy_denies_without_token_when_required() -> None:
    cfg = {"governance": {"require_human_approval_for_policy_change": True, "policy_approval_token": "secret"}}
    assert policy_change_approved({}, cfg) is False


def test_policy_allows_with_header() -> None:
    cfg = {"governance": {"require_human_approval_for_policy_change": True, "policy_approval_token": "secret"}}
    headers = {"X-Ghost-Policy-Approve": "secret"}
    assert policy_change_approved(headers, cfg) is True
