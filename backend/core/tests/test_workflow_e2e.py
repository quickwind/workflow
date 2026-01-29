from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from core.discovery import sync_discovery_for_tenant
from core.models import (
    AuditEvent,
    AuditEventType,
    CapabilityCatalogEntry,
    Tenant,
    TenantApiKey,
    TenantDiscoveryEndpoint,
)


class WorkflowE2ETest(TestCase):
    def setUp(self) -> None:
        self.tenant = Tenant.objects.create(name="Tenant A", slug="tenant-a")
        raw_key = "tenant-a-test-key"
        TenantApiKey.objects.create(
            tenant=self.tenant,
            name="e2e",
            key_hash=TenantApiKey.hash_key(raw_key),
        )
        self.client = APIClient()
        self.client.credentials(HTTP_X_TENANT_API_KEY=raw_key)

    def _sync_discovery(self) -> None:
        payload = {
            "schema_version": "1.0",
            "catalog": [
                {
                    "id": "cap_leave",
                    "name": "Leave Service",
                    "description": "",
                    "category": "hr",
                    "service_url": "http://localhost:9999",
                    "metadata": {},
                    "service_tasks": [
                        {
                            "id": "send_email",
                            "name": "Send Email",
                            "url": "http://localhost:9999/service-task",
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
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            json.dump(payload, handle)
            temp_path = handle.name
        endpoint = TenantDiscoveryEndpoint.objects.create(
            tenant=self.tenant,
            endpoint_url=f"file://{temp_path}",
            api_key="local",
        )
        try:
            result = sync_discovery_for_tenant(self.tenant, endpoint)
        finally:
            Path(temp_path).unlink(missing_ok=True)
        self.assertEqual(result.status, "synced")
        self.assertTrue(
            CapabilityCatalogEntry.objects.filter(tenant=self.tenant).exists()
        )

    def _upload_bpmn(self) -> dict[str, object]:
        bpmn_path = (
            Path(settings.BASE_DIR).parent
            / "fixtures"
            / "bpmn"
            / "leave_request_v1.bpmn"
        )
        xml_bytes = bpmn_path.read_bytes()
        upload = SimpleUploadedFile(
            "leave_request_v1.bpmn",
            xml_bytes,
            content_type="text/xml",
        )
        response = self.client.post(
            "/api/workflows", {"bpmn": upload}, format="multipart"
        )
        self.assertEqual(response.status_code, 201)
        return response.json()

    @patch("core.views._perform_service_task_request")
    def test_end_to_end(self, mock_request) -> None:
        mock_request.return_value = (200, {"ok": True}, "")
        self._sync_discovery()

        upload_response = self._upload_bpmn()
        version = upload_response["version"]
        response = self.client.post(
            f"/api/workflows/leave_request_v1/versions/{version}/instances",
            {"correlation_id": "corr-1", "business_key": "bk-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        instance_id = response.json()["id"]

        detail = self.client.get(f"/api/instances/{instance_id}")
        self.assertEqual(detail.status_code, 200)
        detail_payload = detail.json()
        self.assertEqual(len(detail_payload["active_user_tasks"]), 1)
        self.assertEqual(len(detail_payload["active_service_tasks"]), 1)

        user_task_id = detail_payload["active_user_tasks"][0]["id"]
        service_task_id = detail_payload["active_service_tasks"][0]["id"]

        user_complete = self.client.post(
            f"/api/tasks/{user_task_id}/complete",
            {
                "actor": "user1@example.com",
                "action": "approve",
                "payload": {"ok": True},
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="ut-1",
        )
        self.assertEqual(user_complete.status_code, 200)
        self.assertEqual(user_complete.json()["status"], "completed")

        service_start = self.client.post(
            f"/api/service-tasks/{service_task_id}/start",
            {
                "catalog_entry_id": "cap_leave",
                "service_task_id": "send_email",
                "execution_mode": "sync",
                "payload": {"kind": "notify"},
            },
            format="json",
        )
        self.assertEqual(service_start.status_code, 200)
        self.assertEqual(service_start.json()["status"], "completed")

        audit = self.client.get(
            f"/api/audit?workflow_instance_id={instance_id}",
        )
        self.assertEqual(audit.status_code, 200)
        events = [event["event_type"] for event in audit.json()]
        for required in (
            AuditEventType.DEFINITION_UPLOAD,
            AuditEventType.INSTANCE_START,
            AuditEventType.USER_TASK_COMPLETE,
            AuditEventType.SERVICE_TASK_START,
        ):
            self.assertIn(required, events)
        self.assertGreaterEqual(
            AuditEvent.objects.filter(tenant=self.tenant).count(), 4
        )
