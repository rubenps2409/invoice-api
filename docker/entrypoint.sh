#!/bin/sh
# Brings the database schema up to date, then runs the command (the API).
# Set RUN_MIGRATIONS=false to skip it, for instance when several copies of the
# API start together: Alembic takes no lock, so only one of them should migrate.
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    alembic upgrade head
fi

exec "$@"
