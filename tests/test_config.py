"""The default limits are a policy; these tests keep its reasoning from eroding."""

from decimal import Decimal

from invoice_api.config import Settings

# A typical extraction costs about 0.00034 USD (measured with the eval at the
# default prices); this leaves room for longer invoices and retries.
TYPICAL_EXTRACTION_USD = Decimal("0.0005")


def default(name: str) -> Decimal:
    return Settings.model_fields[name].default


def test_exhausting_the_global_budget_takes_many_accounts():
    """The global budget stops everybody, so the more accounts it takes to spend
    it, the more expensive it is to switch the service off."""
    accounts = default("GLOBAL_DAILY_BUDGET_USD") / default("USER_DAILY_BUDGET_USD")

    assert accounts >= 100


def test_the_user_budget_still_allows_a_real_days_work():
    extractions = default("USER_DAILY_BUDGET_USD") / TYPICAL_EXTRACTION_USD

    assert extractions >= 100
