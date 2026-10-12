# Max value of a PostgreSQL INTEGER (2^31 - 1). Larger ids would cause
# "integer out of range" (500), so they are rejected at the edge (422).
POSTGRES_INT_MAX = 2_147_483_647

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
