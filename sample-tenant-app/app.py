from __future__ import annotations

import hashlib
import hmac
import json
import os
import threading
import time
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Request


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


APP_HOST = _env("APP_HOST", "0.0.0.0")
APP_PORT = int(_env("APP_PORT", "9000"))
TENANT_API_KEY = _env("TENANT_API_KEY", "tenant-a-test-key")
CALLBACK_DELAY_SECONDS = float(_env("CALLBACK_DELAY_SECONDS", "0.5"))
PUBLIC_BASE_URL = _env("PUBLIC_BASE_URL", f"http://localhost:{APP_PORT}")
INTERNAL_BASE_URL = _env("INTERNAL_BASE_URL", f"http://sample-tenant-app:{APP_PORT}")


app = FastAPI(title="Sample Tenant App", version="0.1.0")


def _callback_signature(raw_key: str, body: bytes, timestamp: str) -> str:
    signature_payload = body + timestamp.encode("utf-8")
    return hmac.new(
        raw_key.encode("utf-8"), signature_payload, hashlib.sha256
    ).hexdigest()


def _send_callback(callback_url: str, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = _callback_signature(TENANT_API_KEY, body, timestamp)
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-Api-Key": TENANT_API_KEY,
        "X-Callback-Timestamp": timestamp,
        "X-Callback-Signature": signature,
        "Idempotency-Key": f"cb-{timestamp}",
    }
    try:
        requests.post(callback_url, data=body, headers=headers, timeout=5)
    except Exception:
        # Best-effort callback for sample app.
        return


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/.well-known/workflow-discovery")
def discovery() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "catalog": [
            {
                "id": "cap_sample",
                "name": "Sample Capability",
                "description": "Sample sync + async service tasks",
                "category": "sample",
                "service_url": INTERNAL_BASE_URL,
                "metadata": {},
                "service_tasks": [
                    {
                        "id": "sync_task",
                        "name": "Sync Task",
                        "url": f"{INTERNAL_BASE_URL}/api/sync-task",
                    },
                    {
                        "id": "async_task",
                        "name": "Async Task",
                        "url": f"{INTERNAL_BASE_URL}/api/async-task",
                    },
                ],
            }
        ],
        "rbac": {
            "roles": [{"id": "role_ops", "name": "Operations"}],
            "permissions": [{"id": "perm_run", "name": "Run"}],
            "role_permissions": [{"role_id": "role_ops", "permission_id": "perm_run"}],
        },
        "users": [
            {
                "id": "user_ops",
                "email": "ops@example.com",
                "display_name": "Ops User",
                "role_ids": ["role_ops"],
                "is_active": True,
            }
        ],
    }


@app.post("/api/sync-task")
async def sync_task(request: Request) -> dict[str, Any]:
    payload = await request.json()
    return {
        "status": "completed",
        "result": {
            "echo": payload.get("payload", {}),
            "processed": True,
        },
    }


@app.post("/api/async-task")
async def async_task(request: Request) -> dict[str, Any]:
    payload = await request.json()
    context = payload.get("context", {}) if isinstance(payload, dict) else {}
    callback_url = context.get("callback_url")
    if not callback_url:
        raise HTTPException(status_code=400, detail="Missing callback_url")

    def _background() -> None:
        time.sleep(CALLBACK_DELAY_SECONDS)
        _send_callback(
            callback_url,
            {"status": "completed", "data": {"accepted": True}},
        )

    thread = threading.Thread(target=_background, daemon=True)
    thread.start()
    return {"status": "accepted"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
