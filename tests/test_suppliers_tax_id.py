"""The tax id of a supplier, as handled by the /api/suppliers endpoints."""

import pytest

URL = "/api/suppliers"
NAME_TAKEN = "A supplier with this name already exists"
TAX_ID_TAKEN = "A supplier with this tax id already exists"


def create(client, headers, name="Acme S.L.", **extra):
    return client.post(URL, json={"name": name, **extra}, headers=headers)


# --- create -----------------------------------------------------------------


def test_create_without_tax_id_leaves_it_empty(client, headers_a):
    response = create(client, headers_a)

    assert response.status_code == 201
    assert response.json()["tax_id"] is None


def test_create_with_tax_id_stores_it_normalised(client, headers_a):
    response = create(client, headers_a, tax_id=" es-b12.345.678 ")

    assert response.status_code == 201
    assert response.json()["tax_id"] == "B12345678"
    (listed,) = client.get(URL, headers=headers_a).json()
    assert listed["tax_id"] == "B12345678"


def test_create_with_null_tax_id_is_the_same_as_omitting_it(client, headers_a):
    assert create(client, headers_a, tax_id=None).json()["tax_id"] is None


@pytest.mark.parametrize(
    "tax_id",
    [
        "",
        "   ",
        "N/A",
        "none",
        "B1",
        "ABCDEFGH",
        "B123456 78ñ",
        "a\x00b12345",
        "1" * 51,
        12345678,
        [],
    ],
    ids=lambda v: repr(v)[:20],
)
def test_create_rejects_an_invalid_tax_id(client, headers_a, tax_id):
    response = create(client, headers_a, tax_id=tax_id)

    assert response.status_code == 422
    assert client.get(URL, headers=headers_a).json() == []


def test_several_suppliers_may_have_no_tax_id(client, headers_a):
    assert create(client, headers_a, name="One").status_code == 201
    assert create(client, headers_a, name="Two").status_code == 201


def test_create_with_a_taken_tax_id_returns_409_with_its_own_message(client, headers_a):
    create(client, headers_a, tax_id="B12345678")

    response = create(client, headers_a, name="Other name", tax_id="B-12345678")

    assert response.status_code == 409
    assert response.json()["detail"] == TAX_ID_TAKEN
    assert len(client.get(URL, headers=headers_a).json()) == 1


def test_a_taken_name_still_returns_the_name_message(client, headers_a):
    create(client, headers_a, tax_id="B12345678")

    response = create(client, headers_a, tax_id="A98765432")

    assert response.status_code == 409
    assert response.json()["detail"] == NAME_TAKEN


def test_the_same_tax_id_is_allowed_for_different_users(client, headers_a, headers_b):
    assert create(client, headers_a, tax_id="B12345678").status_code == 201
    assert create(client, headers_b, tax_id="B12345678").status_code == 201


# --- update -----------------------------------------------------------------


def put(client, headers, supplier_id, **body):
    return client.put(f"{URL}/{supplier_id}", json=body, headers=headers)


def test_renaming_keeps_the_known_tax_id(client, headers_a):
    supplier = create(client, headers_a, tax_id="B12345678").json()

    response = put(client, headers_a, supplier["id"], name="Acme Renamed")

    assert response.status_code == 200
    assert response.json()["name"] == "Acme Renamed"
    assert response.json()["tax_id"] == "B12345678"


def test_update_sets_the_tax_id(client, headers_a):
    supplier = create(client, headers_a).json()

    response = put(client, headers_a, supplier["id"], name="Acme S.L.", tax_id="b 12345678")

    assert response.json()["tax_id"] == "B12345678"


def test_update_changes_a_wrong_tax_id(client, headers_a):
    supplier = create(client, headers_a, tax_id="B87654321").json()

    response = put(client, headers_a, supplier["id"], name="Acme S.L.", tax_id="B12345678")

    assert response.json()["tax_id"] == "B12345678"


def test_an_explicit_null_clears_the_tax_id(client, headers_a):
    supplier = create(client, headers_a, tax_id="B12345678").json()

    response = put(client, headers_a, supplier["id"], name="Acme S.L.", tax_id=None)

    assert response.status_code == 200
    assert response.json()["tax_id"] is None
    assert client.get(f"{URL}/{supplier['id']}", headers=headers_a).json()["tax_id"] is None


def test_update_rejects_an_invalid_tax_id_and_changes_nothing(client, headers_a):
    supplier = create(client, headers_a, tax_id="B12345678").json()

    response = put(client, headers_a, supplier["id"], name="Changed", tax_id="N/A")

    assert response.status_code == 422
    stored = client.get(f"{URL}/{supplier['id']}", headers=headers_a).json()
    assert (stored["name"], stored["tax_id"]) == ("Acme S.L.", "B12345678")


def test_update_to_a_taken_tax_id_returns_409_and_changes_nothing(client, headers_a):
    create(client, headers_a, name="First", tax_id="B12345678")
    second = create(client, headers_a, name="Second").json()

    response = put(client, headers_a, second["id"], name="Second", tax_id="B12345678")

    assert response.status_code == 409
    assert response.json()["detail"] == TAX_ID_TAKEN
    assert client.get(f"{URL}/{second['id']}", headers=headers_a).json()["tax_id"] is None


def test_update_to_its_own_tax_id_is_allowed(client, headers_a):
    supplier = create(client, headers_a, tax_id="B12345678").json()

    response = put(client, headers_a, supplier["id"], name="Acme S.L.", tax_id="B12345678")

    assert response.status_code == 200


def test_update_to_a_taken_name_still_returns_the_name_message(client, headers_a):
    create(client, headers_a, name="First")
    second = create(client, headers_a, name="Second").json()

    response = put(client, headers_a, second["id"], name="First")

    assert response.status_code == 409
    assert response.json()["detail"] == NAME_TAKEN


def test_another_users_tax_id_cannot_be_read_or_clashed_with(client, headers_a, headers_b):
    mine = create(client, headers_a, tax_id="B12345678").json()

    assert client.get(URL, headers=headers_b).json() == []
    assert client.get(f"{URL}/{mine['id']}", headers=headers_b).status_code == 404
    assert put(client, headers_b, mine["id"], name="x", tax_id=None).status_code == 404
    assert client.get(f"{URL}/{mine['id']}", headers=headers_a).json()["tax_id"] == "B12345678"
