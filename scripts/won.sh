#!/usr/bin/env bash
# Mark an EspoCRM opportunity as Closed Won through the API, the same thing a rep
# does in the UI. Fires the Opportunity.fieldUpdate.stage webhook.
#   ./scripts/won.sh                       first open opportunity
#   ./scripts/won.sh "Prairie: carrier rate sync"
cd "$(dirname "$0")/.."
set -a; . ./.env; . ./.secrets/local.env; set +a
name="${1:-}"
docker compose --profile seed run --rm -T -e NAME="$name" -e ESPO_API_KEY="$ESPO_API_KEY" seed python -u - <<'PY'
import json, os, urllib.parse, urllib.request
base = "http://espocrm/api/v1"
h = {"X-Api-Key": os.environ["ESPO_API_KEY"], "Content-Type": "application/json"}
def call(m, p, b=None):
    r = urllib.request.Request(base + p, method=m, headers=h, data=json.dumps(b).encode() if b else None)
    return json.loads(urllib.request.urlopen(r).read() or b"null")
name = os.environ.get("NAME")
where = {"where[0][type]": "notIn", "where[0][attribute]": "stage", "where[0][value][]": ["Closed Won", "Closed Lost"], "maxSize": 1}
if name:
    where = {"where[0][type]": "equals", "where[0][attribute]": "name", "where[0][value]": name, "maxSize": 1}
items = call("GET", "/Opportunity?" + urllib.parse.urlencode(where, doseq=True))["list"]
if not items:
    raise SystemExit("No matching open opportunity")
o = items[0]
call("PUT", f"/Opportunity/{o['id']}", {"stage": "Closed Won", "probability": 100})
print(f"Closed Won: {o['name']} (id {o['id']}). The webhook goes out within a minute.")
PY
