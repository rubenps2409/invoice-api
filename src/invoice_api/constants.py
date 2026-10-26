# Max value of a PostgreSQL INTEGER (2^31 - 1). Larger ids would cause
# "integer out of range" (500), so they are rejected at the edge (422).
POSTGRES_INT_MAX = 2_147_483_647

DEFAULT_PAGE_SIZE = 20

# Value of the WWW-Authenticate header on 401 responses.
BEARER_SCHEME = "Bearer"

# One message for the 409 whether the duplicate is found by the invoice
# endpoints or by the extraction.
INVOICE_DUPLICATE_DETAIL = "An invoice with this number already exists for this supplier"

# The rate limiter keeps its events for this long, so no window may be longer.
RATE_LIMIT_MAX_WINDOW_MINUTES = 24 * 60
