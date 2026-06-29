"""Budget enforcement unit tests."""

import pytest

from orbi_gateway.services.budget import BudgetExceededError, BudgetSnapshot, enforce_budget


def test_budget_allows_request_within_both_limits() -> None:
    enforce_budget(BudgetSnapshot(100, 20, 1000, 200), 50)


def test_budget_rejects_request_over_daily_limit() -> None:
    with pytest.raises(BudgetExceededError, match="daily"):
        enforce_budget(BudgetSnapshot(100, 90, 1000, 0), 11)


def test_budget_rejects_request_over_monthly_limit() -> None:
    with pytest.raises(BudgetExceededError, match="monthly"):
        enforce_budget(BudgetSnapshot(1000, 0, 100, 95), 6)
