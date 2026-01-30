from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from core.models import Tenant, TenantApiKey, WorkflowGroup


class WorkflowGroupsTests(TestCase):
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

    def setUp(self) -> None:
        self.client = APIClient()
        self.client.credentials(HTTP_X_TENANT_API_KEY=self.tenant_key_raw)

    def test_group_crud_tree_and_workflow_assignment(self) -> None:
        # Create root group.
        resp = cast(
            Any,
            self.client.post(
                "/api/workflow-groups",
                data={"name": "HR", "description": "HR processes", "parent_id": None},
                format="json",
            ),
        )
        self.assertEqual(resp.status_code, 201)
        root_id = int(resp.data["id"])

        # Create child group.
        child = cast(
            Any,
            self.client.post(
                "/api/workflow-groups",
                data={"name": "Leave", "description": "Leave", "parent_id": root_id},
                format="json",
            ),
        )
        self.assertEqual(child.status_code, 201)
        child_id = int(child.data["id"])

        # Tree shows nesting.
        tree = cast(Any, self.client.get("/api/workflow-groups/tree"))
        self.assertEqual(tree.status_code, 200)
        self.assertEqual(tree.data[0]["name"], "HR")
        self.assertEqual(tree.data[0]["children"][0]["name"], "Leave")

        # Rename child.
        renamed = cast(
            Any,
            self.client.patch(
                f"/api/workflow-groups/{child_id}",
                data={"name": "Leave Requests"},
                format="json",
            ),
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.data["name"], "Leave Requests")

        # Move child to root.
        moved = cast(
            Any,
            self.client.patch(
                f"/api/workflow-groups/{child_id}",
                data={"parent_id": None},
                format="json",
            ),
        )
        self.assertEqual(moved.status_code, 200)
        self.assertIsNone(moved.data["parent_id"])

        # Create a workflow and assign to group via upload.
        bpmn_path = (
            Path(settings.BASE_DIR).parent
            / "fixtures"
            / "bpmn"
            / "leave_request_v1.bpmn"
        )
        upload = SimpleUploadedFile(
            "leave_request_v1.bpmn",
            bpmn_path.read_bytes(),
            content_type="text/xml",
        )
        created = cast(
            Any,
            self.client.post(
                "/api/workflows",
                data={
                    "bpmn": upload,
                    "name": "Leave Request",
                    "description": "Employee leave workflow",
                    "group_id": child_id,
                },
                format="multipart",
            ),
        )
        self.assertEqual(created.status_code, 201)

        # Listing filters by group.
        listed = cast(Any, self.client.get(f"/api/workflows/list?group_id={child_id}"))
        self.assertEqual(listed.status_code, 200)
        self.assertTrue(
            any(item["process_key"] == "leave_request_v1" for item in listed.data)
        )

        # Cannot delete non-empty group.
        cannot_delete = cast(
            Any, self.client.delete(f"/api/workflow-groups/{child_id}")
        )
        self.assertEqual(cannot_delete.status_code, 400)
        self.assertEqual(cannot_delete.data["code"], "group_not_empty")

        # Ungroup workflow then delete group.
        patch_def = cast(
            Any,
            self.client.patch(
                "/api/workflows/leave_request_v1",
                data={"group_id": None},
                format="json",
            ),
        )
        self.assertEqual(patch_def.status_code, 200)

        deleted = cast(Any, self.client.delete(f"/api/workflow-groups/{child_id}"))
        self.assertEqual(deleted.status_code, 204)
        self.assertFalse(
            WorkflowGroup.objects.filter(tenant=self.tenant, id=child_id).exists()
        )
