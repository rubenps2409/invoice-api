import pytest

URL = "/api/invoices"


@pytest.fixture
async def supplier(headers_a, make_supplier):
    return await make_supplier(headers_a)


# --- create -----------------------------------------------------------------


async def test_create_returns_201_with_defaults(client, headers_a, supplier, make_invoice):
    invoice = await make_invoice(headers_a, supplier["id"])

    assert invoice["number"] == "INV-2026-0001"
    assert invoice["supplier_id"] == supplier["id"]
    assert invoice["category_id"] is None
    assert invoice["status"] == "pending"
    assert invoice["base_amount"] == "100.00"
    assert invoice["total_amount"] == "121.00"
    assert invoice["issue_date"] == "2026-03-15"
    assert invoice["created_at"]
    assert "user_id" not in invoice


async def test_create_with_category(headers_a, supplier, make_category, make_invoice):
    category = await make_category(headers_a)

    invoice = await make_invoice(headers_a, supplier["id"], category_id=category["id"])

    assert invoice["category_id"] == category["id"]


async def test_requires_authentication(client):
    assert (await client.get(URL)).status_code == 401
    assert (await client.post(URL, json={})).status_code == 401


async def test_create_rejects_totals_that_do_not_add_up(client, headers_a, supplier):
    payload = {
        "number": "X-1",
        "supplier_id": supplier["id"],
        "base_amount": "100.00",
        "tax_amount": "21.00",
        "total_amount": "999.00",
        "issue_date": "2026-03-15",
    }

    response = await client.post(URL, json=payload, headers=headers_a)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "overrides",
    [
        {"number": ""},
        {"number": "x" * 101},
        {"supplier_id": 0},
        {"status": "unknown"},
        {"issue_date": "2026-13-45"},
        {"issue_date": "not-a-date"},
        {"user_id": 99},
        {"base_amount": "100.001", "total_amount": "121.001"},
        {"base_amount": "NaN", "total_amount": "NaN"},
        {"base_amount": "abc"},
    ],
    ids=[
        "empty-number",
        "number-too-long",
        "supplier-id-zero",
        "invalid-status",
        "impossible-date",
        "text-date",
        "extra-field",
        "three-decimals",
        "nan",
        "text-amount",
    ],
)
async def test_create_rejects_invalid_values(client, headers_a, supplier, overrides):
    payload = {
        "number": "X-1",
        "supplier_id": supplier["id"],
        "base_amount": "100.00",
        "tax_amount": "21.00",
        "total_amount": "121.00",
        "issue_date": "2026-03-15",
    }
    payload.update(overrides)

    response = await client.post(URL, json=payload, headers=headers_a)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "missing",
    [
        "number",
        "supplier_id",
        "base_amount",
        "tax_amount",
        "total_amount",
        "issue_date",
    ],
)
async def test_create_requires_mandatory_fields(client, headers_a, supplier, missing):
    payload = {
        "number": "X-1",
        "supplier_id": supplier["id"],
        "base_amount": "100.00",
        "tax_amount": "21.00",
        "total_amount": "121.00",
        "issue_date": "2026-03-15",
    }
    del payload[missing]

    response = await client.post(URL, json=payload, headers=headers_a)

    assert response.status_code == 422


async def test_create_accepts_largest_amount(headers_a, supplier, make_invoice):
    invoice = await make_invoice(
        headers_a,
        supplier["id"],
        base_amount="99999999.99",
        tax_amount="0.00",
        total_amount="99999999.99",
    )

    assert invoice["total_amount"] == "99999999.99"


async def test_create_rejects_amount_beyond_column_precision(client, headers_a, supplier):
    payload = {
        "number": "X-1",
        "supplier_id": supplier["id"],
        "base_amount": "100000000.00",
        "tax_amount": "0.00",
        "total_amount": "100000000.00",
        "issue_date": "2026-03-15",
    }

    response = await client.post(URL, json=payload, headers=headers_a)

    assert response.status_code == 422


async def test_create_accepts_negative_amounts_for_credit_notes(
    headers_a, supplier, make_invoice
):
    invoice = await make_invoice(
        headers_a,
        supplier["id"],
        base_amount="-100.00",
        tax_amount="-21.00",
        total_amount="-121.00",
    )

    assert invoice["total_amount"] == "-121.00"


async def test_create_duplicate_number_for_same_supplier_returns_409(
    client, headers_a, supplier, make_invoice
):
    await make_invoice(headers_a, supplier["id"], number="DUP-1")
    payload = {
        "number": "DUP-1",
        "supplier_id": supplier["id"],
        "base_amount": "1.00",
        "tax_amount": "0.00",
        "total_amount": "1.00",
        "issue_date": "2026-03-15",
    }

    response = await client.post(URL, json=payload, headers=headers_a)

    assert response.status_code == 409


async def test_same_number_is_allowed_for_different_suppliers(
    headers_a, make_supplier, make_invoice
):
    first = await make_supplier(headers_a, name="First")
    second = await make_supplier(headers_a, name="Second")

    await make_invoice(headers_a, first["id"], number="SAME-1")
    other = await make_invoice(headers_a, second["id"], number="SAME-1")

    assert other["number"] == "SAME-1"


async def test_same_number_and_supplier_name_is_allowed_for_different_users(
    headers_a, headers_b, make_supplier, make_invoice
):
    supplier_a = await make_supplier(headers_a)
    supplier_b = await make_supplier(headers_b)

    await make_invoice(headers_a, supplier_a["id"], number="SAME-1")
    other = await make_invoice(headers_b, supplier_b["id"], number="SAME-1")

    assert other["number"] == "SAME-1"


@pytest.mark.parametrize("field", ["supplier_id", "category_id"])
async def test_create_with_nonexistent_reference_returns_422(
    client, headers_a, supplier, field
):
    payload = {
        "number": "X-1",
        "supplier_id": supplier["id"],
        "base_amount": "100.00",
        "tax_amount": "21.00",
        "total_amount": "121.00",
        "issue_date": "2026-03-15",
    }
    payload[field] = 999999

    response = await client.post(URL, json=payload, headers=headers_a)

    assert response.status_code == 422


async def test_create_with_another_users_supplier_returns_422(
    client, headers_a, headers_b, make_supplier
):
    foreign_supplier = await make_supplier(headers_b)
    payload = {
        "number": "X-1",
        "supplier_id": foreign_supplier["id"],
        "base_amount": "100.00",
        "tax_amount": "21.00",
        "total_amount": "121.00",
        "issue_date": "2026-03-15",
    }

    response = await client.post(URL, json=payload, headers=headers_a)

    assert response.status_code == 422


async def test_create_with_another_users_category_returns_422(
    client, headers_a, headers_b, supplier, make_category
):
    foreign_category = await make_category(headers_b)
    payload = {
        "number": "X-1",
        "supplier_id": supplier["id"],
        "category_id": foreign_category["id"],
        "base_amount": "100.00",
        "tax_amount": "21.00",
        "total_amount": "121.00",
        "issue_date": "2026-03-15",
    }

    response = await client.post(URL, json=payload, headers=headers_a)

    assert response.status_code == 422


# --- read -------------------------------------------------------------------


async def test_get_returns_invoice(client, headers_a, supplier, make_invoice):
    created = await make_invoice(headers_a, supplier["id"])

    response = await client.get(f"{URL}/{created['id']}", headers=headers_a)

    assert response.status_code == 200
    assert response.json() == created


async def test_get_missing_returns_404(client, headers_a):
    assert (await client.get(f"{URL}/999999", headers=headers_a)).status_code == 404


@pytest.mark.parametrize("invoice_id", ["0", "-1", "abc", "2147483648"])
async def test_invalid_id_returns_422(client, headers_a, invoice_id):
    url = f"{URL}/{invoice_id}"

    assert (await client.get(url, headers=headers_a)).status_code == 422
    assert (
        await client.patch(url, json={"status": "paid"}, headers=headers_a)
    ).status_code == 422
    assert (await client.delete(url, headers=headers_a)).status_code == 422


# --- list -------------------------------------------------------------------


@pytest.fixture
async def three_invoices(headers_a, make_supplier, make_category, make_invoice):
    """Two suppliers, one category, three invoices on different dates/statuses."""
    s1 = await make_supplier(headers_a, name="S1")
    s2 = await make_supplier(headers_a, name="S2")
    cat = await make_category(headers_a)
    old = await make_invoice(headers_a, s1["id"], number="OLD", issue_date="2026-01-10")
    mid = await make_invoice(
        headers_a,
        s1["id"],
        number="MID",
        issue_date="2026-02-10",
        status="paid",
        category_id=cat["id"],
    )
    new = await make_invoice(
        headers_a, s2["id"], number="NEW", issue_date="2026-03-10", status="cancelled"
    )
    return {"s1": s1, "s2": s2, "cat": cat, "old": old, "mid": mid, "new": new}


def _numbers(response):
    assert response.status_code == 200, response.text
    return [invoice["number"] for invoice in response.json()]


async def test_list_is_ordered_by_date_descending(client, headers_a, three_invoices):
    assert _numbers(await client.get(URL, headers=headers_a)) == ["NEW", "MID", "OLD"]


async def test_list_orders_same_date_by_id_descending(
    client, headers_a, supplier, make_invoice
):
    await make_invoice(headers_a, supplier["id"], number="A", issue_date="2026-05-01")
    await make_invoice(headers_a, supplier["id"], number="B", issue_date="2026-05-01")

    assert _numbers(await client.get(URL, headers=headers_a)) == ["B", "A"]


async def test_list_empty_returns_empty_list(client, headers_a):
    response = await client.get(URL, headers=headers_a)

    assert response.status_code == 200
    assert response.json() == []


async def test_list_filter_by_status(client, headers_a, three_invoices):
    assert _numbers(await client.get(f"{URL}?status=paid", headers=headers_a)) == ["MID"]


async def test_list_filter_by_supplier(client, headers_a, three_invoices):
    sid = three_invoices["s1"]["id"]

    assert _numbers(await client.get(f"{URL}?supplier_id={sid}", headers=headers_a)) == [
        "MID",
        "OLD",
    ]


async def test_list_filter_by_category(client, headers_a, three_invoices):
    cid = three_invoices["cat"]["id"]

    assert _numbers(await client.get(f"{URL}?category_id={cid}", headers=headers_a)) == ["MID"]


async def test_list_date_range_is_inclusive(client, headers_a, three_invoices):
    response = await client.get(
        f"{URL}?date_from=2026-01-10&date_to=2026-02-10", headers=headers_a
    )

    assert _numbers(response) == ["MID", "OLD"]


async def test_list_filters_combine(client, headers_a, three_invoices):
    sid = three_invoices["s1"]["id"]

    response = await client.get(
        f"{URL}?supplier_id={sid}&status=pending&date_from=2026-01-01",
        headers=headers_a,
    )

    assert _numbers(response) == ["OLD"]


async def test_list_with_date_from_after_date_to_returns_422(client, headers_a):
    response = await client.get(
        f"{URL}?date_from=2026-05-01&date_to=2026-01-01", headers=headers_a
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        "status=unknown",
        "date_from=not-a-date",
        "supplier_id=0",
        "supplier_id=abc",
        "category_id=2147483648",
        "skip=-1",
        "limit=0",
        "limit=101",
    ],
)
async def test_list_rejects_invalid_query(client, headers_a, query):
    assert (await client.get(f"{URL}?{query}", headers=headers_a)).status_code == 422


async def test_list_filter_for_unknown_supplier_returns_empty(client, headers_a):
    response = await client.get(f"{URL}?supplier_id=999999", headers=headers_a)

    assert response.status_code == 200
    assert response.json() == []


async def test_list_pagination_is_stable(client, headers_a, three_invoices):
    page1 = _numbers(await client.get(f"{URL}?skip=0&limit=2", headers=headers_a))
    page2 = _numbers(await client.get(f"{URL}?skip=2&limit=2", headers=headers_a))
    beyond = _numbers(await client.get(f"{URL}?skip=50", headers=headers_a))

    assert page1 == ["NEW", "MID"]
    assert page2 == ["OLD"]
    assert beyond == []


# --- update (PATCH) ---------------------------------------------------------


async def test_patch_updates_only_sent_fields(client, headers_a, supplier, make_invoice):
    created = await make_invoice(headers_a, supplier["id"])

    response = await client.patch(
        f"{URL}/{created['id']}", json={"status": "paid"}, headers=headers_a
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "paid"
    assert {k: v for k, v in body.items() if k != "status"} == {
        k: v for k, v in created.items() if k != "status"
    }


async def test_patch_persists(client, headers_a, supplier, make_invoice):
    created = await make_invoice(headers_a, supplier["id"])
    await client.patch(f"{URL}/{created['id']}", json={"number": "NEW-1"}, headers=headers_a)

    stored = (await client.get(f"{URL}/{created['id']}", headers=headers_a)).json()

    assert stored["number"] == "NEW-1"


async def test_patch_all_amounts_consistently(client, headers_a, supplier, make_invoice):
    created = await make_invoice(headers_a, supplier["id"])
    amounts = {"base_amount": "200.00", "tax_amount": "42.00", "total_amount": "242.00"}

    response = await client.patch(f"{URL}/{created['id']}", json=amounts, headers=headers_a)

    assert response.status_code == 200
    assert response.json()["total_amount"] == "242.00"


@pytest.mark.parametrize(
    "changes",
    [
        {"total_amount": "999.00"},
        {"base_amount": "50.00"},
        {"tax_amount": "1.00"},
        {"base_amount": "200.00", "tax_amount": "42.00"},
        {"base_amount": "200.00", "tax_amount": "42.00", "total_amount": "1.00"},
    ],
    ids=[
        "only-total",
        "only-base",
        "only-tax",
        "base-and-tax-without-total",
        "all-three-inconsistent",
    ],
)
async def test_patch_rejects_amounts_that_break_the_total(
    client, headers_a, supplier, make_invoice, changes
):
    created = await make_invoice(headers_a, supplier["id"])

    response = await client.patch(f"{URL}/{created['id']}", json=changes, headers=headers_a)

    assert response.status_code == 422
    unchanged = (await client.get(f"{URL}/{created['id']}", headers=headers_a)).json()
    assert unchanged == created


async def test_patch_null_clears_category(
    client, headers_a, supplier, make_category, make_invoice
):
    category = await make_category(headers_a)
    created = await make_invoice(headers_a, supplier["id"], category_id=category["id"])

    response = await client.patch(
        f"{URL}/{created['id']}", json={"category_id": None}, headers=headers_a
    )

    assert response.status_code == 200
    assert response.json()["category_id"] is None


@pytest.mark.parametrize(
    "field",
    [
        "number",
        "supplier_id",
        "base_amount",
        "tax_amount",
        "total_amount",
        "issue_date",
        "status",
    ],
)
async def test_patch_rejects_null_for_required_fields(
    client, headers_a, supplier, make_invoice, field
):
    created = await make_invoice(headers_a, supplier["id"])

    response = await client.patch(
        f"{URL}/{created['id']}", json={field: None}, headers=headers_a
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "payload",
    [{}, {"unknown": 1}, {"user_id": 5}, {"status": "unknown"}, {"issue_date": "x"}],
    ids=["empty-body", "unknown-field", "user-id", "invalid-status", "invalid-date"],
)
async def test_patch_rejects_invalid_payload(
    client, headers_a, supplier, make_invoice, payload
):
    created = await make_invoice(headers_a, supplier["id"])

    response = await client.patch(f"{URL}/{created['id']}", json=payload, headers=headers_a)

    assert response.status_code == 422


async def test_patch_to_duplicate_number_returns_409(
    client, headers_a, supplier, make_invoice
):
    await make_invoice(headers_a, supplier["id"], number="ONE")
    other = await make_invoice(headers_a, supplier["id"], number="TWO")

    response = await client.patch(
        f"{URL}/{other['id']}", json={"number": "ONE"}, headers=headers_a
    )

    assert response.status_code == 409


async def test_patch_number_to_its_own_value_is_allowed(
    client, headers_a, supplier, make_invoice
):
    created = await make_invoice(headers_a, supplier["id"], number="ONE")

    response = await client.patch(
        f"{URL}/{created['id']}", json={"number": "ONE"}, headers=headers_a
    )

    assert response.status_code == 200


async def test_patch_moving_to_another_supplier_that_has_same_number_returns_409(
    client, headers_a, make_supplier, make_invoice
):
    first = await make_supplier(headers_a, name="First")
    second = await make_supplier(headers_a, name="Second")
    await make_invoice(headers_a, first["id"], number="SAME")
    moving = await make_invoice(headers_a, second["id"], number="SAME")

    response = await client.patch(
        f"{URL}/{moving['id']}", json={"supplier_id": first["id"]}, headers=headers_a
    )

    assert response.status_code == 409


@pytest.mark.parametrize("field", ["supplier_id", "category_id"])
async def test_patch_with_nonexistent_reference_returns_422(
    client, headers_a, supplier, make_invoice, field
):
    created = await make_invoice(headers_a, supplier["id"])

    response = await client.patch(
        f"{URL}/{created['id']}", json={field: 999999}, headers=headers_a
    )

    assert response.status_code == 422


async def test_patch_with_another_users_supplier_returns_422(
    client, headers_a, headers_b, supplier, make_supplier, make_invoice
):
    created = await make_invoice(headers_a, supplier["id"])
    foreign_supplier = await make_supplier(headers_b)

    response = await client.patch(
        f"{URL}/{created['id']}",
        json={"supplier_id": foreign_supplier["id"]},
        headers=headers_a,
    )

    assert response.status_code == 422


async def test_patch_missing_returns_404(client, headers_a):
    response = await client.patch(f"{URL}/999999", json={"status": "paid"}, headers=headers_a)

    assert response.status_code == 404


# --- delete -----------------------------------------------------------------


async def test_delete_removes_invoice(client, headers_a, supplier, make_invoice):
    created = await make_invoice(headers_a, supplier["id"])

    response = await client.delete(f"{URL}/{created['id']}", headers=headers_a)

    assert response.status_code == 204
    assert (await client.get(f"{URL}/{created['id']}", headers=headers_a)).status_code == 404


async def test_delete_missing_or_twice_returns_404(client, headers_a, supplier, make_invoice):
    created = await make_invoice(headers_a, supplier["id"])
    await client.delete(f"{URL}/{created['id']}", headers=headers_a)

    assert (
        await client.delete(f"{URL}/{created['id']}", headers=headers_a)
    ).status_code == 404
    assert (await client.delete(f"{URL}/999999", headers=headers_a)).status_code == 404


async def test_supplier_can_be_deleted_once_its_invoices_are_gone(
    client, headers_a, supplier, make_invoice
):
    created = await make_invoice(headers_a, supplier["id"])
    blocked = await client.delete(f"/api/suppliers/{supplier['id']}", headers=headers_a)
    await client.delete(f"{URL}/{created['id']}", headers=headers_a)

    allowed = await client.delete(f"/api/suppliers/{supplier['id']}", headers=headers_a)

    assert blocked.status_code == 409
    assert allowed.status_code == 204
