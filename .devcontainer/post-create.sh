#!/usr/bin/env bash
# Runs once when the dev container is built.
set -euo pipefail

echo "Installing Azure Functions Core Tools v4 (has a linux-arm64 build)"
npm install -g azure-functions-core-tools@4 --unsafe-perm true

az bicep install >/dev/null 2>&1 || true
az bicep upgrade >/dev/null 2>&1 || true

echo
echo "Tool versions"
dotnet --version
func --version || echo "func did not install, see https://github.com/Azure/azure-functions-core-tools#installing"
az version --query '"azure-cli"' -o tsv
az bicep version
gh --version | head -1
docker compose version
