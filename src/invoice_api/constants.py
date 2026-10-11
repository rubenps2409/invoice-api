"""Constantes compartidas por schemas y dependencias."""

# Máximo de un INTEGER de PostgreSQL (2^31 - 1). Un id mayor provoca
# "integer out of range" -> error 500, así que se rechaza en el borde (422).
POSTGRES_INT_MAX = 2_147_483_647

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
