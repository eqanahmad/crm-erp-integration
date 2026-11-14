#!/usr/bin/env bash
# Show what is running and where to find it.
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
docker compose --profile crm --profile erp --profile azure --profile tools ps --format 'table {{.Service}}\t{{.State}}\t{{.Status}}'
cat <<INFO

EspoCRM            http://localhost:${ESPO_PORT:-8081}   user admin,          password in .env (ESPO_ADMIN_PASSWORD)
ERPNext            http://localhost:${ERP_PORT:-8082}   user Administrator,  password in .env (ERP_ADMIN_PASSWORD)
Webhook inspector  http://localhost:${INSPECTOR_PORT:-8083}   see payloads with: docker compose logs -f webhook-inspector
Azurite            blob 10000, queue 10001, table 10002
Service Bus        AMQP 5672, management and health http://localhost:5300/health
API keys           .secrets/local.env
Endpoints for code docs/local-stack.md
INFO
