"""Seed EspoCRM and ERPNext for local integration work.

Runs inside the compose network (docker compose run --rm seed). Standard library
only. Safe to run more than once: every step checks before it creates.

What it does
  EspoCRM: sets CAD as the currency, creates an Integration role and an API user
           with an API key, sample accounts, contacts and open opportunities,
           runs the webhook job every minute, and registers a webhook for
           opportunity stage changes that points at the webhook inspector.
  ERPNext: completes the setup wizard (company, currency, fiscal year), creates
           an integration user with API key and secret, a service item and two
           customers (one matches an EspoCRM account, to exercise matching).
  Writes every key to /secrets/local.env.
"""

import base64
import datetime as dt
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ESPO = os.environ["ESPO_URL"].rstrip("/")
ERP = os.environ["ERP_URL"].rstrip("/")
INSPECTOR = os.environ["INSPECTOR_URL"].rstrip("/")
SECRETS = "/secrets/local.env"

secrets: dict[str, str] = {}


def log(msg: str) -> None:
    print(f"[seed] {msg}")


def warn(msg: str) -> None:
    print(f"[seed] WARNING: {msg}")


class Http:
    def __init__(self, base: str, headers: dict | None = None, cookies: bool = False):
        self.base = base
        self.headers = headers or {}
        handlers = []
        if cookies:
            handlers.append(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.opener = urllib.request.build_opener(*handlers)

    def call(self, method: str, path: str, body=None, form: bool = False, headers=None):
        url = path if path.startswith("http") else self.base + path
        h = {"Accept": "application/json", **self.headers, **(headers or {})}
        data = None
        if body is not None:
            if form:
                data = urllib.parse.urlencode(body).encode()
                h["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                data = json.dumps(body).encode()
                h["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with self.opener.open(req, timeout=300) as r:
                raw = r.read().decode() or "null"
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:800]
            raise RuntimeError(f"{method} {url} failed with {e.code}: {detail}") from None

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, body=None, **kw):
        return self.call("POST", path, body, **kw)

    def put(self, path, body=None, **kw):
        return self.call("PUT", path, body, **kw)


def wait_for(name: str, fn, timeout: int = 900) -> None:
    start = time.time()
    log(f"waiting for {name}")
    last_note = 0.0
    while True:
        try:
            fn()
            log(f"{name} is up")
            return
        except Exception as e:  # noqa: BLE001
            if time.time() - start > timeout:
                raise RuntimeError(f"{name} did not come up in {timeout}s: {e}") from None
            if time.time() - last_note > 30:
                log(f"still waiting for {name}: {str(e)[:200]}")
                last_note = time.time()
            time.sleep(5)


def q(params: dict) -> str:
    return "?" + urllib.parse.urlencode(params)


# --------------------------------------------------------------------------- EspoCRM

def espo_admin() -> Http:
    token = base64.b64encode(f"admin:{os.environ['ESPO_ADMIN_PASSWORD']}".encode()).decode()
    return Http(ESPO + "/api/v1", {"Espo-Authorization": token})


def espo_find(api: Http, entity: str, field: str, value: str):
    params = {
        "where[0][type]": "equals",
        "where[0][attribute]": field,
        "where[0][value]": value,
        "maxSize": 1,
    }
    attempts = [params]
    if entity == "User":
        # API users are hidden from the default user list.
        attempts.insert(0, {**params, "primaryFilter": "api"})
    for p in attempts:
        try:
            items = api.get(f"/{entity}" + q(p)).get("list", [])
        except RuntimeError:
            continue
        if items:
            return items[0]
    return None


def espo_ensure(api: Http, entity: str, key_field: str, data: dict) -> dict:
    found = espo_find(api, entity, key_field, data[key_field])
    if found:
        return found
    created = api.post(f"/{entity}", data)
    log(f"EspoCRM: created {entity} {data[key_field]}")
    return created


def seed_espocrm() -> None:
    admin = espo_admin()
    wait_for("EspoCRM", lambda: admin.get("/App/user"))

    admin.put("/Settings", {
        "baseCurrency": "CAD",
        "defaultCurrency": "CAD",
        "currencyList": ["CAD", "USD"],
    })
    log("EspoCRM: currency set to CAD")

    full = {"create": "yes", "read": "all", "edit": "all", "delete": "no", "stream": "all"}
    role = espo_ensure(admin, "Role", "name", {
        "name": "Integration",
        "data": {
            "Account": full,
            "Contact": full,
            "Opportunity": full,
            "Webhook": True,
        },
        "fieldData": {},
    })

    user = espo_ensure(admin, "User", "userName", {
        "userName": "azure-integration",
        "lastName": "Azure Integration",
        "type": "api",
        "authMethod": "ApiKey",
        "isActive": True,
        "rolesIds": [role["id"]],
    })
    user = admin.get(f"/User/{user['id']}")
    api_key = user.get("apiKey")
    if not api_key:
        raise RuntimeError("EspoCRM API user has no apiKey; check Administration > API Users")
    secrets["ESPO_API_USER_ID"] = user["id"]
    secrets["ESPO_API_KEY"] = api_key
    log("EspoCRM: API user azure-integration ready")

    stage_opts = admin.get("/Metadata" + q({"key": "entityDefs.Opportunity.fields.stage.options"}))
    log(f"EspoCRM: opportunity stages are {stage_opts}")

    accounts = [
        {"name": "Northwind Freight", "type": "Customer", "website": "northwindfreight.example",
         "emailAddress": "ap@northwindfreight.example", "billingAddressCity": "Mississauga",
         "billingAddressState": "ON", "billingAddressCountry": "Canada", "billingAddressPostalCode": "L4W 1A1"},
        {"name": "Lakeshore Cold Storage", "type": "Customer", "website": "lakeshorecold.example",
         "emailAddress": "finance@lakeshorecold.example", "billingAddressCity": "Hamilton",
         "billingAddressState": "ON", "billingAddressCountry": "Canada", "billingAddressPostalCode": "L8P 4R5"},
        {"name": "Prairie Parcel Co", "type": "Customer", "website": "prairieparcel.example",
         "emailAddress": "billing@prairieparcel.example", "billingAddressCity": "Winnipeg",
         "billingAddressState": "MB", "billingAddressCountry": "Canada", "billingAddressPostalCode": "R3C 0V8"},
    ]
    contacts = [
        ("Northwind Freight", "Maya", "Singh", "maya.singh@northwindfreight.example"),
        ("Lakeshore Cold Storage", "Owen", "Tremblay", "owen.tremblay@lakeshorecold.example"),
        ("Prairie Parcel Co", "Priya", "Desai", "priya.desai@prairieparcel.example"),
    ]
    close = (dt.date.today() + dt.timedelta(days=30)).isoformat()
    open_stage = "Negotiation" if "Negotiation" in stage_opts else stage_opts[len(stage_opts) // 2]
    deals = [
        ("Northwind Freight", "Northwind: dock scheduling integration", 48000),
        ("Lakeshore Cold Storage", "Lakeshore: cold chain telemetry", 72500),
        ("Prairie Parcel Co", "Prairie: carrier rate sync", 19900),
        ("Northwind Freight", "Northwind: support renewal 2027", 12000),
    ]

    ids = {}
    for a in accounts:
        ids[a["name"]] = espo_ensure(admin, "Account", "name", a)["id"]
    for acct, first, last, email in contacts:
        espo_ensure(admin, "Contact", "emailAddress", {
            "firstName": first, "lastName": last, "emailAddress": email, "accountId": ids[acct],
        })
    for acct, name, amount in deals:
        espo_ensure(admin, "Opportunity", "name", {
            "name": name, "accountId": ids[acct], "amount": amount, "amountCurrency": "CAD",
            "stage": open_stage, "closeDate": close, "probability": 60,
        })

    # Webhooks are sent by the "Process Webhook Queue" job, every 5 minutes by
    # default. Every minute makes local testing bearable.
    try:
        jobs = admin.get("/ScheduledJob" + q({"maxSize": 200})).get("list", [])
        for j in jobs:
            if j.get("job") == "ProcessWebhookQueue" and j.get("scheduling") != "* * * * *":
                admin.put(f"/ScheduledJob/{j['id']}", {"scheduling": "* * * * *"})
                log("EspoCRM: webhook job now runs every minute")
    except Exception as e:  # noqa: BLE001
        warn(f"could not change webhook job schedule ({e}). Set it in Administration > Scheduled Jobs.")

    # Starter webhook pointing at the inspector, so you can see a real payload.
    # Your Function or API Management endpoint gets its own webhook later.
    api = Http(ESPO + "/api/v1", {"X-Api-Key": api_key})
    try:
        hooks = api.get("/Webhook" + q({"maxSize": 50})).get("list", [])
        target = INSPECTOR + "/espocrm"
        existing = [h for h in hooks if h.get("url") == target]
        if existing:
            hook = admin.get(f"/Webhook/{existing[0]['id']}")
        else:
            hook = api.post("/Webhook", {"event": "Opportunity.fieldUpdate.stage", "url": target})
            log("EspoCRM: webhook Opportunity.fieldUpdate.stage registered to the inspector")
        secrets["ESPO_INSPECTOR_WEBHOOK_ID"] = hook["id"]
        if hook.get("secretKey"):
            secrets["ESPO_INSPECTOR_WEBHOOK_SECRET"] = hook["secretKey"]
    except Exception as e:  # noqa: BLE001
        warn(f"could not register the inspector webhook ({e}). Add it in Administration > Webhooks.")


# --------------------------------------------------------------------------- ERPNext

def erp_admin() -> Http:
    s = Http(ERP, cookies=True)
    s.post("/api/method/login", {"usr": "Administrator", "pwd": os.environ["ERP_ADMIN_PASSWORD"]})
    return s


def erp_list(api: Http, doctype: str, filters=None, fields=None, limit=20):
    params = {"limit_page_length": limit}
    if filters is not None:
        params["filters"] = json.dumps(filters)
    if fields is not None:
        params["fields"] = json.dumps(fields)
    return api.get(f"/api/resource/{urllib.parse.quote(doctype)}" + q(params))["data"]


def erp_leaf(api: Http, doctype: str, prefer: str | None = None) -> str:
    if prefer and erp_list(api, doctype, [["name", "=", prefer], ["is_group", "=", 0]]):
        return prefer
    rows = erp_list(api, doctype, [["is_group", "=", 0]], limit=1)
    if not rows:
        raise RuntimeError(f"ERPNext has no non-group {doctype}")
    return rows[0]["name"]


def erp_setup_wizard(api: Http) -> None:
    def done() -> bool:
        return bool(erp_list(api, "Company", limit=1))

    if done():
        log("ERPNext: setup wizard already complete")
        return
    year = dt.date.today().year
    args = {
        "language": "English",
        "country": os.environ.get("ERP_COUNTRY", "Canada"),
        "timezone": os.environ.get("ERP_TIMEZONE", "America/Toronto"),
        "currency": os.environ.get("ERP_CURRENCY", "CAD"),
        "full_name": "Administrator",
        "email": "admin@example.com",
        "company_name": os.environ.get("ERP_COMPANY", "Portage Logistics"),
        "company_abbr": os.environ.get("ERP_COMPANY_ABBR", "PL"),
        "chart_of_accounts": "Standard",
        "fy_start_date": f"{year}-01-01",
        "fy_end_date": f"{year}-12-31",
        "setup_demo": 0,
    }
    log("ERPNext: running setup wizard (one to three minutes)")
    api.post("/api/method/frappe.desk.page.setup_wizard.setup_wizard.setup_complete",
             {"args": json.dumps(args)}, form=True)
    start = time.time()
    while not done():
        if time.time() - start > 600:
            raise RuntimeError("ERPNext setup wizard did not finish; open http://localhost:8082 and finish it in the browser, then rerun ./scripts/seed.sh")
        time.sleep(5)
    log("ERPNext: company created")


def seed_erpnext() -> None:
    wait_for("ERPNext", lambda: Http(ERP).get("/api/method/ping"))
    api = erp_admin()
    erp_setup_wizard(api)
    api = erp_admin()  # fresh session after setup

    email = "integration@example.com"
    if not erp_list(api, "User", [["name", "=", email]]):
        api.post("/api/resource/User", {
            "email": email,
            "first_name": "Azure",
            "last_name": "Integration",
            "user_type": "System User",
            "send_welcome_email": 0,
            "roles": [{"role": r} for r in (
                "Sales User", "Sales Manager", "Accounts User", "Accounts Manager", "Stock User")],
        })
        log("ERPNext: integration user created")

    user = api.get(f"/api/resource/User/{urllib.parse.quote(email)}")["data"]
    if user.get("api_key") and os.path.exists(SECRETS) and "ERP_API_SECRET=" in open(SECRETS).read():
        log("ERPNext: integration user already has keys, keeping them")
        for line in open(SECRETS):
            if line.startswith(("ERP_API_KEY=", "ERP_API_SECRET=")):
                k, v = line.strip().split("=", 1)
                secrets[k] = v
    else:
        res = api.post("/api/method/frappe.core.doctype.user.user.generate_keys", {"user": email}, form=True)
        msg = res.get("message", {})
        user = api.get(f"/api/resource/User/{urllib.parse.quote(email)}")["data"]
        secrets["ERP_API_KEY"] = msg.get("api_key") or user["api_key"]
        secrets["ERP_API_SECRET"] = msg["api_secret"]
        log("ERPNext: API key and secret generated for integration@example.com")

    item_group = erp_leaf(api, "Item Group", "Services")
    if not erp_list(api, "Item", [["name", "=", "SVC-INTEGRATION"]]):
        api.post("/api/resource/Item", {
            "item_code": "SVC-INTEGRATION",
            "item_name": "Integration services",
            "item_group": item_group,
            "stock_uom": "Nos",
            "is_stock_item": 0,
            "include_item_in_manufacturing": 0,
            "description": "Default line item for deals won in the CRM",
        })
        log("ERPNext: item SVC-INTEGRATION created")

    group = erp_leaf(api, "Customer Group", "Commercial")
    territory = erp_leaf(api, "Territory", os.environ.get("ERP_COUNTRY", "Canada"))
    for name in ("Northwind Freight", "Harbourfront Distributors"):
        if not erp_list(api, "Customer", [["customer_name", "=", name]]):
            api.post("/api/resource/Customer", {
                "customer_name": name,
                "customer_type": "Company",
                "customer_group": group,
                "territory": territory,
                "default_currency": os.environ.get("ERP_CURRENCY", "CAD"),
            })
            log(f"ERPNext: customer {name} created")

    company = erp_list(api, "Company", fields=["name", "default_currency"], limit=1)[0]
    secrets["ERP_COMPANY"] = company["name"]
    secrets["ERP_ITEM_CODE"] = "SVC-INTEGRATION"
    secrets["ERP_CUSTOMER_GROUP"] = group
    secrets["ERP_TERRITORY"] = territory


# --------------------------------------------------------------------------- smoke tests

def smoke() -> None:
    espo = Http(ESPO + "/api/v1", {"X-Api-Key": secrets["ESPO_API_KEY"]})
    n = espo.get("/Opportunity" + q({"maxSize": 1})).get("total")
    log(f"smoke: EspoCRM API key works, {n} opportunities visible")
    erp = Http(ERP, {"Authorization": f"token {secrets['ERP_API_KEY']}:{secrets['ERP_API_SECRET']}"})
    who = erp.get("/api/method/frappe.auth.get_logged_user")["message"]
    custs = erp_list(erp, "Customer", fields=["name"])
    log(f"smoke: ERPNext token works as {who}, {len(custs)} customers visible")


def write_secrets() -> None:
    os.makedirs(os.path.dirname(SECRETS), exist_ok=True)
    existing = {}
    if os.path.exists(SECRETS):
        for line in open(SECRETS):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                existing[k] = v
    existing.update(secrets)
    with open(SECRETS, "w") as f:
        f.write("# Generated by local/seed/seed.py. Local stack only. Git-ignored.\n")
        for k in sorted(existing):
            f.write(f"{k}={existing[k]}\n")
    log(f"keys written to .secrets/local.env")


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    try:
        if only in ("all", "crm"):
            seed_espocrm()
        if only in ("all", "erp"):
            seed_erpnext()
    finally:
        if secrets:
            write_secrets()
    if only == "all":
        smoke()
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
