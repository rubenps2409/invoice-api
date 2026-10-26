from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from invoice_api.config import settings
from invoice_api.main import app
from invoice_api.models import LlmCall
from invoice_api.schemas.extraction import ExtractedInvoice
from invoice_api.services.extraction import (
    Attempt,
    AttemptOutcome,
    ExtractionInvalidOutput,
    ExtractionResult,
    ExtractionTimeout,
    ExtractionUnavailable,
    get_extractor,
)
from tests.conftest import add_llm_call, user_id_of

URL = "/api/invoices/extract"
TEXT = "FACTURA A-1 Acme S.L. 15/03/2026 Base 100,00 IVA 21,00 Total 121,00"

EXTRACTED = {
    "supplier_name": "Acme S.L.",
    "invoice_number": "A-1",
    "issue_date": "2026-03-15",
    "base_amount": "100.00",
    "tax_amount": "21.00",
    "total_amount": "121.00",
    "currency": "EUR",
    "category_name": None,
}
OK_ATTEMPT = Attempt(AttemptOutcome.OK, input_tokens=1000, output_tokens=100, latency_ms=900)


class FakeExtractor:
    """Replaces the real extractor: no network, scripted outcome."""

    model = "fake-model"

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    async def extract(self, text, categories=()):
        self.calls.append((text, list(categories)))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def succeed(attempts=(OK_ATTEMPT,), **overrides):
    invoice = ExtractedInvoice.model_validate({**EXTRACTED, **overrides})
    return ExtractionResult(invoice, list(attempts))


@pytest.fixture
def use_extractor(client):
    def _use(outcome):
        extractor = FakeExtractor(outcome)
        app.dependency_overrides[get_extractor] = lambda: extractor
        return extractor

    return _use


async def post(client, headers, text=TEXT):
    return await client.post(URL, json={"text": text}, headers=headers)


async def llm_calls(db):
    return (await db.scalars(select(LlmCall).order_by(LlmCall.id))).all()


# --- success ----------------------------------------------------------------


async def test_extracts_and_stores_a_pending_invoice(client, headers_a, use_extractor):
    use_extractor(succeed())

    response = await post(client, headers_a)

    assert response.status_code == 201
    body = response.json()
    assert body["number"] == "A-1"
    assert body["status"] == "pending"
    assert body["total_amount"] == "121.00"
    assert body["issue_date"] == "2026-03-15"
    assert "user_id" not in body
    stored = await client.get(f"/api/invoices/{body['id']}", headers=headers_a)
    assert stored.json() == body


async def test_a_new_supplier_is_created_and_reused(client, headers_a, use_extractor):
    use_extractor(succeed())
    first = (await post(client, headers_a)).json()
    use_extractor(succeed(invoice_number="A-2"))
    second = (await post(client, headers_a)).json()

    suppliers = (await client.get("/api/suppliers", headers=headers_a)).json()

    assert [s["name"] for s in suppliers] == ["Acme S.L."]
    assert first["supplier_id"] == second["supplier_id"] == suppliers[0]["id"]


async def test_the_extractor_receives_only_the_users_own_categories(
    client, headers_a, headers_b, make_category, use_extractor
):
    await make_category(headers_a, name="Software")
    await make_category(headers_a, name="Marketing")
    await make_category(headers_b, name="Secret of B")
    extractor = use_extractor(succeed())

    await post(client, headers_a, text=f"  {TEXT}  ")

    text, categories = extractor.calls[0]
    assert text == TEXT
    assert categories == ["Marketing", "Software"]


async def test_no_transaction_is_held_open_while_the_model_runs(
    client, db, headers_a, make_category, use_extractor
):
    # An open transaction keeps a pooled DB connection checked out for as long
    # as the (slow) model call lasts, which can starve the rest of the API.
    await make_category(headers_a, name="Software")
    extractor = use_extractor(succeed())
    in_transaction_during_call = []
    original_extract = extractor.extract

    async def spy(text, categories=()):
        in_transaction_during_call.append(db.in_transaction())
        return await original_extract(text, categories)

    extractor.extract = spy

    response = await post(client, headers_a)

    assert response.status_code == 201
    assert in_transaction_during_call == [False]


async def test_the_suppliers_tax_id_is_stored_and_listed(client, headers_a, use_extractor):
    use_extractor(succeed(supplier_tax_id="ES-B12.345.678"))

    await post(client, headers_a)

    (supplier,) = (await client.get("/api/suppliers", headers=headers_a)).json()
    assert supplier["name"] == "Acme S.L."
    assert supplier["tax_id"] == "B12345678"


async def test_a_supplier_created_by_hand_with_a_tax_id_is_recognised_by_it(
    client, headers_a, use_extractor
):
    supplier = (
        await client.post(
            "/api/suppliers",
            json={"name": "Acme Soluciones Integrales", "tax_id": "B12345678"},
            headers=headers_a,
        )
    ).json()
    use_extractor(succeed(supplier_name="ACME", supplier_tax_id="B12345678"))

    invoice = (await post(client, headers_a)).json()

    assert invoice["supplier_id"] == supplier["id"]
    assert len((await client.get("/api/suppliers", headers=headers_a)).json()) == 1


async def test_a_wrongly_learned_tax_id_can_be_corrected_through_the_api(
    client, headers_a, use_extractor
):
    # The model takes the customer's tax id for the supplier's.
    use_extractor(succeed(supplier_tax_id="B87654321"))
    first = (await post(client, headers_a)).json()
    (supplier,) = (await client.get("/api/suppliers", headers=headers_a)).json()
    assert supplier["tax_id"] == "B87654321"

    fixed = await client.put(
        f"/api/suppliers/{supplier['id']}",
        json={"name": supplier["name"], "tax_id": "B12345678"},
        headers=headers_a,
    )
    use_extractor(succeed(supplier_tax_id="B12345678", invoice_number="A-2"))
    second = (await post(client, headers_a)).json()

    assert fixed.status_code == 200
    assert second["supplier_id"] == first["supplier_id"]
    assert len((await client.get("/api/suppliers", headers=headers_a)).json()) == 1


async def test_a_name_variant_of_a_known_supplier_is_a_duplicate_invoice(
    client, headers_a, use_extractor
):
    use_extractor(succeed())
    assert (await post(client, headers_a)).status_code == 201
    use_extractor(succeed(supplier_name="ACME, S.L."))

    response = await post(client, headers_a)

    assert response.status_code == 409
    assert len((await client.get("/api/suppliers", headers=headers_a)).json()) == 1
    assert len((await client.get("/api/invoices", headers=headers_a)).json()) == 1


async def test_the_withholding_and_the_currency_are_stored(client, headers_a, use_extractor):
    use_extractor(
        succeed(
            base_amount="1000.00",
            tax_amount="210.00",
            withholding_amount="150.00",
            total_amount="1060.00",
            currency="usd",
        )
    )

    body = (await post(client, headers_a)).json()

    assert body["withholding_amount"] == "150.00"
    assert body["currency"] == "USD"
    assert body["tax_amount"] == "210.00"
    assert (await client.get(f"/api/invoices/{body['id']}", headers=headers_a)).json() == body


async def test_an_invoice_without_withholding_is_stored_with_zero(
    client, headers_a, use_extractor
):
    use_extractor(succeed())

    body = (await post(client, headers_a)).json()

    assert body["withholding_amount"] == "0.00"
    assert body["currency"] == "EUR"


async def test_amounts_from_a_model_that_returns_floats_show_two_decimals(
    client, headers_a, use_extractor
):
    use_extractor(succeed(base_amount=84.3, tax_amount=17.7, total_amount=102.0))

    body = (await post(client, headers_a)).json()

    assert (body["base_amount"], body["tax_amount"], body["total_amount"]) == (
        "84.30",
        "17.70",
        "102.00",
    )
    assert (await client.get(f"/api/invoices/{body['id']}", headers=headers_a)).json() == body


async def test_a_matching_category_is_linked(client, headers_a, make_category, use_extractor):
    category = await make_category(headers_a, name="Software")
    use_extractor(succeed(category_name="Software"))

    response = await post(client, headers_a)

    assert response.json()["category_id"] == category["id"]


async def test_cost_of_the_call_is_recorded(client, db, headers_a, use_extractor):
    use_extractor(succeed())

    await post(client, headers_a)

    (call,) = await llm_calls(db)
    me = (await client.get("/api/users/me", headers=headers_a)).json()
    assert call.user_id == me["id"]
    assert call.model == "fake-model"
    assert call.outcome == AttemptOutcome.OK
    assert (call.input_tokens, call.output_tokens) == (1000, 100)
    assert call.cost_usd > Decimal(0)


# --- request validation -----------------------------------------------------


async def test_requires_authentication(client, use_extractor):
    extractor = use_extractor(succeed())

    response = await client.post(URL, json={"text": TEXT})

    assert response.status_code == 401
    assert extractor.calls == []


async def test_authentication_is_checked_before_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)

    response = await client.post(URL, json={"text": TEXT})

    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"text": ""},
        {"text": "   \n  "},
        {"text": "x" * (settings.MAX_INVOICE_TEXT_CHARS + 1)},
        {"text": "a\x00b"},
        {"text": TEXT, "model": "something-expensive"},
        {"text": 123},
    ],
    ids=[
        "missing",
        "empty",
        "blank",
        "too-long",
        "nul-character",
        "extra-field",
        "not-a-string",
    ],
)
async def test_invalid_request_is_rejected_without_calling_the_model(
    client, db, headers_a, use_extractor, payload
):
    extractor = use_extractor(succeed())

    response = await client.post(URL, json=payload, headers=headers_a)

    assert response.status_code == 422
    assert extractor.calls == []
    assert await llm_calls(db) == []


async def test_text_at_the_size_limit_is_accepted(client, headers_a, use_extractor):
    extractor = use_extractor(succeed())

    response = await post(client, headers_a, text="x" * settings.MAX_INVOICE_TEXT_CHARS)

    assert response.status_code == 201
    assert len(extractor.calls[0][0]) == settings.MAX_INVOICE_TEXT_CHARS


# --- failures: right status, nothing stored, cost still recorded ------------


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (
            ExtractionInvalidOutput(
                "The model did not return a valid invoice (total_amount: mismatch)",
                [
                    Attempt(
                        AttemptOutcome.INVALID_OUTPUT, 900, 40, 800, "total_amount: mismatch"
                    ),
                    Attempt(
                        AttemptOutcome.INVALID_OUTPUT, 950, 40, 800, "total_amount: mismatch"
                    ),
                ],
            ),
            422,
        ),
        (
            ExtractionTimeout(
                "The model took too long to answer",
                [
                    Attempt(
                        AttemptOutcome.TIMEOUT, latency_ms=30000, detail="request timed out"
                    )
                ],
            ),
            504,
        ),
        (
            ExtractionUnavailable(
                "The model API returned an error",
                [Attempt(AttemptOutcome.API_ERROR, latency_ms=200, detail="http 500")],
            ),
            502,
        ),
    ],
    ids=["invalid-output", "timeout", "unavailable"],
)
async def test_extraction_failures_map_to_http_errors(
    client, db, headers_a, use_extractor, error, expected_status
):
    use_extractor(error)

    response = await post(client, headers_a)

    assert response.status_code == expected_status
    assert response.json()["detail"] == str(error)
    assert (await client.get("/api/invoices", headers=headers_a)).json() == []
    assert (await client.get("/api/suppliers", headers=headers_a)).json() == []
    assert [c.outcome for c in await llm_calls(db)] == [a.outcome for a in error.attempts]


async def test_failed_attempts_are_recorded_for_the_right_user(
    client, db, headers_a, headers_b, use_extractor
):
    use_extractor(
        ExtractionTimeout(
            "slow", [Attempt(AttemptOutcome.TIMEOUT, latency_ms=30000, detail="t")]
        )
    )

    await post(client, headers_b)

    (call,) = await llm_calls(db)
    me_b = (await client.get("/api/users/me", headers=headers_b)).json()
    assert call.user_id == me_b["id"]


async def test_error_responses_do_not_echo_the_invoice_text(client, headers_a, use_extractor):
    secret = "SECRET-CUSTOMER-DATA"
    use_extractor(ExtractionInvalidOutput("The model did not return a valid invoice", []))

    response = await post(client, headers_a, text=secret)

    assert secret not in response.text


async def test_missing_api_key_returns_503(client, db, headers_a, monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)

    response = await post(client, headers_a)

    assert response.status_code == 503
    assert await llm_calls(db) == []


async def test_503_does_not_reveal_configuration_details(client, headers_a, monkeypatch):
    monkeypatch.setattr(settings, "ANTHROPIC_API_KEY", None)

    response = await post(client, headers_a)

    assert "ANTHROPIC" not in response.text
    assert "key" not in response.text.lower()


# --- duplicates -------------------------------------------------------------


async def test_duplicate_invoice_returns_409_but_the_cost_is_kept(
    client, db, headers_a, use_extractor
):
    use_extractor(succeed())
    first = await post(client, headers_a)

    second = await post(client, headers_a)

    assert first.status_code == 201
    assert second.status_code == 409
    assert len((await client.get("/api/invoices", headers=headers_a)).json()) == 1
    assert len(await llm_calls(db)) == 2  # both calls spent tokens


async def test_other_users_can_extract_the_same_invoice(
    client, headers_a, headers_b, use_extractor
):
    use_extractor(succeed())
    a = await post(client, headers_a)

    b = await post(client, headers_b)

    assert (a.status_code, b.status_code) == (201, 201)
    assert a.json()["id"] != b.json()["id"]
    assert a.json()["supplier_id"] != b.json()["supplier_id"]


async def test_extracted_invoices_are_isolated_between_users(
    client, headers_a, headers_b, use_extractor
):
    use_extractor(succeed())
    invoice = (await post(client, headers_a)).json()

    assert (
        await client.get(f"/api/invoices/{invoice['id']}", headers=headers_b)
    ).status_code == 404
    assert (await client.get("/api/invoices", headers=headers_b)).json() == []


# --- routing ----------------------------------------------------------------


async def test_extract_path_is_not_read_as_an_invoice_id(client, headers_a):
    assert (await client.get(URL, headers=headers_a)).status_code == 422
    assert (await client.delete(URL, headers=headers_a)).status_code == 422


# --- daily budgets ----------------------------------------------------------


@pytest.fixture
def budgets(monkeypatch):
    monkeypatch.setattr(settings, "USER_DAILY_BUDGET_USD", Decimal("0.10"))
    monkeypatch.setattr(settings, "GLOBAL_DAILY_BUDGET_USD", Decimal("0.50"))


async def test_a_user_who_spent_their_budget_is_stopped_before_anything_is_spent(
    client, db, headers_a, budgets, use_extractor
):
    await add_llm_call(db, await user_id_of(client, headers_a), "0.10")
    extractor = use_extractor(succeed())

    response = await post(client, headers_a)

    assert response.status_code == 429
    assert response.json()["detail"] == "Daily extraction budget reached"
    assert 1 <= int(response.headers["Retry-After"]) <= 24 * 60 * 60
    assert extractor.calls == []  # the model was never asked
    assert len(await llm_calls(db)) == 1  # only the one we added
    assert (await client.get("/api/invoices", headers=headers_a)).json() == []


async def test_a_user_below_the_budget_can_extract(
    client, db, headers_a, budgets, use_extractor
):
    await add_llm_call(db, await user_id_of(client, headers_a), "0.09")
    use_extractor(succeed())

    assert (await post(client, headers_a)).status_code == 201


async def test_one_users_budget_does_not_stop_another(
    client, db, headers_a, headers_b, budgets, use_extractor
):
    await add_llm_call(db, await user_id_of(client, headers_a), "0.20")
    use_extractor(succeed())

    assert (await post(client, headers_b)).status_code == 201
    assert (await post(client, headers_a)).status_code == 429


async def test_the_extraction_that_crosses_the_budget_is_served_and_the_next_one_is_not(
    client, headers_a, monkeypatch, use_extractor
):
    # One extraction costs 0.00015 (1000 in / 100 out at the default prices).
    monkeypatch.setattr(settings, "USER_DAILY_BUDGET_USD", Decimal("0.0001"))
    use_extractor(succeed())

    first = await post(client, headers_a)
    second = await post(client, headers_a)

    assert (first.status_code, second.status_code) == (201, 429)


async def test_failed_extractions_spend_budget_too(
    client, headers_a, monkeypatch, use_extractor
):
    monkeypatch.setattr(settings, "USER_DAILY_BUDGET_USD", Decimal("0.0001"))
    use_extractor(
        ExtractionInvalidOutput(
            "no invoice",
            [Attempt(AttemptOutcome.INVALID_OUTPUT, 1000, 100, 800, "total_amount: mismatch")],
        )
    )

    failed = await post(client, headers_a)
    after = await post(client, headers_a)

    assert (failed.status_code, after.status_code) == (422, 429)


async def test_yesterdays_spending_does_not_block_today(
    client, db, headers_a, budgets, use_extractor
):
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    await add_llm_call(
        db,
        await user_id_of(client, headers_a),
        "5.00",
        created_at=midnight - timedelta(hours=1),
    )
    use_extractor(succeed())

    assert (await post(client, headers_a)).status_code == 201


async def test_when_the_whole_service_spent_its_budget_nobody_can_extract(
    client, db, headers_a, headers_b, budgets, use_extractor
):
    await add_llm_call(db, await user_id_of(client, headers_b), "0.50")
    extractor = use_extractor(succeed())

    response = await post(client, headers_a)  # this user has spent nothing

    assert response.status_code == 503
    assert response.json()["detail"] == "Invoice extraction is temporarily unavailable"
    assert "budget" not in response.text.lower()  # not the user's business
    assert 1 <= int(response.headers["Retry-After"]) <= 24 * 60 * 60
    assert extractor.calls == []


async def test_the_budget_does_not_replace_authentication(
    client, db, headers_a, budgets, use_extractor
):
    await add_llm_call(db, await user_id_of(client, headers_a), "9.00")
    use_extractor(succeed())

    assert (await client.post(URL, json={"text": TEXT})).status_code == 401
