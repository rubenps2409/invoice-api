"""Categories and suppliers share the same CRUD behaviour, so every test here
runs twice: once per resource."""

import pytest


@pytest.fixture(params=["categories", "suppliers"])
def resource(request):
    return request.param


@pytest.fixture
def make(resource, make_category, make_supplier):
    return {"categories": make_category, "suppliers": make_supplier}[resource]


@pytest.fixture
def make_in_use(resource, make_supplier, make_invoice):
    """Create an invoice that references the given category or supplier."""

    async def _use(headers, obj):
        if resource == "suppliers":
            await make_invoice(headers, obj["id"])
        else:
            supplier = await make_supplier(headers)
            await make_invoice(headers, supplier["id"], category_id=obj["id"])

    return _use


async def test_requires_authentication(client, resource):
    assert (await client.get(f"/api/{resource}")).status_code == 401
    assert (await client.post(f"/api/{resource}", json={"name": "X"})).status_code == 401


async def test_create_returns_201(client, resource, headers_a):
    response = await client.post(f"/api/{resource}", json={"name": "Alpha"}, headers=headers_a)

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Alpha"
    assert isinstance(body["id"], int)
    assert "user_id" not in body


@pytest.mark.parametrize(
    "payload",
    [{}, {"name": ""}, {"name": "x" * 256}, {"name": "Alpha", "user_id": 99}],
    ids=["missing-name", "empty-name", "name-too-long", "extra-field"],
)
async def test_create_rejects_invalid_payload(client, resource, headers_a, payload):
    response = await client.post(f"/api/{resource}", json=payload, headers=headers_a)

    assert response.status_code == 422


async def test_create_duplicate_name_returns_409(client, resource, headers_a, make):
    await make(headers_a, name="Alpha")

    response = await client.post(f"/api/{resource}", json={"name": "Alpha"}, headers=headers_a)

    assert response.status_code == 409


async def test_same_name_is_allowed_for_different_users(
    client, resource, headers_a, headers_b, make
):
    await make(headers_a, name="Alpha")

    response = await client.post(f"/api/{resource}", json={"name": "Alpha"}, headers=headers_b)

    assert response.status_code == 201


async def test_list_returns_items_in_creation_order(client, resource, headers_a, make):
    names = ["Alpha", "Bravo", "Charlie"]
    for name in names:
        await make(headers_a, name=name)

    response = await client.get(f"/api/{resource}", headers=headers_a)

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == names


async def test_list_pagination(client, resource, headers_a, make):
    for name in ["Alpha", "Bravo", "Charlie"]:
        await make(headers_a, name=name)

    page = (await client.get(f"/api/{resource}?skip=1&limit=1", headers=headers_a)).json()
    beyond_end = (await client.get(f"/api/{resource}?skip=100", headers=headers_a)).json()

    assert [item["name"] for item in page] == ["Bravo"]
    assert beyond_end == []


async def test_get_returns_item(client, resource, headers_a, make):
    created = await make(headers_a)

    response = await client.get(f"/api/{resource}/{created['id']}", headers=headers_a)

    assert response.status_code == 200
    assert response.json() == created


async def test_get_missing_returns_404(client, resource, headers_a):
    response = await client.get(f"/api/{resource}/999999", headers=headers_a)

    assert response.status_code == 404


async def test_update_changes_name(client, resource, headers_a, make):
    created = await make(headers_a, name="Alpha")

    response = await client.put(
        f"/api/{resource}/{created['id']}", json={"name": "Renamed"}, headers=headers_a
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Renamed"
    stored = (await client.get(f"/api/{resource}/{created['id']}", headers=headers_a)).json()
    assert stored["name"] == "Renamed"


async def test_update_to_existing_name_returns_409(client, resource, headers_a, make):
    await make(headers_a, name="Alpha")
    other = await make(headers_a, name="Bravo")

    response = await client.put(
        f"/api/{resource}/{other['id']}", json={"name": "Alpha"}, headers=headers_a
    )

    assert response.status_code == 409


async def test_delete_removes_item(client, resource, headers_a, make):
    created = await make(headers_a)

    response = await client.delete(f"/api/{resource}/{created['id']}", headers=headers_a)

    assert response.status_code == 204
    after = await client.get(f"/api/{resource}/{created['id']}", headers=headers_a)
    assert after.status_code == 404


async def test_delete_item_used_by_invoice_returns_409(
    client, resource, headers_a, make, make_in_use
):
    created = await make(headers_a)
    await make_in_use(headers_a, created)

    response = await client.delete(f"/api/{resource}/{created['id']}", headers=headers_a)

    assert response.status_code == 409
    still_there = await client.get(f"/api/{resource}/{created['id']}", headers=headers_a)
    assert still_there.status_code == 200


# --- edge cases -------------------------------------------------------------

MAX_NAME_LENGTH = {"categories": 100, "suppliers": 255}


async def test_name_length_boundary(client, resource, headers_a):
    limit = MAX_NAME_LENGTH[resource]

    at_limit = await client.post(
        f"/api/{resource}", json={"name": "x" * limit}, headers=headers_a
    )
    over_limit = await client.post(
        f"/api/{resource}", json={"name": "x" * (limit + 1)}, headers=headers_a
    )

    assert at_limit.status_code == 201
    assert over_limit.status_code == 422


async def test_name_is_trimmed(client, resource, headers_a):
    response = await client.post(
        f"/api/{resource}", json={"name": "  Alpha  "}, headers=headers_a
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Alpha"


@pytest.mark.parametrize("name", [" ", "a\x00b"], ids=["blank", "nul-character"])
async def test_create_rejects_unusable_names(client, resource, headers_a, name):
    response = await client.post(f"/api/{resource}", json={"name": name}, headers=headers_a)

    assert response.status_code == 422


async def test_unicode_name_roundtrips(client, resource, headers_a):
    created = (
        await client.post(f"/api/{resource}", json={"name": "ñandú 🙂"}, headers=headers_a)
    ).json()

    fetched = (await client.get(f"/api/{resource}/{created['id']}", headers=headers_a)).json()

    assert fetched["name"] == "ñandú 🙂"


@pytest.mark.parametrize("item_id", ["0", "-1", "abc", "2147483648", "99999999999999999999"])
async def test_invalid_id_returns_422(client, resource, headers_a, item_id):
    url = f"/api/{resource}/{item_id}"

    assert (await client.get(url, headers=headers_a)).status_code == 422
    assert (await client.put(url, json={"name": "X"}, headers=headers_a)).status_code == 422
    assert (await client.delete(url, headers=headers_a)).status_code == 422


async def test_largest_valid_id_returns_404_not_500(client, resource, headers_a):
    response = await client.get(f"/api/{resource}/2147483647", headers=headers_a)

    assert response.status_code == 404


@pytest.mark.parametrize(
    "query",
    ["skip=-1", "limit=0", "limit=101", "limit=abc", "skip=2147483648"],
)
async def test_invalid_pagination_returns_422(client, resource, headers_a, query):
    response = await client.get(f"/api/{resource}?{query}", headers=headers_a)

    assert response.status_code == 422


async def test_update_to_own_current_name_is_allowed(client, resource, headers_a, make):
    created = await make(headers_a, name="Alpha")

    response = await client.put(
        f"/api/{resource}/{created['id']}", json={"name": "Alpha"}, headers=headers_a
    )

    assert response.status_code == 200


@pytest.mark.parametrize("payload", [{}, {"name": ""}, {"name": "A", "id": 5}])
async def test_update_rejects_invalid_payload(client, resource, headers_a, make, payload):
    created = await make(headers_a)

    response = await client.put(
        f"/api/{resource}/{created['id']}", json=payload, headers=headers_a
    )

    assert response.status_code == 422


async def test_update_and_delete_missing_return_404(client, resource, headers_a):
    put = await client.put(f"/api/{resource}/999999", json={"name": "Z"}, headers=headers_a)
    delete = await client.delete(f"/api/{resource}/999999", headers=headers_a)

    assert put.status_code == 404
    assert delete.status_code == 404


async def test_delete_twice_returns_404(client, resource, headers_a, make):
    created = await make(headers_a)
    await client.delete(f"/api/{resource}/{created['id']}", headers=headers_a)

    response = await client.delete(f"/api/{resource}/{created['id']}", headers=headers_a)

    assert response.status_code == 404


async def test_name_can_be_reused_after_delete(client, resource, headers_a, make):
    created = await make(headers_a, name="Alpha")
    await client.delete(f"/api/{resource}/{created['id']}", headers=headers_a)

    response = await client.post(f"/api/{resource}", json={"name": "Alpha"}, headers=headers_a)

    assert response.status_code == 201
