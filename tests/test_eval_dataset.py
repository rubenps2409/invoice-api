"""Guards the eval dataset itself, so a typo in a case cannot hide a regression."""

import re
from collections import Counter
from decimal import Decimal

import pytest

from evals.cases import CASES, CATEGORIES
from invoice_api.schemas.extraction import ExtractedInvoice
from invoice_api.schemas.invoice import check_amounts
from invoice_api.services.extraction import FEW_SHOT_EXAMPLES, SYSTEM_PROMPT

# Lines that name the customer: a tax id printed there is NOT the supplier's.
CUSTOMER_LINE = re.compile(r"^.*\b(?:Cliente|Customer|Bill to)\b.*$", re.M | re.I)

NIF_SHAPED = re.compile(r"\b[A-Z]\d{8}\b|\b\d{8}[A-Z]\b")

EXTRACTION_CASES = [c for c in CASES if c.expected is not None]
REFUSAL_CASES = [c for c in CASES if c.expected is None]


def test_dataset_has_enough_cases():
    assert 10 <= len(CASES) <= 50
    assert len(EXTRACTION_CASES) >= 10
    assert len(REFUSAL_CASES) >= 1


def test_case_ids_are_unique():
    duplicates = [i for i, n in Counter(c.id for c in CASES).items() if n > 1]
    assert duplicates == []


def _gap(invoice: ExtractedInvoice) -> Decimal:
    """How far the total is from base + tax - withholding."""
    return (
        invoice.base_amount
        + invoice.tax_amount
        - invoice.withholding_amount
        - invoice.total_amount
    )


@pytest.mark.parametrize("case", EXTRACTION_CASES, ids=lambda c: c.id)
def test_expected_values_are_a_valid_extraction(case):
    assert case.expected is not None

    invoice = ExtractedInvoice.model_validate(case.expected)  # also checks the totals

    assert abs(_gap(invoice)) <= Decimal("0.01")
    assert Decimal(case.expected["total_amount"]) == invoice.total_amount


@pytest.mark.parametrize("case", EXTRACTION_CASES, ids=lambda c: c.id)
def test_expected_category_is_one_of_the_offered_ones(case):
    assert case.expected is not None
    category = case.expected["category_name"]

    assert category is None or category in case.categories


def test_expected_values_appear_in_the_text_of_each_case():
    """Catches expected values that do not match their own text."""
    for case in EXTRACTION_CASES:
        assert case.expected is not None
        assert case.expected["invoice_number"] in case.text, case.id


def _without_separators(text: str) -> str:
    return re.sub(r"[\s.\-/]", "", text).upper()


def test_every_extraction_case_states_its_expected_tax_id():
    for case in EXTRACTION_CASES:
        assert case.expected is not None
        assert "supplier_tax_id" in case.expected, case.id


def test_an_expected_tax_id_is_printed_in_the_text_and_none_is_expected_otherwise():
    for case in EXTRACTION_CASES:
        assert case.expected is not None
        tax_id = case.expected["supplier_tax_id"]
        if tax_id is None:
            # A case that expects no tax id must not print anything shaped like one.
            supplier_side = CUSTOMER_LINE.sub("", case.text)
            assert not NIF_SHAPED.search(supplier_side), case.id
        else:
            assert tax_id in _without_separators(case.text), case.id


def test_some_cases_have_a_tax_id_and_some_do_not():
    expected = [c.expected for c in EXTRACTION_CASES if c.expected]

    assert any(e["supplier_tax_id"] for e in expected)
    assert any(e["supplier_tax_id"] is None for e in expected)


def test_a_case_tests_that_the_customers_tax_id_is_not_taken():
    case = next(c for c in EXTRACTION_CASES if c.id == "customer_tax_id_is_not_the_suppliers")

    assert case.expected is not None
    printed = set(NIF_SHAPED.findall(case.text))
    # The text really contains another tax id to be confused with.
    assert printed - {case.expected["supplier_tax_id"]}


def _expected_invoices() -> list[ExtractedInvoice]:
    return [
        ExtractedInvoice.model_validate(c.expected) for c in EXTRACTION_CASES if c.expected
    ]


def test_the_dataset_covers_withholdings_other_currencies_and_rounding_gaps():
    invoices = _expected_invoices()

    assert any(i.withholding_amount != 0 for i in invoices)
    assert any(i.currency != "EUR" for i in invoices)
    assert {"EUR", "USD", "GBP"} <= {i.currency for i in invoices}
    assert any(abs(_gap(i)) == Decimal("0.01") for i in invoices)  # printed as is


def test_a_withholding_case_keeps_the_withholding_out_of_the_tax():
    """If the tax absorbed the withholding, the totals would still add up."""
    case = next(c for c in EXTRACTION_CASES if c.id == "es_irpf_withholding_on_fees")
    invoice = ExtractedInvoice.model_validate(case.expected)

    assert invoice.tax_amount == invoice.base_amount * Decimal("0.21")
    assert invoice.withholding_amount > 0


@pytest.mark.parametrize(
    ("case_id", "base", "tax", "total"),
    [
        ("refuse_printed_total_two_cents_off", "250,00", "52,50", "302,52"),
        ("refuse_invoice_with_non_taxable_expenses", "600,00", "126,00", "771,00"),
    ],
)
def test_a_refusal_case_about_bent_figures_really_does_not_add_up(case_id, base, tax, total):
    """If the printed figures became acceptable (e.g. a wider tolerance), the case
    would no longer measure whether the model bends numbers to fit."""
    case = next(c for c in CASES if c.id == case_id)
    assert case.expected is None
    for figure in (base, tax, total):
        assert figure in case.text

    def amount(printed: str) -> Decimal:
        return Decimal(printed.replace(",", "."))

    with pytest.raises(ValueError):
        check_amounts(amount(base), amount(tax), Decimal(0), amount(total))


def test_the_credit_note_case_prints_the_withholding_with_the_opposite_sign():
    case = next(c for c in EXTRACTION_CASES if c.id == "credit_note_reverses_the_withholding")

    assert case.expected is not None
    assert "Retención IRPF 15%: 75,00" in case.text  # printed positive
    assert Decimal(case.expected["withholding_amount"]) == Decimal("-75.00")


def test_the_unknown_currency_case_is_a_refusal():
    case = next(c for c in CASES if c.id == "refuse_unknown_currency")

    assert case.expected is None


def test_some_cases_expect_no_category_and_some_expect_negative_amounts():
    expected = [c.expected for c in EXTRACTION_CASES if c.expected]

    assert any(e["category_name"] is None for e in expected)
    assert any(Decimal(e["total_amount"]) < 0 for e in expected)


def test_every_offered_category_is_used_by_some_case():
    used = {c.expected["category_name"] for c in EXTRACTION_CASES if c.expected}

    assert set(CATEGORIES) <= used


def test_cases_do_not_reuse_the_few_shot_examples():
    shown_texts = {text for _, text, _ in FEW_SHOT_EXAMPLES}
    shown_numbers = {out["invoice_number"] for _, _, out in FEW_SHOT_EXAMPLES}
    shown_suppliers = {out["supplier_name"] for _, _, out in FEW_SHOT_EXAMPLES}

    for case in CASES:
        assert case.text not in shown_texts, case.id
        if case.expected:
            assert case.expected["invoice_number"] not in shown_numbers, case.id
            assert case.expected["supplier_name"] not in shown_suppliers, case.id


def test_the_system_prompt_does_not_leak_any_case():
    """A rule in the prompt must not quote a case, or that case proves nothing."""
    for case in CASES:
        for line in case.text.splitlines():
            if len(line.strip()) >= 8:
                assert line.strip() not in SYSTEM_PROMPT, case.id
        if case.expected:
            numeric = case.expected["issue_date"].split("-")[::-1]  # dd, mm, yyyy
            assert "/".join(numeric) not in SYSTEM_PROMPT, case.id
            assert case.expected["invoice_number"] not in SYSTEM_PROMPT, case.id
            assert case.expected["supplier_name"] not in SYSTEM_PROMPT, case.id
