import pytest

from invoice_api.normalization import normalize_tax_id, supplier_name_key

# --- tax ids ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("B12345678", "B12345678"),
        ("b12345678", "B12345678"),
        ("B-12345678", "B12345678"),
        ("B 12.345.678", "B12345678"),
        ("  B12345678  ", "B12345678"),
        ("ESB12345678", "B12345678"),
        ("ES-B12345678", "B12345678"),
        ("es b65.432.109", "B65432109"),
        ("12345678Z", "12345678Z"),
        ("DE123456789", "DE123456789"),
        ("FR12 345678901", "FR12345678901"),
    ],
)
def test_tax_ids_are_reduced_to_a_canonical_form(raw, expected):
    assert normalize_tax_id(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "   ",
        "N/A",
        "none",
        "unknown",
        "B1",
        "12",
        "ABCDEFGH",
        "B123 45678 ñ",
        "1" * 21,
    ],
)
def test_values_that_are_not_tax_ids_become_none(raw):
    assert normalize_tax_id(raw) is None


def test_normalising_twice_changes_nothing():
    once = normalize_tax_id("ES-B65.432.109")

    assert normalize_tax_id(once) == once


def test_a_foreign_vat_number_starting_with_es_is_not_truncated():
    # Only the 11-character "ES" + NIF form is a Spanish VAT number.
    assert normalize_tax_id("ES1234") == "ES1234"
    assert normalize_tax_id("ES123456789012") == "ES123456789012"


# --- supplier names ---------------------------------------------------------


@pytest.mark.parametrize(
    "other",
    [
        "ACME S.L.",
        "Acme, S.L.",
        "ACME, S.L.",
        "acme sl",
        "  Acme   S.L.  ",
        "Acme",
        "Acmé S.L.",
        "Acme S.L.U.",
    ],
)
def test_spellings_of_the_same_company_share_a_key(other):
    assert supplier_name_key(other) == supplier_name_key("Acme S.L.")


@pytest.mark.parametrize(
    "other",
    ["Acme Soluciones S.L.", "Acmes S.L.", "Sacme", "Acme Norte"],
)
def test_different_companies_do_not_share_a_key(other):
    assert supplier_name_key(other) != supplier_name_key("Acme S.L.")


def test_a_legal_form_is_only_dropped_at_the_end():
    assert supplier_name_key("Sa Nostra Viatges") == "sa nostra viatges"
    assert supplier_name_key("S.L. Acme") == "sl acme"


def test_a_name_that_is_only_a_legal_form_keeps_a_usable_key():
    assert supplier_name_key("S.L.") == "sl"
    assert supplier_name_key("...") == "..."


def test_accents_are_ignored():
    assert supplier_name_key("Papelería El Cuaderno") == supplier_name_key(
        "PAPELERIA EL CUADERNO"
    )
