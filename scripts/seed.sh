#!/usr/bin/env bash
# Re-run seeding on its own: ./scripts/seed.sh [all|crm|erp]
cd "$(dirname "$0")/.." && mkdir -p .secrets
docker compose --profile seed run --rm seed python -u seed.py "${1:-all}"
