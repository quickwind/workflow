# pyright: reportGeneralTypeIssues=false
# pyright: reportUnknownMemberType=false
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import (
    CapabilityCatalogEntry,
    CatalogServiceTask,
    DirectoryUser,
    ServiceTask,
    Tenant,
    TenantApiKey,
    TenantDiscoveryEndpoint,
)
from core.workflow_runtime import (
    ServiceTaskSnapshot,
    UserTaskSnapshot,
    WorkflowRunResult,
)


class _FakeHTTPResponse:
    def __init__(self, status_code: int, body: dict[str, Any] | None = None) -> None:
        self.status = status_code
        self._body = body or {}

    def read(self) -> bytes:
        return json.dumps(self._body, ensure_ascii=True).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class WorkflowE2EIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        tenant_manager = cast(Any, Tenant)._default_manager
        api_key_manager = cast(Any, TenantApiKey)._default_manager

        cls.tenant = tenant_manager.create(name="Tenant A", slug="tenant-a")
        cls.tenant_key_raw = "tenant-a-test-key"
        api_key_manager.create(
            tenant=cls.tenant,
            name="test",
            key_hash=TenantApiKey.hash_key(cls.tenant_key_raw),
        )

        cls.other_tenant = tenant_manager.create(name="Tenant B", slug="tenant-b")
        cls.other_key_raw = "tenant-b-test-key"
        api_key_manager.create(
            tenant=cls.other_tenant,
            name="test",
            key_hash=TenantApiKey.hash_key(cls.other_key_raw),
        )

    def _client_for(self, raw_key: str) -> APIClient:
        client = APIClient()
        client.credentials(HTTP_X_TENANT_API_KEY=raw_key)
        return client

    def _callback_signature(self, raw_key: str, body: bytes, timestamp: str) -> str:
        signature_payload = body + timestamp.encode("utf-8")
        return hmac.new(
            raw_key.encode("utf-8"), signature_payload, hashlib.sha256
        ).hexdigest()

    def test_e2e_discovery_workflows_tasks_service_callback_audit(self) -> None:
        client = self._client_for(self.tenant_key_raw)
        other_client = self._client_for(self.other_key_raw)

        # Configure discovery endpoint (tenant-scoped).
        resp = cast(
            Any,
            client.post(
                "/api/discovery/endpoint",
                data={
                    "endpoint_url": "https://example.invalid/discovery",
                    "api_key": "discovery-key",
                },
                format="json",
            ),
        )
        self.assertEqual(resp.status_code, 200)
        endpoint_manager = cast(Any, TenantDiscoveryEndpoint)._default_manager
        self.assertTrue(endpoint_manager.filter(tenant=self.tenant).exists())
        self.assertFalse(endpoint_manager.filter(tenant=self.other_tenant).exists())

        discovery_payload = {
            "schema_version": "1.0",
            "catalog": [
                {
                    "id": "cap_leave",
                    "name": "Leave Service",
                    "description": "",
                    "category": "hr",
                    "service_url": "http://localhost:9999/service",
                    "metadata": {},
                    "service_tasks": [
                        {
                            "id": "send_email",
                            "name": "Send Email",
                            "url": "http://localhost:9999/mock/send_email",
                        }
                    ],
                }
            ],
            "rbac": {
                "roles": [{"id": "role_hr", "name": "HR"}],
                "permissions": [{"id": "perm_view", "name": "View"}],
                "role_permissions": [
                    {"role_id": "role_hr", "permission_id": "perm_view"}
                ],
            },
            "users": [
                {
                    "id": "user_1",
                    "email": "user1@example.com",
                    "display_name": "User One",
                    "role_ids": ["role_hr"],
                    "is_active": True,
                }
            ],
        }

        # No external network in tests: patch discovery fetch.
        with patch(
            "core.discovery.fetch_discovery_payload", return_value=discovery_payload
        ):
            call_command("sync_discovery", tenant="tenant-a")

        catalog_entry_manager = cast(Any, CapabilityCatalogEntry)._default_manager
        catalog_task_manager = cast(Any, CatalogServiceTask)._default_manager
        user_manager = cast(Any, DirectoryUser)._default_manager

        self.assertTrue(
            catalog_entry_manager.filter(
                tenant=self.tenant, external_id="cap_leave"
            ).exists()
        )
        self.assertTrue(
            catalog_task_manager.filter(
                tenant=self.tenant,
                catalog_entry__external_id="cap_leave",
                external_id="send_email",
            ).exists()
        )
        self.assertTrue(user_manager.filter(tenant=self.tenant).exists())

        resp = cast(Any, client.get("/api/discovery/catalog"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data[0]["external_id"], "cap_leave")
        self.assertEqual(resp.data[0]["service_tasks"][0]["external_id"], "send_email")

        # Upload BPMN definition.
        repo_root = Path(__file__).resolve().parents[3]
        bpmn_path = repo_root / "fixtures" / "bpmn" / "leave_request_v1.bpmn"
        with open(bpmn_path, "rb") as handle:
            bpmn_upload = SimpleUploadedFile(
                "leave_request_v1.bpmn", handle.read(), content_type="text/xml"
            )
        resp = cast(
            Any,
            client.post(
                "/api/workflows", data={"bpmn": bpmn_upload}, format="multipart"
            ),
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["process_key"], "leave_request_v1")
        self.assertEqual(resp.data["version"], 1)

        # Start instance.
        start_result = WorkflowRunResult(
            status="waiting",
            serialized_state={"state": "initial"},
            waiting_user_tasks=[
                UserTaskSnapshot(
                    task_id="UserTask_Approve",
                    name="Approve Leave",
                    task_type="UserTask",
                )
            ],
            waiting_service_tasks=[
                ServiceTaskSnapshot(
                    task_id="ServiceTask_Notify",
                    name="Notify HR",
                    task_type="ServiceTask",
                    element_id="ServiceTask_Notify",
                    element_name="Notify HR",
                )
            ],
        )
        resume_result = WorkflowRunResult(
            status="waiting",
            serialized_state={"state": "after_service"},
            waiting_user_tasks=[],
            waiting_service_tasks=[],
        )

        with (
            patch(
                "core.views.start_workflow_from_definition", return_value=start_result
            ),
            patch("core.views.resume_workflow_from_state", return_value=resume_result),
        ):
            resp = cast(
                Any,
                client.post(
                    "/api/workflows/leave_request_v1/versions/1/instances",
                    data={"correlation_id": "corr-1", "business_key": "bk-1"},
                    format="json",
                ),
            )
        self.assertEqual(resp.status_code, 201)
        instance_id = int(resp.data["id"])

        # Tenant isolation checks.
        resp = cast(Any, other_client.get(f"/api/instances/{instance_id}"))
        self.assertEqual(resp.status_code, 404)

        resp = cast(Any, client.get(f"/api/instances/{instance_id}"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["id"], instance_id)
        self.assertEqual(len(resp.data["active_user_tasks"]), 1)
        self.assertEqual(len(resp.data["active_service_tasks"]), 1)

        user_task_db_id = int(resp.data["active_user_tasks"][0]["id"])
        service_task_db_id = int(resp.data["active_service_tasks"][0]["id"])

        # Complete a user task record (does not resume workflow state).
        resp = cast(
            Any,
            client.post(
                f"/api/tasks/{user_task_db_id}/complete",
                data={
                    "actor": "user1@example.com",
                    "action": "approve",
                    "payload": {"approved": True},
                },
                format="json",
                HTTP_IDEMPOTENCY_KEY="ut-1",
            ),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "completed")

        # Start the service task in async mode; patch outbound request.
        with patch(
            "core.views.urlopen",
            return_value=_FakeHTTPResponse(200, {"accepted": True}),
        ):
            resp = cast(
                Any,
                client.post(
                    f"/api/service-tasks/{service_task_db_id}/start",
                    data={
                        "catalog_entry_id": "cap_leave",
                        "service_task_id": "send_email",
                        "execution_mode": "async",
                        "payload": {"kind": "notify"},
                    },
                    format="json",
                ),
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "waiting")
        self.assertEqual(resp.data["execution_mode"], "async")

        # Callback completion (no external network): signed request.
        callback_body = json.dumps(
            {"status": "completed", "data": {"ok": True}},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        timestamp = "1700000000"
        signature = self._callback_signature(
            self.tenant_key_raw, callback_body, timestamp
        )
        with patch("core.views.resume_workflow_from_state", return_value=resume_result):
            resp = cast(
                Any,
                client.post(
                    f"/api/service-tasks/{service_task_db_id}/callback",
                    data=callback_body,
                    content_type="application/json",
                    HTTP_X_CALLBACK_TIMESTAMP=timestamp,
                    HTTP_X_CALLBACK_SIGNATURE=signature,
                    HTTP_IDEMPOTENCY_KEY="cb-1",
                ),
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "completed")

        task_manager = cast(Any, ServiceTask)._default_manager
        service_task = task_manager.get(tenant=self.tenant, id=service_task_db_id)
        self.assertEqual(service_task.status, "completed")

        # Audit trail contains key events.
        resp = cast(Any, client.get(f"/api/audit?workflow_instance_id={instance_id}"))
        self.assertEqual(resp.status_code, 200)
        instance_event_types = {item["event_type"] for item in resp.data}
        self.assertTrue(
            {
                "instance_start",
                "user_task_complete",
                "service_task_start",
                "service_task_callback",
            }.issubset(instance_event_types)
        )

        resp = cast(Any, client.get("/api/audit"))
        self.assertEqual(resp.status_code, 200)
        all_event_types = {item["event_type"] for item in resp.data}
        self.assertIn("definition_upload", all_event_types)
