# CRM to ERP integration on Azure (personal project)

A won deal in EspoCRM becomes a customer and sales order in ERPNext through Azure API Management, Functions and Service Bus. When the invoice is paid, a Logic App writes the payment status back to the CRM.

This README grows with the project. For now it covers the local setup (milestone 1).

## Local setup

You need Docker Desktop for Apple Silicon with about 8 GB of memory allocated, and VS Code with the Dev Containers extension.

1. In a Mac terminal, from this folder: `./scripts/up.sh`
   The first run pulls a few GB and ERPNext takes 5 to 15 minutes to create its site. When it finishes it prints the URLs.
2. Open EspoCRM at http://localhost:8081 and ERPNext at http://localhost:8082. Passwords are in `.env`, API keys in `.secrets/local.env`.
3. Test the webhook: run `./scripts/won.sh`, then `docker compose logs -f webhook-inspector`. Within a minute or so you see EspoCRM's payload and its `Signature` header.
4. Open the folder in VS Code and choose "Reopen in Container". The dev container has .NET 10, Functions Core Tools, Azure CLI with Bicep, GitHub CLI and Docker, and sits on the same network as the stack.

Details: [docs/local-stack.md](docs/local-stack.md) (endpoints, connection strings, commands) and [docs/systems-primer.md](docs/systems-primer.md) (how each system models deals, customers, orders and invoices, and how their APIs and webhooks work).

## Layout

```
.devcontainer/      dev container
compose.yaml        local stack: EspoCRM, ERPNext, Azurite, Service Bus emulator, webhook inspector
local/servicebus/   emulator queue definitions
local/seed/         seeding job (API users, keys, sample data)
scripts/            up, down, reset, status, seed, won
docs/               reference notes
```
