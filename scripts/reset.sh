#!/usr/bin/env bash
# Stop everything and delete ALL local data (databases, ERPNext site, Azurite,
# generated keys). Asks first.
cd "$(dirname "$0")/.."
read -r -p "Delete all local CRM, ERP and emulator data? Type yes: " ok
[ "$ok" = "yes" ] || { echo "Cancelled"; exit 0; }
docker compose --profile crm --profile erp --profile azure --profile tools --profile seed down -v
rm -f .secrets/local.env
echo "Reset. Run ./scripts/up.sh to start fresh. (.env passwords are kept.)"
