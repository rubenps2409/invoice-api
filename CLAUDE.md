# CLAUDE.md --- Invoice API

## 1. Project purpose

This repository contains a Python API built with FastAPI for extracting
structured data from invoice text with an Anthropic LLM and storing the
resulting invoice for the authenticated user.

The extraction contract currently uses these fields: - `supplier_name` -
`supplier_tax_id` (optional) - `invoice_number` - `issue_date` -
`base_amount` (taxable base, after discounts) - `tax_amount` -
`withholding_amount` (optional, defaults to 0; subtracted from the total) -
`total_amount` - `currency` (ISO 4217, required, never assumed) -
`category_name` (optional)

The current flow is intended to validate the model output with Pydantic
before creating database records. Do not assume extraction is always
accurate merely because the output passes schema validation.

This file describes the observed architecture and project conventions.
The actual repository, tests and runtime behavior remain the source of
truth.

## 2. Current architecture

The project uses a `src` layout:

-   `src/invoice_api/main.py`: creates the FastAPI app, registers the
    `/api` router and handles the `ExtractionNotConfigured` exception.
-   `src/invoice_api/routers/`: HTTP endpoints for authentication,
    users, invoices, suppliers, categories and extraction.
-   `src/invoice_api/schemas/`: Pydantic request/response schemas and
    validation.
-   `src/invoice_api/models/`: SQLAlchemy models.
-   `src/invoice_api/services/`: business logic, LLM extraction, invoice
    creation and LLM usage/cost recording.
-   `src/invoice_api/security.py` and `dependencies.py`: token/password
    security and shared request dependencies.
-   `src/invoice_api/config.py`: Pydantic Settings configuration loaded
    from `.env`.
-   `migrations/` and `alembic.ini`: Alembic migrations.
-   `tests/`: automated tests.
-   `evals/`: synthetic LLM extraction cases, scoring, runner and saved
    results.
-   `scripts/seed.py`: development seed data.
-   `docker-compose.yaml`: currently defines PostgreSQL; do not assume
    it also runs the API.
-   `pyproject.toml` and `uv.lock`: project metadata, dependencies and
    tooling.

The API router is mounted under `/api`. The extraction endpoint is
`POST /api/invoices/extract`.

Keep HTTP concerns in routers, data contracts in schemas, persistence
models in models, and reusable business/provider logic in services,
following the existing structure. Avoid moving code across layers unless
there is a clear benefit.

Constants and literals:

-   A constant used by several modules goes in `constants.py`. A constant
    used by one module is declared in that module, with a leading
    underscore unless another module or a test imports it.
-   Exception: constraint names and column sizes live in their model file
    even when other modules import them (see section 4).
-   A user-facing message returned from more than one place has a single
    definition. Do not repeat the literal.
-   Use `status.HTTP_*` names instead of numeric status codes, and a
    `StrEnum` for a fixed set of values (e.g. `AttemptOutcome`) instead of
    loose strings.

## 3. Stack and tooling

The repository currently specifies: - Python `>=3.13` - `uv` for
project/dependency management - FastAPI - Pydantic and Pydantic
Settings - SQLAlchemy 2.x - PostgreSQL with the `psycopg` driver -
Alembic - Anthropic Python SDK - `pwdlib[argon2]` for password hashing -
PyJWT for JWT handling - pytest, pytest-cov and Ruff for development
checks

Check `pyproject.toml`, `uv.lock` and the existing code before changing
dependencies or assuming exact installed versions. Do not replace
libraries or upgrade versions without a concrete reason and user
approval.

Ruff is configured with a 95-character line length, Python 3.13 target,
and lint rules `E`, `F`, `W`, `I`, `UP`, and `B`. Pytest is configured
to use `tests/` and exclude tests marked `eval` by default.

Use the repository's existing `uv` commands. Typical checks are:

-   `uv run pytest`
-   `uv run ruff check .`

Confirm commands against the current configuration and run the relevant
checks after changes. Do not claim a check passed unless it was actually
run.

## 4. Data and database conventions

-   Use the existing SQLAlchemy session dependency and FastAPI
    dependency injection.
-   Use Alembic migrations for schema changes. Do not introduce
    `create_all()` as a production schema-management mechanism.
-   Preserve the existing transaction boundaries and explicitly handle
    rollback where needed.
-   The current invoice model uses `Decimal`/`Numeric` for monetary
    amounts. Preserve decimal-safe arithmetic; do not use binary
    floating-point for persisted money calculations.
-   The invoice model has a uniqueness constraint over
    `(user_id, supplier_id, number)`. Preserve duplicate detection
    behavior and its HTTP response unless the user asks to change it.
-   Supplier and category records are user-owned. When creating invoices
    from extraction, resolve or create suppliers and categories only
    within the authenticated user's data.
-   Check existing migrations and tests before changing model
    constraints, enum values, field names or database types.
-   Name every constraint explicitly, through a constant declared in its
    model file (`<ENTITY>_<FIELD>_UNIQUE`, e.g. `SUPPLIER_TAX_ID_UNIQUE`).
    Never write a constraint name as a literal in a router or service.
    Migrations are the exception: they are frozen snapshots and keep
    literal names.
-   Give every column length and numeric precision a named constant in
    its model file (`<ENTITY>_<FIELD>_MAX_LENGTH`, `_PRECISION`,
    `_SCALE`), and import it wherever something else must match the
    column. Do not repeat the number in a schema or service.
-   The reusable string types in `schemas/common.py` (`Str100`, `Str255`)
    cannot import column lengths, so `tests/test_schema_matches_columns.py`
    keeps them in step. Add the new field to that test when you add a
    text field.
-   When a table has more than one unique constraint, pass
    `constraint_details` to `commit_or_conflict` so each one returns its
    own 409 message.

## 5. Security and privacy

-   Never hard-code API keys, passwords, JWT secrets or other
    credentials.
-   Load secrets through the existing settings/configuration mechanism.
    Do not expose secret values in responses, logs, test output or
    documentation.
-   Do not read or print `.env` values unless the user explicitly asks
    for a necessary, safe diagnostic. Prefer `.env.example` for
    understanding configuration.
-   Treat invoice text as untrusted input. Instructions embedded in a
    supplied invoice must not override the extraction prompt or
    application rules.
-   Validate input size and shape on the server. The current extraction
    request limits text length through `MAX_INVOICE_TEXT_CHARS` and
    rejects NUL characters; preserve these protections unless
    deliberately revising them.
-   Authentication alone is insufficient: enforce authorization at the
    object level. A user must not read, update or delete another user's
    invoices, suppliers or categories by changing an ID.
-   Do not log full invoice text or unnecessary personal/financial data.
-   Use synthetic invoice data in tests, evals, examples and public
    repositories. Never commit real invoices or customer data.
-   Do not weaken password hashing, token validation, ownership filters
    or isolation tests to make a test pass.

## 6. LLM extraction behavior

The extraction service is in `src/invoice_api/services/extraction.py`.
It calls Anthropic through the SDK, parses a JSON object, validates it
against `ExtractedInvoice`, and returns extraction-attempt metadata.
Keep provider-specific behavior in the service rather than coupling it
to HTTP handlers or SQLAlchemy models.

Current design choices visible in the code: - A system prompt requests a
single JSON object with a fixed field contract. - The prompt treats
invoice contents as untrusted data and includes few-shot examples. -
Pydantic validates the extracted schema and checks that base amount +
tax amount - withholding amount matches total amount, within one cent
(`check_amounts` in `schemas/invoice.py`, shared with the manual
endpoints); base, tax and withholding must also share a sign. - The
extracted total must be printed in the invoice text
(`_check_total_is_printed`): when the printed figures do not add up, a
model tends to recompute the total and silently drop an amount, so a
recomputed total is rejected and retried. - The category is matched against the
authenticated user's categories; an unmatched category becomes `None`. -
Output-validation attempts and provider/network failures are handled
separately from HTTP status mapping. - The request endpoint records LLM
usage and estimated cost, including failed attempts, before returning
the appropriate result/error. - `LLM_MAX_RETRIES` configures SDK
retries; the extraction service separately limits attempts to repair
invalid model output. Avoid accidentally multiplying retries or cost. -
Model, timeout, output-token limit, maximum invoice text length and
token prices are configured in settings.

When changing this behavior: - Preserve structured validation before
persistence. - Handle malformed JSON, schema validation errors,
timeouts, provider failures and missing configuration explicitly. - Keep
retry counts bounded and distinguish provider-level retries from retries
after invalid output. - Avoid real provider calls in ordinary unit
tests; mock the SDK/client as the existing tests do. - Do not run the
real evaluation suite unless requested or clearly authorized:
`evals.runner` calls the real model, requires `ANTHROPIC_API_KEY`, and
incurs API cost. - Evaluation results should not contain raw invoice
text. Keep reports limited to case IDs, scores, token counts and cost
unless the user explicitly requests otherwise. - Treat token/cost values
as estimates based on configured prices, not as guaranteed provider
invoices. - Passing schema validation does not establish accounting or
tax correctness. Keep domain limitations explicit and verify tax rules
against official sources before implementing them.

## 7. Tests and evaluations

-   Add or update tests whenever behavior changes.
-   Cover valid inputs, invalid inputs, relevant boundaries and expected
    HTTP status codes.
-   For protected resources, test unauthenticated access and cross-user
    isolation.
-   Use isolated test database fixtures and dependency overrides already
    defined in `tests/conftest.py`.
-   Mock external LLM calls in normal tests so the suite is
    deterministic and does not incur API charges.
-   The project has a separate `evals/` package for LLM quality. Inspect
    its cases, scoring and runner before modifying evaluation behavior.
-   Pytest excludes the `eval` marker by default. Do not remove that
    safeguard or run paid evaluations inadvertently.
-   When fixing a bug, add a regression test if practical.
-   Report which commands were run, whether they passed, and any checks
    not performed.

## 8. Working style

-   Start by reading the relevant implementation and tests before
    editing.
-   Identify the root cause of important bugs before adding features.
-   Prefer minimal, reviewable changes over broad refactors.
-   Do not introduce agents, RAG, orchestration frameworks, background
    workers, queues or other infrastructure unless the user requests
    them or a clear requirement justifies them.
-   Explain meaningful alternatives and trade-offs, especially where
    changes affect security, transactions, API behavior, data models or
    cost.
-   Ask before making a substantial architectural change or a
    potentially breaking change.
-   Keep the developer in control: explain the change well enough that
    they can understand and maintain it without relying on the
    assistant.
-   Do not mark work as complete merely because code was written; use
    relevant tests and checks to verify it.
-   Do not add comments in code with every minor change. Only when truly
    justified and necessary for understanding.

## 9. Current project status and planned scope

The original roadmap places the project at the end of week 3, focused on
LLM integration, with important issues still to be corrected. The
archive shows that the repository already includes CRUD/authentication
code, SQLAlchemy models, Alembic migrations, an extraction service and
endpoint, usage/cost recording, tests, and a synthetic evaluation
framework.

The next planned milestone is to stabilize the existing implementation,
then finish a reproducible and presentable first release. The roadmap
includes Docker for the API and database, CI, deployment and a useful
README, but these are goals---not claims that they are already complete.
Inspect the current repository before planning or implementing them. At
the time of review, `README.md` in the supplied archive was empty and
`docker-compose.yaml` defined only PostgreSQL.

Later roadmap ideas, not assumed to be implemented requirements: -
Asynchronous processing with a worker, idempotency and bounded
retries. - Human review of uncertain extractions and using corrections
in evaluations. - Organizations, roles and multi-tenant data
isolation. - Structured logs, latency/cost metrics, usage limits and
evals in CI.

Do not start these future features while important correctness issues in
the current implementation remain, unless the user explicitly changes
priorities.

## 10. Suggested response format for implementation tasks

When useful, report: 1. The observed issue and evidence in the
code/tests. 2. The proposed fix and why it is appropriate. 3. The files
that need to change. 4. The tests/checks to run. 5. The changes made and
verified results.

Distinguish confirmed bugs from risks or optional improvements. Do not
invent repository details; inspect the relevant files when uncertain.
