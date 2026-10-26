"""Object-level authorization (OWASP API1): a user must never read, change or
even detect the existence of another user's data."""

import pytest

# --- the domain test, spelled out ------------------------------------------


async def test_user_b_cannot_read_user_a_invoice(
    client, headers_a, headers_b, make_supplier, make_invoice
):
    supplier = await make_supplier(headers_a)
    invoice = await make_invoice(headers_a, supplier["id"])

    as_owner = await client.get(f"/api/invoices/{invoice['id']}", headers=headers_a)
    as_other_user = await client.get(f"/api/invoices/{invoice['id']}", headers=headers_b)

    assert as_owner.status_code == 200
    assert as_other_user.status_code == 404


# --- the same guarantees for every resource --------------------------------

UPDATE_REQUEST = {
    "categories": ("put", {"name": "Hacked"}),
    "suppliers": ("put", {"name": "Hacked"}),
    "invoices": ("patch", {"status": "paid"}),
}


@pytest.fixture(params=["categories", "suppliers", "invoices"])
def resource(request):
    return request.param


@pytest.fixture
async def item_of_a(resource, headers_a, make_category, make_supplier, make_invoice):
    if resource == "categories":
        return await make_category(headers_a)
    supplier = await make_supplier(headers_a)
    if resource == "suppliers":
        return supplier
    return await make_invoice(headers_a, supplier["id"])


async def test_other_user_cannot_read_item(client, resource, item_of_a, headers_b):
    response = await client.get(f"/api/{resource}/{item_of_a['id']}", headers=headers_b)

    assert response.status_code == 404


async def test_foreign_item_is_indistinguishable_from_a_missing_one(
    client, resource, item_of_a, headers_b
):
    foreign = await client.get(f"/api/{resource}/{item_of_a['id']}", headers=headers_b)
    missing = await client.get(f"/api/{resource}/999999", headers=headers_b)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


async def test_other_user_cannot_update_item(
    client, resource, item_of_a, headers_a, headers_b
):
    method, body = UPDATE_REQUEST[resource]

    response = await client.request(
        method, f"/api/{resource}/{item_of_a['id']}", json=body, headers=headers_b
    )

    assert response.status_code == 404
    untouched = await client.get(f"/api/{resource}/{item_of_a['id']}", headers=headers_a)
    assert untouched.json() == item_of_a


async def test_other_user_cannot_delete_item(
    client, resource, item_of_a, headers_a, headers_b
):
    response = await client.delete(f"/api/{resource}/{item_of_a['id']}", headers=headers_b)

    assert response.status_code == 404
    still_there = await client.get(f"/api/{resource}/{item_of_a['id']}", headers=headers_a)
    assert still_there.status_code == 200


async def test_lists_only_contain_own_items(client, resource, item_of_a, headers_a, headers_b):
    own = (await client.get(f"/api/{resource}", headers=headers_a)).json()
    other = (await client.get(f"/api/{resource}", headers=headers_b)).json()

    assert [item["id"] for item in own] == [item_of_a["id"]]
    assert other == []


@pytest.mark.parametrize("resource", ["categories", "suppliers"])
async def test_foreign_item_does_not_collide_with_own_unique_values(
    client, resource, item_of_a, headers_b
):
    """B can reuse A's names and numbers: uniqueness is per user, so B's
    attempt must not reveal (409) that A already uses them."""
    response = await client.post(
        f"/api/{resource}", json={"name": item_of_a["name"]}, headers=headers_b
    )

    assert response.status_code == 201


# --- filters must not leak across users ------------------------------------


async def test_invoice_filters_do_not_reveal_other_users_data(
    client, headers_a, headers_b, make_supplier, make_category, make_invoice
):
    supplier = await make_supplier(headers_a)
    category = await make_category(headers_a)
    await make_invoice(headers_a, supplier["id"], category_id=category["id"])

    by_supplier = await client.get(
        f"/api/invoices?supplier_id={supplier['id']}", headers=headers_b
    )
    by_category = await client.get(
        f"/api/invoices?category_id={category['id']}", headers=headers_b
    )
    by_status = await client.get("/api/invoices?status=pending", headers=headers_b)

    assert by_supplier.json() == []
    assert by_category.json() == []
    assert by_status.json() == []


# --- identity ---------------------------------------------------------------


async def test_each_token_resolves_to_its_own_user(client, headers_a, headers_b):
    me_a = (await client.get("/api/users/me", headers=headers_a)).json()
    me_b = (await client.get("/api/users/me", headers=headers_b)).json()

    assert me_a["email"] == "a@example.com"
    assert me_b["email"] == "b@example.com"
    assert me_a["id"] != me_b["id"]


async def test_deleting_one_users_data_does_not_affect_the_other(
    client, headers_a, headers_b, make_supplier, make_invoice
):
    supplier_a = await make_supplier(headers_a, name="Shared name")
    supplier_b = await make_supplier(headers_b, name="Shared name")
    invoice_a = await make_invoice(headers_a, supplier_a["id"])
    invoice_b = await make_invoice(headers_b, supplier_b["id"])

    await client.delete(f"/api/invoices/{invoice_a['id']}", headers=headers_a)
    await client.delete(f"/api/suppliers/{supplier_a['id']}", headers=headers_a)

    remaining = await client.get(f"/api/invoices/{invoice_b['id']}", headers=headers_b)
    assert remaining.status_code == 200
    assert (await client.get("/api/suppliers", headers=headers_b)).json() == [supplier_b]
