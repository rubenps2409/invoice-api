"""Object-level authorization (OWASP API1): a user must never read, change or
even detect the existence of another user's data."""

import pytest

# --- the domain test, spelled out ------------------------------------------


def test_user_b_cannot_read_user_a_invoice(
    client, headers_a, headers_b, make_supplier, make_invoice
):
    supplier = make_supplier(headers_a)
    invoice = make_invoice(headers_a, supplier["id"])

    as_owner = client.get(f"/api/invoices/{invoice['id']}", headers=headers_a)
    as_other_user = client.get(f"/api/invoices/{invoice['id']}", headers=headers_b)

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
def item_of_a(resource, headers_a, make_category, make_supplier, make_invoice):
    if resource == "categories":
        return make_category(headers_a)
    supplier = make_supplier(headers_a)
    if resource == "suppliers":
        return supplier
    return make_invoice(headers_a, supplier["id"])


def test_other_user_cannot_read_item(client, resource, item_of_a, headers_b):
    response = client.get(f"/api/{resource}/{item_of_a['id']}", headers=headers_b)

    assert response.status_code == 404


def test_foreign_item_is_indistinguishable_from_a_missing_one(
    client, resource, item_of_a, headers_b
):
    foreign = client.get(f"/api/{resource}/{item_of_a['id']}", headers=headers_b)
    missing = client.get(f"/api/{resource}/999999", headers=headers_b)

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_other_user_cannot_update_item(
    client, resource, item_of_a, headers_a, headers_b
):
    method, body = UPDATE_REQUEST[resource]

    response = client.request(
        method, f"/api/{resource}/{item_of_a['id']}", json=body, headers=headers_b
    )

    assert response.status_code == 404
    untouched = client.get(f"/api/{resource}/{item_of_a['id']}", headers=headers_a)
    assert untouched.json() == item_of_a


def test_other_user_cannot_delete_item(
    client, resource, item_of_a, headers_a, headers_b
):
    response = client.delete(f"/api/{resource}/{item_of_a['id']}", headers=headers_b)

    assert response.status_code == 404
    still_there = client.get(f"/api/{resource}/{item_of_a['id']}", headers=headers_a)
    assert still_there.status_code == 200


def test_lists_only_contain_own_items(
    client, resource, item_of_a, headers_a, headers_b
):
    own = client.get(f"/api/{resource}", headers=headers_a).json()
    other = client.get(f"/api/{resource}", headers=headers_b).json()

    assert [item["id"] for item in own] == [item_of_a["id"]]
    assert other == []


@pytest.mark.parametrize("resource", ["categories", "suppliers"])
def test_foreign_item_does_not_collide_with_own_unique_values(
    client, resource, item_of_a, headers_b
):
    """B can reuse A's names and numbers: uniqueness is per user, so B's
    attempt must not reveal (409) that A already uses them."""
    response = client.post(
        f"/api/{resource}", json={"name": item_of_a["name"]}, headers=headers_b
    )

    assert response.status_code == 201


# --- filters must not leak across users ------------------------------------


def test_invoice_filters_do_not_reveal_other_users_data(
    client, headers_a, headers_b, make_supplier, make_category, make_invoice
):
    supplier = make_supplier(headers_a)
    category = make_category(headers_a)
    make_invoice(headers_a, supplier["id"], category_id=category["id"])

    by_supplier = client.get(
        f"/api/invoices?supplier_id={supplier['id']}", headers=headers_b
    )
    by_category = client.get(
        f"/api/invoices?category_id={category['id']}", headers=headers_b
    )
    by_status = client.get("/api/invoices?status=pending", headers=headers_b)

    assert by_supplier.json() == []
    assert by_category.json() == []
    assert by_status.json() == []


# --- identity ---------------------------------------------------------------


def test_each_token_resolves_to_its_own_user(client, headers_a, headers_b):
    me_a = client.get("/api/users/me", headers=headers_a).json()
    me_b = client.get("/api/users/me", headers=headers_b).json()

    assert me_a["email"] == "a@example.com"
    assert me_b["email"] == "b@example.com"
    assert me_a["id"] != me_b["id"]


def test_deleting_one_users_data_does_not_affect_the_other(
    client, headers_a, headers_b, make_supplier, make_invoice
):
    supplier_a = make_supplier(headers_a, name="Shared name")
    supplier_b = make_supplier(headers_b, name="Shared name")
    invoice_a = make_invoice(headers_a, supplier_a["id"])
    invoice_b = make_invoice(headers_b, supplier_b["id"])

    client.delete(f"/api/invoices/{invoice_a['id']}", headers=headers_a)
    client.delete(f"/api/suppliers/{supplier_a['id']}", headers=headers_a)

    remaining = client.get(f"/api/invoices/{invoice_b['id']}", headers=headers_b)
    assert remaining.status_code == 200
    assert client.get("/api/suppliers", headers=headers_b).json() == [supplier_b]
