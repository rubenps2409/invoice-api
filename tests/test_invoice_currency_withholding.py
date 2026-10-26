"""Currency and income-tax withholding on invoices, through the manual endpoints.

The rule is: total = base + tax - withholding, give or take one cent."""

import pytest

URL = "/api/invoices"


@pytest.fixture
async def supplier(headers_a, make_supplier):
    return await make_supplier(headers_a)


def payload(supplier, **overrides):
    data = {
        "number": "X-1",
        "supplier_id": supplier["id"],
        "base_amount": "1000.00",
        "tax_amount": "210.00",
        "withholding_amount": "150.00",
        "total_amount": "1060.00",
        "issue_date": "2026-03-15",
    }
    return {**data, **overrides}


# --- defaults and representation ---------------------------------------------


async def test_currency_defaults_to_eur_and_withholding_to_zero(
    client, headers_a, supplier, make_invoice
):
    created = await make_invoice(headers_a, supplier["id"])

    assert created["currency"] == "EUR"
    assert created["withholding_amount"] == "0.00"


async def test_amounts_always_show_two_decimals_and_a_post_equals_the_next_get(
    client, headers_a, supplier
):
    response = await client.post(
        URL,
        json=payload(
            supplier,
            base_amount="100",
            tax_amount="21.5",
            withholding_amount="0",
            total_amount="121.5",
        ),
        headers=headers_a,
    )

    body = response.json()
    assert (body["base_amount"], body["tax_amount"]) == ("100.00", "21.50")
    assert (body["withholding_amount"], body["total_amount"]) == ("0.00", "121.50")
    assert (await client.get(f"{URL}/{body['id']}", headers=headers_a)).json() == body


# --- create ------------------------------------------------------------------


async def test_create_with_a_withholding_subtracts_it_from_the_total(
    client, headers_a, supplier
):
    response = await client.post(URL, json=payload(supplier), headers=headers_a)

    assert response.status_code == 201
    body = response.json()
    assert body["withholding_amount"] == "150.00"
    assert body["total_amount"] == "1060.00"


async def test_create_rejects_a_total_that_ignores_the_withholding(
    client, headers_a, supplier
):
    # base + tax = 1210: right only if there were no withholding.
    response = await client.post(
        URL, json=payload(supplier, total_amount="1210.00"), headers=headers_a
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("total", "status_code"),
    [("1060.01", 201), ("1059.99", 201), ("1060.02", 422), ("1059.98", 422)],
)
async def test_the_total_may_be_one_cent_off_but_not_two(
    client, headers_a, supplier, total, status_code
):
    response = await client.post(
        URL, json=payload(supplier, total_amount=total), headers=headers_a
    )

    assert response.status_code == status_code


async def test_a_credit_note_has_a_negative_withholding_too(client, headers_a, supplier):
    credit_note = payload(
        supplier,
        base_amount="-1000.00",
        tax_amount="-210.00",
        withholding_amount="-150.00",
        total_amount="-1060.00",
    )

    response = await client.post(URL, json=credit_note, headers=headers_a)

    assert response.status_code == 201


@pytest.mark.parametrize("currency", ["USD", "usd", " gbp "])
async def test_create_accepts_other_currencies_and_normalises_them(
    client, headers_a, supplier, currency
):
    response = await client.post(
        URL, json=payload(supplier, currency=currency), headers=headers_a
    )

    assert response.status_code == 201
    assert response.json()["currency"] == currency.strip().upper()


@pytest.mark.parametrize("currency", ["", "EURO", "EU", "€", "E1R", 978, None, ["EUR"]])
async def test_create_rejects_an_invalid_currency(client, headers_a, supplier, currency):
    response = await client.post(
        URL, json=payload(supplier, currency=currency), headers=headers_a
    )

    assert response.status_code == 422


@pytest.mark.parametrize("value", ["1.005", "NaN", "abc", "100000000.00"])
async def test_create_rejects_an_invalid_withholding(client, headers_a, supplier, value):
    response = await client.post(
        URL, json=payload(supplier, withholding_amount=value), headers=headers_a
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "amounts",
    [
        # positive invoice, negative withholding (would absorb an extra amount)
        {
            "base_amount": "600.00",
            "tax_amount": "126.00",
            "withholding_amount": "-45.00",
            "total_amount": "771.00",
        },
        # credit note whose withholding kept its positive sign
        {
            "base_amount": "-500.00",
            "tax_amount": "-105.00",
            "withholding_amount": "75.00",
            "total_amount": "-680.00",
        },
        # negative base with a positive tax
        {
            "base_amount": "-100.00",
            "tax_amount": "21.00",
            "withholding_amount": "0.00",
            "total_amount": "-79.00",
        },
    ],
    ids=["negative-withholding", "credit-note-positive-withholding", "mixed-base-and-tax"],
)
async def test_amounts_with_opposite_signs_are_rejected(client, headers_a, supplier, amounts):
    response = await client.post(URL, json=payload(supplier, **amounts), headers=headers_a)

    assert response.status_code == 422
    assert "be positive or all negative" in response.text


async def test_zero_amounts_do_not_count_as_a_sign(client, headers_a, supplier):
    credit_note_without_tax = payload(
        supplier,
        base_amount="-100.00",
        tax_amount="0.00",
        withholding_amount="0.00",
        total_amount="-100.00",
    )

    assert (
        await client.post(URL, json=credit_note_without_tax, headers=headers_a)
    ).status_code == 201


async def test_patch_cannot_flip_the_withholding_against_the_stored_signs(
    client, headers_a, invoice_with_withholding
):
    url = f"{URL}/{invoice_with_withholding['id']}"

    response = await client.patch(
        url,
        json={"withholding_amount": "-150.00", "total_amount": "1360.00"},
        headers=headers_a,
    )

    assert response.status_code == 422
    assert (await client.get(url, headers=headers_a)).json() == invoice_with_withholding


# --- patch -------------------------------------------------------------------


@pytest.fixture
async def invoice_with_withholding(client, headers_a, supplier):
    return (await client.post(URL, json=payload(supplier), headers=headers_a)).json()


async def test_patch_changes_the_currency_only(client, headers_a, invoice_with_withholding):
    response = await client.patch(
        f"{URL}/{invoice_with_withholding['id']}", json={"currency": "usd"}, headers=headers_a
    )

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "USD"
    assert body["total_amount"] == invoice_with_withholding["total_amount"]


async def test_patch_rejects_a_null_or_invalid_currency(
    client, headers_a, invoice_with_withholding
):
    url = f"{URL}/{invoice_with_withholding['id']}"

    assert (
        await client.patch(url, json={"currency": None}, headers=headers_a)
    ).status_code == 422
    assert (
        await client.patch(url, json={"currency": "EURO"}, headers=headers_a)
    ).status_code == 422
    assert (await client.get(url, headers=headers_a)).json() == invoice_with_withholding


async def test_patch_the_withholding_alone_must_keep_the_totals_consistent(
    client, headers_a, invoice_with_withholding
):
    url = f"{URL}/{invoice_with_withholding['id']}"

    broken = await client.patch(url, json={"withholding_amount": "0.00"}, headers=headers_a)

    assert broken.status_code == 422
    assert (await client.get(url, headers=headers_a)).json() == invoice_with_withholding


async def test_patch_the_withholding_together_with_the_total(
    client, headers_a, invoice_with_withholding
):
    url = f"{URL}/{invoice_with_withholding['id']}"

    response = await client.patch(
        url, json={"withholding_amount": "0.00", "total_amount": "1210.00"}, headers=headers_a
    )

    assert response.status_code == 200
    assert response.json()["withholding_amount"] == "0.00"


async def test_patch_all_four_amounts_at_once_are_checked_together(
    client, headers_a, invoice_with_withholding
):
    url = f"{URL}/{invoice_with_withholding['id']}"
    amounts = {
        "base_amount": "200.00",
        "tax_amount": "42.00",
        "withholding_amount": "30.00",
        "total_amount": "212.00",
    }

    inconsistent = await client.patch(
        url, json={**amounts, "total_amount": "242.00"}, headers=headers_a
    )
    consistent = await client.patch(url, json=amounts, headers=headers_a)

    assert inconsistent.status_code == 422
    assert consistent.status_code == 200
    assert consistent.json()["total_amount"] == "212.00"


async def test_patch_the_base_is_checked_against_the_stored_withholding(
    client, headers_a, invoice_with_withholding
):
    url = f"{URL}/{invoice_with_withholding['id']}"

    # base + tax - 150 would no longer be 1060.
    response = await client.patch(url, json={"base_amount": "1100.00"}, headers=headers_a)

    assert response.status_code == 422


async def test_patch_rejects_a_null_withholding(client, headers_a, invoice_with_withholding):
    url = f"{URL}/{invoice_with_withholding['id']}"

    assert (
        await client.patch(url, json={"withholding_amount": None}, headers=headers_a)
    ).status_code == 422
