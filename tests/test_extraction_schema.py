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
    "currency": "EUR",
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
        ' "base_amount": 33.1, "tax_amount": 6.95, "total_amount": 40.05, "currency": "EUR"}'
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


def test_withholding_defaults_to_zero():
    assert make().withholding_amount == Decimal("0")


def test_an_invoice_with_a_withholding_is_valid_with_the_honest_figures():
    invoice = make(
        base_amount="1000.00",
        tax_amount="210.00",
        withholding_amount="150.00",
        total_amount="1060.00",
    )

    assert invoice.tax_amount == Decimal("210.00")  # the tax is not reduced
    assert invoice.withholding_amount == Decimal("150.00")


def test_a_withholding_left_out_of_an_invoice_that_has_one_is_rejected():
    """The model forgot the withholding: the totals no longer add up."""
    with pytest.raises(ValidationError):
        make(base_amount="1000.00", tax_amount="210.00", total_amount="1060.00")


@pytest.mark.parametrize(
    ("total", "valid"),
    [
        ("121.00", True),
        ("121.01", True),
        ("120.99", True),
        ("121.02", False),
        ("120.98", False),
    ],
)
def test_the_total_may_be_one_cent_off(total, valid):
    if valid:
        assert make(total_amount=total).total_amount == Decimal(total)
    else:
        with pytest.raises(ValidationError):
            make(total_amount=total)


def test_amounts_are_normalised_to_two_decimals():
    invoice = make(base_amount=33.1, tax_amount=6.95, total_amount=40.05)

    assert [
        str(a) for a in (invoice.base_amount, invoice.tax_amount, invoice.total_amount)
    ] == [
        "33.10",
        "6.95",
        "40.05",
    ]
    assert str(invoice.withholding_amount) == "0.00"


def test_a_negative_withholding_cannot_absorb_an_unmodelled_amount():
    """Non-taxable expenses (45) hidden as a negative withholding would add up:
    600 + 126 - (-45) = 771. A normal invoice cannot have mixed signs."""
    with pytest.raises(ValidationError, match="be positive or all negative"):
        make(
            base_amount="600.00",
            tax_amount="126.00",
            withholding_amount="-45.00",
            total_amount="771.00",
        )


def test_a_credit_note_reverses_every_amount_including_the_withholding():
    invoice = make(
        base_amount="-500.00",
        tax_amount="-105.00",
        withholding_amount="-75.00",
        total_amount="-530.00",
    )

    assert invoice.withholding_amount == Decimal("-75.00")


def test_a_credit_note_whose_withholding_keeps_its_positive_sign_is_rejected():
    # The model copied the printed +75: the retry feedback must point at the signs.
    with pytest.raises(ValidationError, match="be positive or all negative"):
        make(
            base_amount="-500.00",
            tax_amount="-105.00",
            withholding_amount="75.00",
            total_amount="-680.00",
        )


def test_currency_is_required():
    payload = {k: v for k, v in VALID.items() if k != "currency"}

    with pytest.raises(ValidationError):
        ExtractedInvoice.model_validate(payload)


@pytest.mark.parametrize("currency", [None, "", "EURO", "€", "E1R", 978, ["EUR"]])
def test_an_unusable_currency_is_rejected_not_guessed(currency):
    with pytest.raises(ValidationError):
        make(currency=currency)


@pytest.mark.parametrize(
    ("raw", "expected"), [("EUR", "EUR"), ("eur", "EUR"), (" usd ", "USD")]
)
def test_currency_is_upper_cased(raw, expected):
    assert make(currency=raw).currency == expected


def test_category_may_be_missing():
    payload = {k: v for k, v in VALID.items() if k != "category_name"}

    assert ExtractedInvoice.model_validate(payload).category_name is None


def test_category_may_be_null():
    assert make(category_name=None).category_name is None


def test_unknown_keys_are_ignored():
    invoice = make(language="es", notes="thanks")

    assert not hasattr(invoice, "language")


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
