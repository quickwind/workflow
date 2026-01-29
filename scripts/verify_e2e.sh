#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_BASE="${API_BASE:-$BASE_URL/api}"

TENANT_SLUG="${TENANT_SLUG:-tenant-a}"
TENANT_NAME="${TENANT_NAME:-Tenant A}"
TENANT_API_KEY="${TENANT_API_KEY:-tenant-a-test-key}"

BPMN_FILE="${BPMN_FILE:-$(pwd)/fixtures/bpmn/leave_request_v1.bpmn}"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

require curl
require jq
require python

tmpdir="$(mktemp -d)"
cleanup() {
  if [[ -n "${MOCK_PID:-}" ]]; then
    kill "$MOCK_PID" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmpdir"
}
trap cleanup EXIT

echo "BASE_URL=$BASE_URL"
echo "API_BASE=$API_BASE"
echo "TENANT_SLUG=$TENANT_SLUG"

echo "[1/7] Health"
curl -fsS "$API_BASE/health" | jq -e '.status == "ok"' >/dev/null

echo "[2/7] Ensure tenant + API key exist (Django ORM)"
USE_SQLITE=1 DJANGO_SETTINGS_MODULE=config.settings python - <<'PY'
from __future__ import annotations

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings"))
django.setup()

from core.models import Tenant, TenantApiKey

tenant_slug = os.environ.get("TENANT_SLUG", "tenant-a")
tenant_name = os.environ.get("TENANT_NAME", "Tenant A")
raw_key = os.environ.get("TENANT_API_KEY", "tenant-a-test-key")

tenant, _ = Tenant.objects.get_or_create(slug=tenant_slug, defaults={"name": tenant_name})
key_hash = TenantApiKey.hash_key(raw_key)
TenantApiKey.objects.get_or_create(tenant=tenant, key_hash=key_hash, defaults={"name": "e2e"})

print(f"tenant_id={tenant.id} slug={tenant.slug}")
PY

echo "[3/7] Create discovery payload (file://) + sync into catalog/directory"
mock_port="${MOCK_PORT:-9999}"
mock_url="http://127.0.0.1:${mock_port}/service-task"

cat >"$tmpdir/discovery.json" <<EOF
{
  "schema_version": "1.0",
  "catalog": [
    {
      "id": "cap_leave",
      "name": "Leave Service",
      "description": "",
      "category": "hr",
      "service_url": "http://127.0.0.1:${mock_port}",
      "metadata": {},
      "service_tasks": [
        {"id": "send_email", "name": "Send Email", "url": "${mock_url}"}
      ]
    }
  ],
  "rbac": {
    "roles": [{"id": "role_hr", "name": "HR"}],
    "permissions": [{"id": "perm_view", "name": "View"}],
    "role_permissions": [{"role_id": "role_hr", "permission_id": "perm_view"}]
  },
  "users": [
    {
      "id": "user_1",
      "email": "user1@example.com",
      "display_name": "User One",
      "role_ids": ["role_hr"],
      "is_active": true
    }
  ]
}
EOF

discovery_url="file://$tmpdir/discovery.json"

curl -fsS -X POST "$API_BASE/discovery/endpoint" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Api-Key: $TENANT_API_KEY" \
  -d "$(jq -c --arg url "$discovery_url" '{endpoint_url: $url, api_key: "local"}' < /dev/null)" \
  | jq -e '.endpoint_url != ""' >/dev/null

USE_SQLITE=1 DJANGO_SETTINGS_MODULE=config.settings TENANT_SLUG="$TENANT_SLUG" python backend/manage.py sync_discovery --tenant "$TENANT_SLUG" >/dev/null

curl -fsS "$API_BASE/discovery/catalog" \
  -H "X-Tenant-Api-Key: $TENANT_API_KEY" \
  | jq -e '.[0].external_id == "cap_leave" and .[0].service_tasks[0].external_id == "send_email"' >/dev/null

echo "[4/7] Start local mock service task receiver"
python - <<PY &
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        _ = self.rfile.read(length) if length else b""
        body = json.dumps({"accepted": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return

HTTPServer(("127.0.0.1", int("$mock_port")), Handler).serve_forever()
PY

MOCK_PID=$!
sleep 0.2

echo "[5/7] Upload definition + start instance"
upload_json="$tmpdir/upload.json"

curl -fsS -X POST "$API_BASE/workflows" \
  -H "X-Tenant-Api-Key: $TENANT_API_KEY" \
  -F "bpmn=@$BPMN_FILE;type=text/xml" \
  | tee "$upload_json" \
  | jq -e '.process_key == "leave_request_v1" and .version >= 1' >/dev/null

version="$(jq -r '.version' < "$upload_json")"

instance_json="$tmpdir/instance.json"
curl -fsS -X POST "$API_BASE/workflows/leave_request_v1/versions/$version/instances" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Api-Key: $TENANT_API_KEY" \
  -d '{"correlation_id":"corr-1","business_key":"bk-1"}' \
  | tee "$instance_json" \
  | jq -e '.id > 0' >/dev/null

instance_id="$(jq -r '.id' < "$instance_json")"

echo "[6/7] Complete user task + service task callback"
detail_json="$tmpdir/detail.json"
curl -fsS "$API_BASE/instances/$instance_id" \
  -H "X-Tenant-Api-Key: $TENANT_API_KEY" \
  | tee "$detail_json" \
  | jq -e '.active_user_tasks|length==1 and .active_service_tasks|length==1' >/dev/null

user_task_id="$(jq -r '.active_user_tasks[0].id' < "$detail_json")"
service_task_id="$(jq -r '.active_service_tasks[0].id' < "$detail_json")"

curl -fsS -X POST "$API_BASE/tasks/$user_task_id/complete" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Api-Key: $TENANT_API_KEY" \
  -H "Idempotency-Key: ut-1" \
  -d '{"actor":"user1@example.com","action":"approve","payload":{"approved":true}}' \
  | jq -e '.status=="completed"' >/dev/null

curl -fsS -X POST "$API_BASE/service-tasks/$service_task_id/start" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Api-Key: $TENANT_API_KEY" \
  -d '{"catalog_entry_id":"cap_leave","service_task_id":"send_email","execution_mode":"async","payload":{"kind":"notify"}}' \
  | jq -e '.status=="waiting" and .execution_mode=="async"' >/dev/null

callback_body='{"status":"completed","data":{"ok":true}}'
callback_timestamp="1700000000"
callback_sig="$(TENANT_API_KEY="$TENANT_API_KEY" CALLBACK_BODY="$callback_body" CALLBACK_TIMESTAMP="$callback_timestamp" python - <<PY
import hashlib
import hmac
import os

raw_key = os.environ["TENANT_API_KEY"].encode("utf-8")
body = os.environ["CALLBACK_BODY"].encode("utf-8")
ts = os.environ["CALLBACK_TIMESTAMP"].encode("utf-8")
print(hmac.new(raw_key, body + ts, hashlib.sha256).hexdigest())
PY
)"

curl -fsS -X POST "$API_BASE/service-tasks/$service_task_id/callback" \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Api-Key: $TENANT_API_KEY" \
  -H "X-Callback-Timestamp: $callback_timestamp" \
  -H "X-Callback-Signature: $callback_sig" \
  -H "Idempotency-Key: cb-1" \
  -d "$callback_body" \
  | jq -e '.status=="completed"' >/dev/null

echo "[7/7] Verify audit"
curl -fsS "$API_BASE/audit?workflow_instance_id=$instance_id" \
  -H "X-Tenant-Api-Key: $TENANT_API_KEY" \
  | jq -e 'map(.event_type) | (index("definition_upload")!=null) and (index("instance_start")!=null) and (index("user_task_complete")!=null) and (index("service_task_start")!=null) and (index("service_task_callback")!=null)' >/dev/null

echo "OK"
