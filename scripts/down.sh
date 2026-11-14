#!/usr/bin/env bash
# Stop everything. Data is kept; ./scripts/up.sh brings it back.
cd "$(dirname "$0")/.."
docker compose --profile crm --profile erp --profile azure --profile tools --profile seed down
