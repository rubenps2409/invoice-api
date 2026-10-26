import json
from decimal import Decimal

import pytest
from pydantic import ValidationError

from invoice_api.schemas.extraction import ExtractedInvoice

VALID = {
    "supplier_name": "Acme S.L.",
    "invoice_number": "INV-2026-0042",
    "issue_date": "2026-03-15",
    "base_amount": "100.00",
    "tax_amount": "21.00",
    "total_amount": "121.00",
    "category_name": "Software",
}


def make(**overrides):
    return ExtractedInvoice.model_validate({**VALID, **overrides})


def test_valid_payload_is_parsed():
    invoice = make()

    assert invoice.supplier_name == "Acme S.L."
    assert invoice.issue_date.isoformat() == "2026-03-15"
    assert invoice.total_amount == Decimal("121.00")
    assert invoice.category_name == "Software"


def test_json_numbers_are_accepted_as_amounts():
    """LLMs usually emit JSON numbers (floats), not strings."""
    raw = (
        '{"supplier_name": "Acme", "invoice_number": "1", "issue_date": "2026-01-02",'
        ' "base_amount": 33.1, "tax_amount": 6.95, "total_amount": 40.05}'
    )

    invoice = ExtractedInvoice.model_validate(json.loads(raw))

    assert invoice.base_amount + invoice.tax_amount == invoice.total_amount


def test_tax_id_is_normalised():
    assert make(supplier_tax_id="ES-b12.345.678").supplier_tax_id == "B12345678"


def test_tax_id_may_be_missing_or_null():
    assert make().supplier_tax_id is None
    assert make(supplier_tax_id=None).supplier_tax_id is None


@pytest.mark.parametrize(
    "value", ["", "N/A", "not printed", "B1", 12345678, 1.5, True, [], {}]
)
def test_an_unusable_tax_id_is_dropped_instead_of_rejecting_the_invoice(value):
    invoice = make(supplier_tax_id=value)

    assert invoice.supplier_tax_id is None
    assert invoice.supplier_name == "Acme S.L."


def test_category_may_be_missing():
    payload = {k: v for k, v in VALID.items() if k != "category_name"}

    assert ExtractedInvoice.model_validate(payload).category_name is None


def test_category_may_be_null():
    assert make(category_name=None).category_name is None


def test_unknown_keys_are_ignored():
    invoice = make(currency="EUR", notes="thanks")

    assert not hasattr(invoice, "currency")


def test_text_fields_are_trimmed():
    assert make(supplier_name="  Acme S.L.  ").supplier_name == "Acme S.L."


def test_credit_notes_with_negative_amounts_are_valid():
    invoice = make(base_amount="-100.00", tax_amount="-21.00", total_amount="-121.00")

    assert invoice.total_amount == Decimal("-121.00")


@pytest.mark.parametrize(
    "overrides",
    [
        {"total_amount": "999.00"},
        {"supplier_name": ""},
        {"supplier_name": "x" * 256},
        {"invoice_number": ""},
        {"issue_date": "15/03/2026"},
        {"issue_date": "2026-13-45"},
        {"base_amount": "100.001", "total_amount": "121.001"},
        {"base_amount": "abc"},
        {"base_amount": "NaN", "total_amount": "NaN"},
        {"base_amount": "100000000.00", "total_amount": "100000021.00"},
        {"supplier_name": None},
        {"category_name": "x" * 101},
    ],
    ids=[
        "totals-mismatch",
        "empty-supplier",
        "supplier-too-long",
        "empty-number",
        "wrong-date-format",
        "impossible-date",
        "three-decimals",
        "text-amount",
        "nan",
        "amount-too-large",
        "null-supplier",
        "category-too-long",
    ],
)
def test_invalid_payloads_are_rejected(overrides):
    with pytest.raises(ValidationError):
        make(**overrides)


@pytest.mark.parametrize(
    "field",
    [
        "supplier_name",
        "invoice_number",
        "issue_date",
        "base_amount",
        "tax_amount",
        "total_amount",
    ],
)
def test_required_fields_are_enforced(field):
    payload = {k: v for k, v in VALID.items() if k != field}

    with pytest.raises(ValidationError):
        ExtractedInvoice.model_validate(payload)
