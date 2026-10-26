# Invoice API

[![CI](https://github.com/rubenps2409/invoice-api/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/rubenps2409/invoice-api/actions/workflows/ci.yml)

An asynchronous API that reads the text of an invoice, extracts its data with an LLM,
**checks that the numbers add up** before trusting them, and stores the invoice for the
authenticated user.

**Live demo:** <https://invoice-api-cdkh.onrender.com/docs>

> The demo runs on a free plan that **goes to sleep after 15 minutes without traffic**.
> The first request after that can take about a minute while the service wakes up.

<!-- The Swagger screenshot goes here. -->

## The problem

Freelancers and small companies in Spain receive invoices as free text or PDFs and key them
in by hand: supplier, tax id, number, date, base, VAT, income-tax withholding (IRPF), total.
Asking an LLM for those fields is easy. Trusting the answer is not: a model that cannot make
the printed figures add up tends to *recompute* the total and silently drop an amount.

This project is the part after the model call: a contract for what an invoice is, validation
that rejects what does not add up, and the controls a public endpoint that spends money needs.

## What it does

- `POST /api/invoices/extract` turns invoice text into a stored `pending` invoice:
  supplier (matched by tax id, then by name), number, date, taxable base, VAT, withholding,
  total, currency (ISO 4217, required, never assumed) and an optional category taken from
  the user's own categories.
- Every extraction is **validated before anything is saved**: schema, `base + tax - withholding
  = total` within one cent, same sign on all three amounts, and the total must appear in the
  invoice text. Invalid output is sent back to the model once with the reason; after that the
  API answers `422` instead of guessing.
- Users, suppliers, categories and invoices have normal CRUD endpoints. Every record is
  owned by a user and cannot be read or changed by anyone else (tested).
- Spending is capped **per user and for the whole service, in USD per UTC day**, summed from a
  table that also records failed model calls. Login and registration are rate-limited per
  client IP, with hashed keys.

| Method | Path | |
|---|---|---|
| POST | `/api/auth/register`, `/api/auth/login` | accounts, JWT |
| GET | `/api/users/me`, `/api/usage`, `/api/health` | profile, own daily spend, health |
| POST, GET | `/api/invoices/extract`, `/api/invoices` | extract from text, list and filter |
| GET, PATCH, DELETE | `/api/invoices/{id}` | |
| POST, GET, PUT, DELETE | `/api/suppliers`, `/api/categories` (and `/{id}`) | |

## Try it

Open the demo's `/docs`, register, press **Authorize**, and send this synthetic invoice to
`POST /api/invoices/extract`:

```json
{
  "text": "FACTURA Nº 2026/17\nFecha de emisión: 03/11/2026\n\nProfesional: Marina Vela Ejemplo\nNIF: 12345678Z\n\nCliente: Agencia Demo S.L.\n\nHonorarios por traducción técnica ........ 800,00 EUR\nIVA (21%) ................................ 168,00 EUR\nRetención IRPF (15%) ..................... -120,00 EUR\n\nTOTAL A PAGAR: 848,00 EUR"
}
```

It returns `201` with base `800.00`, tax `168.00`, withholding `120.00` and total `848.00`.

## Run it locally

You need Docker, and an Anthropic API key only if you want the extraction to work.

```bash
cp .env.example .env     # then set SECRET_KEY (at least 32 characters) and the passwords
docker compose up --build
```

The API listens on <http://127.0.0.1:8000> (`/docs` for the interactive docs). The container
applies the Alembic migrations before it starts. Without `ANTHROPIC_API_KEY` everything works
except extraction, which answers `503`.

To work on the code instead of running the container: `docker compose up -d db`, then
`uv sync` and `uv run fastapi dev`. On Windows, a plain `uvicorn` needs
`--loop asyncio:SelectorEventLoop` because psycopg cannot use the default event loop there.

## Tests and evals

```bash
docker compose up -d db
docker compose exec db createdb -U invoice invoice_test   # once; use the user from your .env
uv run pytest            # a few hundred tests: no network, no API cost
uv run ruff check . && uv run ruff format --check .
```

The suite never calls the model: it swaps the database for a savepoint and the extractor for
a fake. CI runs the same checks on every pull request, plus the migrations and a
`docker compose up` smoke test, and the deploy waits for them to pass.

The quality of the model is measured separately, with a real-model **eval** of 35 synthetic
invoices, five of which must be refused:

```bash
uv run python -m evals.runner --runs 10     # needs ANTHROPIC_API_KEY; about $0.15
```

Last run: 10 passes, 100% of invoices fully correct and 100% of refusals, at an estimated
$0.14. The reports hold case ids, scores, tokens and cost, never invoice text.

## Decisions worth knowing

- **The model is untrusted, and so is the invoice.** The text goes inside delimiters with an
  instruction to treat it as data, and the output is accepted only if it passes every check
  above. A passing schema is not treated as proof of correctness.
- **Money is `Decimal`/`Numeric` end to end.** No floats in anything that is stored or summed.
- **Async from the request to the database.** SQLAlchemy `AsyncSession`, the async Anthropic
  client, and Argon2 hashing in a thread so it does not block the event loop. Measured with a
  fake one-second model in a single process: 400 simultaneous extractions finished in 2.8 s,
  while the earlier threaded version answered 80 of 100 with a `500`. A synthetic benchmark
  (`scripts/load_extraction.py`), not real traffic.
- **The database releases its connection while the model thinks.** The endpoint ends its
  transaction before the call and takes a connection again only to save. A cap on calls in
  flight (`LLM_MAX_CONCURRENT_CALLS`) answers `503` immediately instead of queueing.
- **Limits live in PostgreSQL, not Redis.** Daily budgets and rate-limit events are plain
  tables: one less service to run, and they survive a restart. Failed logins are counted per
  IP+email and per IP, never per email alone, or anyone could lock somebody else out.
- **Per-user data isolation is enforced at the object level**, with a cross-user test for each
  resource.
- **Deployed as a container** on Render (free web service) with a Neon Postgres, from a
  multi-stage image that runs as a non-root user.

## Known limitations

- It extracts and checks arithmetic. It is **not accounting or tax advice**, and it does not
  verify tax rules.
- Advances and unmodelled amounts (such as non-taxable expenses) are refused with `422`
  instead of being stored wrongly. An invoice has one tax rate; mixed rates are not modelled
  line by line, so an inflated base or tax can still pass the sum check.
- There is no review step for uncertain extractions, and extraction is synchronous: a request
  waits for the model.
- Registration is open. The budgets limit the damage, but enough accounts can use up the daily
  cap and pause extraction for everybody until 00:00 UTC.
- The demo's limits count every visitor as one client, because the deployment does not yet
  trust any proxy to tell it the real IP.
- The free plan sleeps when idle, and free tiers can change.

## Layout

```
src/invoice_api/
  routers/      HTTP: endpoints and status codes
  schemas/      Pydantic contracts and the amount checks
  models/       SQLAlchemy tables
  services/     extraction, invoice creation, budgets, rate limits, concurrency cap
migrations/     Alembic
evals/          synthetic cases, scoring and the runner
scripts/        demo data (development only) and a load test
tests/
```
