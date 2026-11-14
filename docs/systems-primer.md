# EspoCRM and ERPNext: what you need to know for this project

## EspoCRM (plays Dynamics 365 Sales)

PHP application on MariaDB. Comparable to a model-driven app: entities, fields, layouts and relationships, all editable in Administration > Entity Manager.

**Records that matter here**

| EspoCRM | Dynamics equivalent | Key fields |
|---|---|---|
| Account | account | `name`, `emailAddress`, `billingAddress*`, `website` |
| Contact | contact | `firstName`, `lastName`, `emailAddress`, `accountId` |
| Opportunity | opportunity | `name`, `accountId`, `amount`, `amountCurrency`, `stage`, `closeDate`, `probability` |

Default opportunity stages run from Prospecting through Negotiation to Closed Won or Closed Lost (the seed prints the exact list). "Deal won" means `stage` became `Closed Won`. Record ids are 17 character strings.

**API**

- Base: `/api/v1/{Entity}` and `/api/v1/{Entity}/{id}`. GET, POST, PUT, DELETE.
- Auth for integrations: an **API user** (Administration > API Users) with method API Key, sent as header `X-Api-Key`. HMAC is the stronger option; worth a line in your decision records.
- What an API user can do is set by its **role**, like a Dataverse security role. The seed gives `azure-integration` read, create and edit on Account, Contact and Opportunity, plus the Webhooks scope.
- Filtering: `?where[0][type]=equals&where[0][attribute]=name&where[0][value]=X`. Paging: `maxSize`, `offset`.

**Webhooks**

- Created by an API user (POST `/api/v1/Webhook` with `event` and `url`) or by an admin under Administration > Webhooks. The response gives an `id` and a `secretKey`.
- Event names: `Opportunity.create`, `Opportunity.update`, `Opportunity.delete`, `Opportunity.fieldUpdate.stage`.
- Body is always a JSON **array**, even for one record, and events are batched. Field update events carry the new field values, not the whole record, so your Function may need to read the full opportunity back.
- Signature in header `Signature`: base64 of the webhook id, a colon, then the HMAC-SHA256 of the raw body keyed with the secret. Check the exact encoding against a real request in the inspector before you write the verifier.
- Delivery is **asynchronous**: a scheduled job sends queued webhooks. Default every 5 minutes; the seed sets it to every minute. Failed sends are retried, and a 410 response deletes the webhook.
- EspoCRM refuses webhook URLs that resolve to internal addresses, to block server-side request forgery. Exceptions go in the config parameter `webhookAllowedAddressList` as exact `host:port` pairs. `scripts/espo-allow-webhooks.sh` allows only the inspector and your local Function host. In Azure the target is API Management's public address, so no exception is needed there. This is a good threat-model point.
- The seed registers one webhook pointing at the inspector, so you can see a real payload today.

Docs: https://docs.espocrm.com/development/api/ and https://docs.espocrm.com/administration/webhooks/

## ERPNext (plays Dynamics 365 Finance and Operations)

Python on the Frappe framework, MariaDB, Redis, background workers. Every record type is a **DocType**, and the REST API is generated from DocTypes, so every type works the same way.

**Records that matter here**

| ERPNext | Dynamics equivalent | Key fields |
|---|---|---|
| Customer | customer | `customer_name`, `customer_group`, `territory`, `default_currency` |
| Item | released product | `item_code`, `item_group`, `stock_uom`, `is_stock_item` |
| Sales Order | sales order | `customer`, `company`, `transaction_date`, `delivery_date`, `currency`, `items` (child table: `item_code`, `qty`, `rate`) |
| Sales Invoice | free text or sales invoice | created from a Sales Order, `outstanding_amount`, `status` |
| Payment Entry | customer payment journal | `references` (child table pointing at invoices), `paid_amount` |

**Document lifecycle (`docstatus`)**: 0 is draft, 1 is submitted, 2 is cancelled. Submitted documents can't be edited, only cancelled and amended. Sales orders, invoices and payments all follow this. Deciding whether your integration submits the sales order or leaves it as a draft for a person to review is a real design choice; write it down.

The flow in ERPNext: Sales Order (submitted), then Sales Invoice made from it, then Payment Entry against the invoice. When the payment is submitted, the invoice status becomes Paid. That submit is the event for the return path.

Record names: customers are named by `customer_name` by default; sales orders get series names like `SAL-ORD-2026-00001`. Nothing stores the EspoCRM id yet. Where to keep the cross reference (a custom field on Customer and Sales Order, your Table Storage, or both) is part of your master data decision.

**API**

- Base: `/api/resource/{DocType}` and `/api/resource/{DocType}/{name}`. Lists take `filters`, `fields` and `limit_page_length` as JSON in the query string.
- Methods: `/api/method/{dotted.path}`, for example `frappe.client.submit`.
- Auth: header `Authorization: token API_KEY:API_SECRET`. Keys belong to a user, and that user's roles decide access. The seed uses `integration@example.com` with sales and accounts roles.
- Errors come back as JSON with `exc_type` and `_server_messages`; validation errors are HTTP 417.

**Webhooks**

- Configured as records of the DocType **Webhook** (search "Webhook" in the awesome bar). Pick a DocType and event (for example Payment Entry, on submit), a URL and a JSON body template using Jinja.
- Tick "Enable Security" and set a secret to get header `X-Frappe-Webhook-Signature`: base64 HMAC-SHA256 of the body. Again, confirm against the inspector.
- Sent by background workers through Redis queues, so `erp-queue` must be running.

Docs: https://docs.frappe.io/framework/user/en/api/rest and https://docs.frappe.io/framework/user/en/guides/integration/webhooks

## Seed data

| System | Records |
|---|---|
| EspoCRM | Accounts Northwind Freight, Lakeshore Cold Storage, Prairie Parcel Co; one contact each; four open opportunities in CAD |
| ERPNext | Company Portage Logistics (CAD, Canada, standard chart of accounts); item SVC-INTEGRATION (non-stock service); customers Northwind Freight and Harbourfront Distributors |

Northwind Freight exists in both on purpose: your mapping has to match it rather than create a duplicate. Lakeshore and Prairie exist only in the CRM, so they test the create path.
