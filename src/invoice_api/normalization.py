"""Normalisation of tax ids and supplier names (to recognise the same supplier
written in different ways) and reading of the amounts printed in an invoice."""

import re
import unicodedata
from decimal import Decimal

from invoice_api.models.supplier import SUPPLIER_TAX_ID_MAX_LENGTH

_TAX_ID_MIN_LENGTH = 5
_TAX_ID_SEPARATORS = re.compile(r"[\s.\-/]")
# Letters/digits with at least one digit: rejects "N/A", "none", "unknown".
_TAX_ID = re.compile(rf"(?=.*\d)[A-Z0-9]{{{_TAX_ID_MIN_LENGTH},{SUPPLIER_TAX_ID_MAX_LENGTH}}}")
_PUNCTUATION = re.compile(r"[^\w\s]")

# Legal forms. They are only dropped from the END of a name, so a name that
# merely starts with one ("Sa Nostra") keeps it.
_LEGAL_SUFFIXES = frozenset(
    {
        "sl",
        "sa",
        "slu",
        "sau",
        "sll",
        "sc",
        "scp",
        "cb",
        "ltd",
        "llc",
        "inc",
        "corp",
        "gmbh",
        "bv",
    }
)


def normalize_tax_id(value: str | None) -> str | None:
    """Canonical form of a NIF/CIF/VAT number, or None if it does not look like one.

    "ES-B65.432.109" and "b 65432109" both become "B65432109".
    """
    if value is None:
        return None
    cleaned = _TAX_ID_SEPARATORS.sub("", value).upper()
    # Spanish VAT numbers carry an "ES" prefix over the 9-character NIF.
    if len(cleaned) == 11 and cleaned.startswith("ES"):
        cleaned = cleaned[2:]
    return cleaned if _TAX_ID.fullmatch(cleaned) else None


def supplier_name_key(name: str) -> str:
    """Comparison key: "ACME, S.L." and "Acme S.L." give the same key.

    Ignores case, accents, punctuation and a trailing legal form.
    """
    folded = unicodedata.normalize("NFKD", name.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    # Dots go first so initials stay together ("s.l." -> "sl").
    words = _PUNCTUATION.sub(" ", folded.replace(".", "")).split()
    while len(words) > 1 and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    # A name made only of punctuation still needs a usable key.
    return " ".join(words) or name.casefold().strip()


# A number as printed: digits with "." "," or "'" between them ("1.512,50",
# "1,512.50", "1'512.50"); or groups of three separated by a space ("1 512,50").
_NUMBER = re.compile(r"\d(?:[\d.,'’]*\d)?")
_SPACE_GROUPED_NUMBER = re.compile(r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d{1,2})?")
_CENT = Decimal("0.01")


def _number_values(token: str) -> set[Decimal]:
    """Every value a printed number can mean (the separator may be ambiguous)."""
    token = token.replace("'", "").replace("’", "")
    separators = [token.rfind("."), token.rfind(",")]
    last = max(separators)
    if last < 0:
        return {Decimal(token)}

    before, after = token[:last], token[last + 1 :]
    digits_before = re.sub(r"[.,]", "", before)
    as_decimal = Decimal(f"{digits_before}.{after}")  # the last separator is the point
    as_thousands = Decimal(f"{digits_before}{after}")  # ... or it only groups digits

    mixed = "." in token and "," in token
    repeated = token.count(token[last]) > 1
    if mixed:
        return {as_decimal}
    if repeated:
        return {as_thousands}
    return {as_decimal, as_thousands} if len(after) == 3 else {as_decimal}


def printed_amounts(text: str) -> set[Decimal]:
    """The numbers in an invoice text, as 2-decimal values.

    Used to check that an amount returned by the model is really printed there
    and was not worked out by the model.
    """
    tokens = _NUMBER.findall(text) + _SPACE_GROUPED_NUMBER.findall(text)
    amounts: set[Decimal] = set()
    for token in tokens:
        cleaned = re.sub(r"[   ]", "", token)
        amounts |= {value.quantize(_CENT) for value in _number_values(cleaned)}
    return amounts
