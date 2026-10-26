"""Guards the eval dataset itself, so a typo in a case cannot hide a regression."""

import re
from collections import Counter
from decimal import Decimal

import pytest

from evals.cases import CASES, CATEGORIES
from invoice_api.schemas.extraction import ExtractedInvoice
from invoice_api.services.extraction import FEW_SHOT_EXAMPLES, SYSTEM_PROMPT

NIF_SHAPED = re.compile(r"\b[A-Z]\d{8}\b|\b\d{8}[A-Z]\b")

EXTRACTION_CASES = [c for c in CASES if c.expected is not None]
REFUSAL_CASES = [c for c in CASES if c.expected is None]


def test_dataset_has_enough_cases():
    assert 10 <= len(CASES) <= 20
    assert len(EXTRACTION_CASES) >= 10
    assert len(REFUSAL_CASES) >= 1


def test_case_ids_are_unique():
    duplicates = [i for i, n in Counter(c.id for c in CASES).items() if n > 1]
    assert duplicates == []


@pytest.mark.parametrize("case", EXTRACTION_CASES, ids=lambda c: c.id)
def test_expected_values_are_a_valid_extraction(case):
    assert case.expected is not None

    invoice = ExtractedInvoice.model_validate(case.expected)  # also checks the totals

    assert invoice.base_amount + invoice.tax_amount == invoice.total_amount
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
            assert not NIF_SHAPED.search(case.text), case.id
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
