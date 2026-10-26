"""The default limits are a policy; these tests keep its reasoning from eroding."""

import re
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from invoice_api.config import SECRET_KEY_MIN_LENGTH, SECRET_KEY_PLACEHOLDER, Settings

ENV_EXAMPLE = Path(__file__).parent.parent / ".env.example"

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


def settings_with(secret_key: str) -> Settings:
    return Settings(_env_file=None, DATABASE_URL="postgresql://x", SECRET_KEY=secret_key)


def test_a_strong_secret_key_is_accepted():
    key = "a" * SECRET_KEY_MIN_LENGTH

    assert settings_with(key).SECRET_KEY == key


@pytest.mark.parametrize(
    "key",
    ["", "short", "a" * (SECRET_KEY_MIN_LENGTH - 1), SECRET_KEY_PLACEHOLDER],
    ids=["empty", "short", "one-char-short", "placeholder"],
)
def test_a_weak_secret_key_is_rejected(key):
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        settings_with(key)


def example_variables() -> dict[str, str]:
    """NAME -> value of every line of .env.example, commented out or not."""
    found = {}
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"#?\s?([A-Z][A-Z0-9_]*)=(.*)", line)
        if match:
            found[match[1]] = match[2]
    return found


def test_env_example_lists_every_setting():
    missing = set(Settings.model_fields) - set(example_variables())

    assert not missing


def test_env_example_secret_key_is_the_rejected_placeholder():
    assert example_variables()["SECRET_KEY"] == SECRET_KEY_PLACEHOLDER


def test_env_example_defaults_match_the_code():
    """A commented-out line documents a default, so it must be the real one."""
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = re.match(r"# ([A-Z][A-Z0-9_]*)=(.*)", line)
        if match and match[1] in Settings.model_fields:
            default = Settings.model_fields[match[1]].default
            assert str(default) == match[2], match[1]
