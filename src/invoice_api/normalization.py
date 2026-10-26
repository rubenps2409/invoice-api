"""Normalisation used to recognise the same supplier written in different ways."""

import re
import unicodedata

_TAX_ID_SEPARATORS = re.compile(r"[\s.\-/]")
# 5-20 letters/digits with at least one digit: rejects "N/A", "none", "unknown".
_TAX_ID = re.compile(r"(?=.*\d)[A-Z0-9]{5,20}")
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
