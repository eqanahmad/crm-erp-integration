#!/usr/bin/env bash
# Bring up the whole local stack and seed it. Run from your Mac terminal (not the
# dev container). Safe to run again: it skips anything already done.
#   ./scripts/up.sh            everything
#   ./scripts/up.sh crm erp    only some profiles (crm, erp, azure, tools)
set -euo pipefail
cd "$(dirname "$0")/.."

say() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

docker info >/dev/null 2>&1 || die "Docker is not running. Start Docker Desktop and try again."

[ $# -eq 0 ] && set -- crm erp azure tools
profiles=("$@")
pargs=()
for p in "${profiles[@]}"; do pargs+=(--profile "$p"); done

mem_gb=$(( $(docker info --format '{{.MemTotal}}') / 1024 / 1024 / 1024 ))
if [ "$mem_gb" -lt 7 ]; then
  echo "Docker has about ${mem_gb} GB of memory. The full stack wants 7 to 8 GB."
  echo "Raise it in Docker Desktop > Settings > Resources, or start fewer profiles (./scripts/up.sh crm erp)."
fi

# 1. Local settings with random passwords. Fills any placeholder still in .env.
[ -f .env ] || cp .env.example .env
if grep -q '__RANDOM' .env; then
  say "Filling random local passwords in .env"
  tmp=$(mktemp)
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      *__RANDOM_SQL__*) line="${line/__RANDOM_SQL__/Sb1!$(openssl rand -hex 12)}" ;;
      *__RANDOM__*)     line="${line/__RANDOM__/$(openssl rand -hex 12)}" ;;
    esac
    printf '%s\n' "$line"
  done < .env > "$tmp"
  mv "$tmp" .env
fi
grep -q '__RANDOM' .env && die "Could not fill passwords in .env"
# Values with spaces must be quoted so scripts can read .env.
sed -i.bak -E 's/^ERP_COMPANY=([^"].* .*)$/ERP_COMPANY="\1"/' .env && rm -f .env.bak
mkdir -p .secrets

# 2. Pick native ARM64 images where they exist, Rosetta (amd64) where they don't.
has_arm64() { docker manifest inspect "$1" 2>/dev/null | grep -q '"arm64"'; }
set_env() { sed -i.bak "s#^$1=.*#$1=$2#" .env && rm -f .env.bak; }
erp_ver=$(grep '^ERPNEXT_VERSION=' .env | cut -d= -f2)
if [ "$(uname -m)" = "arm64" ]; then
  say "Checking ARM64 builds"
  if has_arm64 "frappe/erpnext:${erp_ver}"; then set_env ERPNEXT_PLATFORM linux/arm64; echo "ERPNext: native ARM64"
  else set_env ERPNEXT_PLATFORM linux/amd64; echo "ERPNext: no ARM64 build, using Rosetta"; fi
  if has_arm64 "mcr.microsoft.com/azure-messaging/servicebus-emulator:latest"; then set_env SB_PLATFORM linux/arm64; echo "Service Bus emulator: native ARM64"
  else set_env SB_PLATFORM linux/amd64; echo "Service Bus emulator: using Rosetta"; fi
else
  set_env ERPNEXT_PLATFORM linux/amd64; set_env SB_PLATFORM linux/amd64
fi

# 3. Shared network, so the dev container can reach every service by name.
docker network inspect crmerp >/dev/null 2>&1 || docker network create crmerp >/dev/null

# 4. Start.
say "Pulling images (first run downloads a few GB)"
docker compose "${pargs[@]}" pull --quiet
say "Starting: ${profiles[*]}"
docker compose "${pargs[@]}" up -d

# 5. Wait and seed.
want() { for p in "${profiles[@]}"; do [ "$p" = "$1" ] && return 0; done; return 1; }
if want erp; then
  say "Waiting for ERPNext to create its site (5 to 15 minutes on first run)"
  start=$(date +%s)
  until [ "$(docker compose ps -a --format '{{.State}} {{.ExitCode}}' erp-create-site 2>/dev/null)" = "exited 0" ]; do
    state=$(docker compose ps -a --format '{{.State}} {{.ExitCode}}' erp-create-site 2>/dev/null || true)
    case "$state" in exited\ [1-9]*) docker compose logs --tail 40 erp-create-site; die "ERPNext site creation failed (logs above).";; esac
    [ $(( $(date +%s) - start )) -gt 1800 ] && die "ERPNext still not ready after 30 minutes. Run: docker compose logs erp-create-site"
    printf '.'; sleep 10
  done
  echo " ready"
fi

seed_target=""
if want crm && want erp; then seed_target=all; elif want crm; then seed_target=crm; elif want erp; then seed_target=erp; fi
if want crm; then
  say "Allowing local webhook targets in EspoCRM"
  until docker compose exec -T espocrm test -f data/config.php 2>/dev/null; do sleep 5; done
  ./scripts/espo-allow-webhooks.sh || echo "Could not set webhookAllowedAddressList; see docs/local-stack.md"
fi
# Keep the admin passwords in the systems in line with .env (they drift if .env
# is regenerated while the databases are kept).
set -a; . ./.env; set +a
if want crm; then
  printf '%s\n' "$ESPO_ADMIN_PASSWORD" | docker compose exec -T -u www-data espocrm bin/command set-password admin >/dev/null 2>&1 || true
fi
if want erp; then
  docker compose exec -T erp-backend bench --site frontend set-admin-password "$ERP_ADMIN_PASSWORD" >/dev/null 2>&1 || true
fi
if [ -n "$seed_target" ]; then
  say "Seeding ($seed_target)"
  docker compose --profile seed run --rm seed python -u seed.py "$seed_target"
fi

say "Done"
./scripts/status.sh
