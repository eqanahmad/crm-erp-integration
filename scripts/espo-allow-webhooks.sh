#!/usr/bin/env bash
# EspoCRM refuses webhook URLs that point at internal addresses (protection
# against server-side request forgery). Locally every target is internal, so
# allow the exact host:port pairs we use, and nothing else.
#   webhook-inspector:8080    the request inspector
#   crmerp-dev:7071           Functions running in the dev container
#   host.docker.internal:7071 Functions running directly on your Mac
cd "$(dirname "$0")/.."
docker compose exec -T -u www-data espocrm bin/command config:set webhookAllowedAddressList \
  '["webhook-inspector:8080","crmerp-dev:7071","host.docker.internal:7071"]' --type=json \
  && echo "EspoCRM: internal webhook targets allowed"
