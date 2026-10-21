def test_protected_endpoint_requires_token(client):
    response = client.get("/api/categories")
    assert response.status_code == 401

def test_user_a_can_create_and_read_invoice(client, headers_a, make_supplier, make_invoice):
    supplier = make_supplier(headers_a)
    invoice = make_invoice(headers_a, supplier["id"])

    response = client.get(f"/api/invoices/{invoice['id']}", headers=headers_a)

    assert response.status_code == 200
    assert response.json()["total_amount"] == "121.00"


def test_users_are_different(client, headers_a, headers_b):
    me_a = client.get("/api/users/me", headers=headers_a).json()
    me_b = client.get("/api/users/me", headers=headers_b).json()

    assert me_a["email"] == "a@example.com"
    assert me_b["email"] == "b@example.com"
    assert me_a["id"] != me_b["id"]
