# Local stack reference

Everything runs in Docker on one network named `crmerp`. The dev container joins that network too, so inside it you use service names, and from your Mac you use `localhost`.

## Services

| Service | From your Mac | From the dev container or another container | Login |
|---|---|---|---|
| EspoCRM UI and API | http://localhost:8081 | http://espocrm | `admin`, password `ESPO_ADMIN_PASSWORD` in `.env` |
| ERPNext UI and API | http://localhost:8082 | http://erpnext:8080 | `Administrator`, password `ERP_ADMIN_PASSWORD` in `.env` |
| Webhook inspector | http://localhost:8083 | http://webhook-inspector:8080 | none |
| Azurite blob, queue, table | ports 10000, 10001, 10002 | host `azurite` | well-known dev key |
| Service Bus emulator | AMQP 5672, management 5300 | host `servicebus-emulator` | well-known dev key |
| Your Functions (when running in the dev container) | http://localhost:7071 | http://crmerp-dev:7071 | function keys are off locally |

## API keys

`./scripts/up.sh` writes them to `.secrets/local.env` (git-ignored):

| Variable | What it is |
|---|---|
| `ESPO_API_KEY` | EspoCRM API user `azure-integration`. Send as header `X-Api-Key`. |
| `ESPO_INSPECTOR_WEBHOOK_ID`, `ESPO_INSPECTOR_WEBHOOK_SECRET` | The starter webhook that posts opportunity stage changes to the inspector. |
| `ERP_API_KEY`, `ERP_API_SECRET` | ERPNext user `integration@example.com`. Send as header `Authorization: token KEY:SECRET`. |
| `ERP_COMPANY`, `ERP_ITEM_CODE`, `ERP_CUSTOMER_GROUP`, `ERP_TERRITORY` | Values a sales order needs. |

## Connection strings for local.settings.json

Storage (Azurite), from inside the dev container:

```
DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://azurite:10000/devstoreaccount1;QueueEndpoint=http://azurite:10001/devstoreaccount1;TableEndpoint=http://azurite:10002/devstoreaccount1;
```

`UseDevelopmentStorage=true` only works from your Mac, because it points at 127.0.0.1.

Service Bus emulator, from inside the dev container:

```
Endpoint=sb://servicebus-emulator;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=SAS_KEY_VALUE;UseDevelopmentEmulator=true;
```

From your Mac, replace `servicebus-emulator` with `localhost`. For the administration client (creating entities from code) add the port: `sb://localhost:5300`.

The emulator ignores identity and only takes connection strings. In Azure you will use managed identity instead, so keep the connection setting name the same and switch how it is resolved per environment.

## Service Bus entities

Defined in `local/servicebus/Config.json` and created when the emulator starts. One queue to begin with:

| Queue | Duplicate detection | Max delivery count | Lock | TTL |
|---|---|---|---|---|
| `deals-won` | on, 5 minute window (the emulator maximum) | 5 | 1 minute | 1 hour |

These are starter values for local work. You decide the real ones when you write the Bicep, and you should be able to say why. Change the file and run `docker compose --profile azure restart servicebus-emulator` to apply.

Emulator limits worth knowing: no portal, no Service Bus Explorer, no identity, and entity settings come only from this file or the administration client.

## Everyday commands (run on your Mac, in the repo folder)

| Command | What it does |
|---|---|
| `./scripts/up.sh` | Start everything and seed. Safe to rerun. |
| `./scripts/up.sh crm erp` | Start only the CRM and ERP, to save memory. |
| `./scripts/status.sh` | What is running and the URLs. |
| `./scripts/won.sh` | Mark the first open opportunity Closed Won, which fires the webhook. |
| `docker compose logs -f webhook-inspector` | Watch webhook payloads arrive. |
| `./scripts/seed.sh` | Rerun seeding only. |
| `./scripts/espo-allow-webhooks.sh` | Let EspoCRM send webhooks to the inspector and your local Functions (it blocks internal addresses by default). |
| `./scripts/down.sh` | Stop, keep data. |
| `./scripts/reset.sh` | Stop and delete all data. |

## Memory

The full stack wants 7 to 8 GB in Docker Desktop. SQL Server (behind the Service Bus emulator) is the heaviest piece and runs under Rosetta because it has no ARM64 build. When you are only working on the CRM or ERP side, run `./scripts/up.sh crm erp`.
