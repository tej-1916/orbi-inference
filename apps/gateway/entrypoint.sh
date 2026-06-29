#!/usr/bin/env sh
set -eu

alembic -c apps/gateway/alembic.ini upgrade head
exec uvicorn orbi_gateway.main:create_app --factory --host 0.0.0.0 --port 8000
