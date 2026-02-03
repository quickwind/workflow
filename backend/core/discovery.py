from __future__ import annotations

"""
Logic for fetching, validating, and syncing tenant discovery data.
Discovery data defines a tenant's automation capabilities (service tasks) and RBAC model.
"""

import json
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen

from django.db import transaction
from django.utils import timezone

from .models import (
    CapabilityCatalogEntry,
    CatalogServiceTask,
    DirectoryUser,
    DirectoryUserRole,
    RbacPermission,
    RbacRole,
    RbacRolePermission,
    Tenant,
    TenantDiscoveryEndpoint,
    TenantDiscoveryPayload,
)


class DiscoveryFetchError(RuntimeError):
    """Raised when discovery payload cannot be fetched from the tenant endpoint."""

    pass


@dataclass(frozen=True)
class DiscoverySyncResult:
    """Result of a discovery sync operation for a tenant."""

    tenant_id: int
    status: str
    errors: list[dict[str, str]]


def validate_discovery_payload(payload: Any) -> list[dict[str, str]]:
    """
    Validates a discovery payload against the expected schema version 1.0.
    Checks for required fields, data types, and unique identifiers.
    Returns a list of error dictionaries with 'path', 'code', and 'message'.
    """
    errors: list[dict[str, str]] = _error_list()
    # ... rest of validation logic ...

    if not isinstance(payload, dict):
        _add_error(errors, "", "invalid_type", "Payload must be an object.")
        return _sorted_errors(errors)

    allowed_top = {"schema_version", "catalog", "rbac", "users"}
    for key in sorted(payload.keys()):
        if key not in allowed_top:
            _add_error(errors, key, "unexpected_field", "Unexpected field.")

    for key in sorted(allowed_top):
        if key not in payload:
            _add_error(errors, key, "required", "Field is required.")

    schema_version = payload.get("schema_version")
    if "schema_version" in payload and not _expect_type(
        errors, "schema_version", schema_version, str
    ):
        pass
    elif isinstance(schema_version, str) and schema_version != "1.0":
        _add_error(
            errors,
            "schema_version",
            "unsupported",
            "Only schema_version 1.0 is supported.",
        )

    catalog = payload.get("catalog")
    if "catalog" in payload and _expect_type(errors, "catalog", catalog, list):
        catalog_ids: set[str] = set()
        for idx, entry in enumerate(catalog):
            entry_path = f"catalog[{idx}]"
            if not _expect_type(errors, entry_path, entry, dict):
                continue
            allowed_entry = {
                "id",
                "name",
                "description",
                "category",
                "service_url",
                "service_tasks",
                "metadata",
            }
            for key in sorted(entry.keys()):
                if key not in allowed_entry:
                    _add_error(
                        errors,
                        f"{entry_path}.{key}",
                        "unexpected_field",
                        "Unexpected field.",
                    )
            for key in ["id", "name", "service_url"]:
                if key not in entry:
                    _add_error(
                        errors,
                        f"{entry_path}.{key}",
                        "required",
                        "Field is required.",
                    )
            entry_id = entry.get("id")
            if "id" in entry and _expect_type(
                errors, f"{entry_path}.id", entry_id, str
            ):
                if entry_id in catalog_ids:
                    _add_error(
                        errors,
                        f"{entry_path}.id",
                        "duplicate_id",
                        "Catalog id must be unique.",
                    )
                catalog_ids.add(entry_id)
            if "name" in entry:
                _expect_type(errors, f"{entry_path}.name", entry.get("name"), str)
            if "description" in entry:
                _expect_type(
                    errors, f"{entry_path}.description", entry.get("description"), str
                )
            if "category" in entry:
                _expect_type(
                    errors, f"{entry_path}.category", entry.get("category"), str
                )
            if "service_url" in entry:
                _expect_type(
                    errors, f"{entry_path}.service_url", entry.get("service_url"), str
                )
            if "metadata" in entry and not _expect_type(
                errors, f"{entry_path}.metadata", entry.get("metadata"), dict
            ):
                pass

            service_tasks = entry.get("service_tasks", [])
            if "service_tasks" in entry and _expect_type(
                errors, f"{entry_path}.service_tasks", service_tasks, list
            ):
                task_ids: set[str] = set()
                for task_idx, task in enumerate(service_tasks):
                    task_path = f"{entry_path}.service_tasks[{task_idx}]"
                    if not _expect_type(errors, task_path, task, dict):
                        continue
                    allowed_task = {"id", "name", "url"}
                    for key in sorted(task.keys()):
                        if key not in allowed_task:
                            _add_error(
                                errors,
                                f"{task_path}.{key}",
                                "unexpected_field",
                                "Unexpected field.",
                            )
                    for key in ["id", "name", "url"]:
                        if key not in task:
                            _add_error(
                                errors,
                                f"{task_path}.{key}",
                                "required",
                                "Field is required.",
                            )
                    task_id = task.get("id")
                    if "id" in task and _expect_type(
                        errors, f"{task_path}.id", task_id, str
                    ):
                        if task_id in task_ids:
                            _add_error(
                                errors,
                                f"{task_path}.id",
                                "duplicate_id",
                                "Service task id must be unique within catalog entry.",
                            )
                        task_ids.add(task_id)
                    if "name" in task:
                        _expect_type(errors, f"{task_path}.name", task.get("name"), str)
                    if "url" in task:
                        _expect_type(errors, f"{task_path}.url", task.get("url"), str)

    rbac = payload.get("rbac")
    role_ids: set[str] = set()
    permission_ids: set[str] = set()
    if "rbac" in payload and _expect_type(errors, "rbac", rbac, dict):
        allowed_rbac = {"roles", "permissions", "role_permissions"}
        for key in sorted(rbac.keys()):
            if key not in allowed_rbac:
                _add_error(
                    errors, f"rbac.{key}", "unexpected_field", "Unexpected field."
                )
        for key in sorted(allowed_rbac):
            if key not in rbac:
                _add_error(errors, f"rbac.{key}", "required", "Field is required.")

        roles = rbac.get("roles")
        if "roles" in rbac and _expect_type(errors, "rbac.roles", roles, list):
            for idx, role in enumerate(roles):
                role_path = f"rbac.roles[{idx}]"
                if not _expect_type(errors, role_path, role, dict):
                    continue
                allowed_role = {"id", "name", "description"}
                for key in sorted(role.keys()):
                    if key not in allowed_role:
                        _add_error(
                            errors,
                            f"{role_path}.{key}",
                            "unexpected_field",
                            "Unexpected field.",
                        )
                for key in ["id", "name"]:
                    if key not in role:
                        _add_error(
                            errors,
                            f"{role_path}.{key}",
                            "required",
                            "Field is required.",
                        )
                role_id = role.get("id")
                if "id" in role and _expect_type(
                    errors, f"{role_path}.id", role_id, str
                ):
                    if role_id in role_ids:
                        _add_error(
                            errors,
                            f"{role_path}.id",
                            "duplicate_id",
                            "Role id must be unique.",
                        )
                    role_ids.add(role_id)
                if "name" in role:
                    _expect_type(errors, f"{role_path}.name", role.get("name"), str)
                if "description" in role:
                    _expect_type(
                        errors, f"{role_path}.description", role.get("description"), str
                    )

        permissions = rbac.get("permissions")
        if "permissions" in rbac and _expect_type(
            errors, "rbac.permissions", permissions, list
        ):
            for idx, permission in enumerate(permissions):
                permission_path = f"rbac.permissions[{idx}]"
                if not _expect_type(errors, permission_path, permission, dict):
                    continue
                allowed_permission = {"id", "name", "description"}
                for key in sorted(permission.keys()):
                    if key not in allowed_permission:
                        _add_error(
                            errors,
                            f"{permission_path}.{key}",
                            "unexpected_field",
                            "Unexpected field.",
                        )
                for key in ["id", "name"]:
                    if key not in permission:
                        _add_error(
                            errors,
                            f"{permission_path}.{key}",
                            "required",
                            "Field is required.",
                        )
                permission_id = permission.get("id")
                if "id" in permission and _expect_type(
                    errors, f"{permission_path}.id", permission_id, str
                ):
                    if permission_id in permission_ids:
                        _add_error(
                            errors,
                            f"{permission_path}.id",
                            "duplicate_id",
                            "Permission id must be unique.",
                        )
                    permission_ids.add(permission_id)
                if "name" in permission:
                    _expect_type(
                        errors, f"{permission_path}.name", permission.get("name"), str
                    )
                if "description" in permission:
                    _expect_type(
                        errors,
                        f"{permission_path}.description",
                        permission.get("description"),
                        str,
                    )

        role_permissions = rbac.get("role_permissions")
        if "role_permissions" in rbac and _expect_type(
            errors, "rbac.role_permissions", role_permissions, list
        ):
            for idx, role_permission in enumerate(role_permissions):
                rp_path = f"rbac.role_permissions[{idx}]"
                if not _expect_type(errors, rp_path, role_permission, dict):
                    continue
                allowed_rp = {"role_id", "permission_id"}
                for key in sorted(role_permission.keys()):
                    if key not in allowed_rp:
                        _add_error(
                            errors,
                            f"{rp_path}.{key}",
                            "unexpected_field",
                            "Unexpected field.",
                        )
                for key in ["role_id", "permission_id"]:
                    if key not in role_permission:
                        _add_error(
                            errors,
                            f"{rp_path}.{key}",
                            "required",
                            "Field is required.",
                        )
                role_id = role_permission.get("role_id")
                permission_id = role_permission.get("permission_id")
                if "role_id" in role_permission and _expect_type(
                    errors, f"{rp_path}.role_id", role_id, str
                ):
                    if role_id not in role_ids:
                        _add_error(
                            errors,
                            f"{rp_path}.role_id",
                            "invalid_reference",
                            "Unknown role_id.",
                        )
                if "permission_id" in role_permission and _expect_type(
                    errors, f"{rp_path}.permission_id", permission_id, str
                ):
                    if permission_id not in permission_ids:
                        _add_error(
                            errors,
                            f"{rp_path}.permission_id",
                            "invalid_reference",
                            "Unknown permission_id.",
                        )

    users = payload.get("users")
    if "users" in payload and _expect_type(errors, "users", users, list):
        user_ids: set[str] = set()
        for idx, user in enumerate(users):
            user_path = f"users[{idx}]"
            if not _expect_type(errors, user_path, user, dict):
                continue
            allowed_user = {"id", "email", "display_name", "role_ids", "is_active"}
            for key in sorted(user.keys()):
                if key not in allowed_user:
                    _add_error(
                        errors,
                        f"{user_path}.{key}",
                        "unexpected_field",
                        "Unexpected field.",
                    )
            for key in ["id", "email"]:
                if key not in user:
                    _add_error(
                        errors,
                        f"{user_path}.{key}",
                        "required",
                        "Field is required.",
                    )
            user_id = user.get("id")
            if "id" in user and _expect_type(errors, f"{user_path}.id", user_id, str):
                if user_id in user_ids:
                    _add_error(
                        errors,
                        f"{user_path}.id",
                        "duplicate_id",
                        "User id must be unique.",
                    )
                user_ids.add(user_id)
            if "email" in user:
                _expect_type(errors, f"{user_path}.email", user.get("email"), str)
            if "display_name" in user:
                _expect_type(
                    errors, f"{user_path}.display_name", user.get("display_name"), str
                )
            role_ids_value = user.get("role_ids", [])
            if "role_ids" in user and _expect_type(
                errors, f"{user_path}.role_ids", role_ids_value, list
            ):
                for role_idx, role_id in enumerate(role_ids_value):
                    role_path = f"{user_path}.role_ids[{role_idx}]"
                    if not _expect_type(errors, role_path, role_id, str):
                        continue
                    if role_id not in role_ids:
                        _add_error(
                            errors,
                            role_path,
                            "invalid_reference",
                            "Unknown role_id.",
                        )
            if "is_active" in user:
                _expect_type(
                    errors, f"{user_path}.is_active", user.get("is_active"), bool
                )

    return _sorted_errors(errors)


def fetch_discovery_payload(endpoint: TenantDiscoveryEndpoint) -> dict[str, Any]:
    """
    Performs an HTTP GET request to the tenant's discovery endpoint.
    Expects a JSON object in response.
    """
    request = Request(endpoint.endpoint_url)
    request.add_header("X-Discovery-Api-Key", endpoint.api_key)
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise DiscoveryFetchError("Discovery payload must be a JSON object.")
    return payload


def sync_discovery_for_tenant(
    tenant: Tenant, endpoint: TenantDiscoveryEndpoint
) -> DiscoverySyncResult:
    """
    Full end-to-end sync process:
    1. Fetch payload from endpoint.
    2. Validate payload schema.
    3. Update tenant-scoped catalog, RBAC, and user directory in a single transaction.
    """
    try:
        payload = fetch_discovery_payload(endpoint)
    except Exception as exc:  # noqa: BLE001 - surfacing deterministic errors
        endpoint.last_synced_at = timezone.now()
        endpoint.last_sync_status = "fetch_failed"
        endpoint.last_sync_error = str(exc)
        endpoint.save(
            update_fields=["last_synced_at", "last_sync_status", "last_sync_error"]
        )
        return DiscoverySyncResult(
            tenant_id=tenant.id,
            status="fetch_failed",
            errors=[{"path": "", "code": "fetch_failed", "message": str(exc)}],
        )

    errors = validate_discovery_payload(payload)
    payload_entry = TenantDiscoveryPayload.objects.create(
        tenant=tenant,
        schema_version=str(payload.get("schema_version", "")),
        payload=payload,
        is_valid=not errors,
        errors=errors,
    )

    if errors:
        endpoint.last_synced_at = payload_entry.fetched_at
        endpoint.last_sync_status = "invalid_schema"
        endpoint.last_sync_error = "schema_validation_failed"
        endpoint.save(
            update_fields=["last_synced_at", "last_sync_status", "last_sync_error"]
        )
        return DiscoverySyncResult(
            tenant_id=tenant.id,
            status="invalid_schema",
            errors=errors,
        )

    catalog_entries = payload.get("catalog", [])
    rbac = payload.get("rbac", {})
    users = payload.get("users", [])

    with transaction.atomic():
        CatalogServiceTask.objects.filter(tenant=tenant).delete()
        CapabilityCatalogEntry.objects.filter(tenant=tenant).delete()
        RbacRolePermission.objects.filter(tenant=tenant).delete()
        DirectoryUserRole.objects.filter(tenant=tenant).delete()
        RbacRole.objects.filter(tenant=tenant).delete()
        RbacPermission.objects.filter(tenant=tenant).delete()
        DirectoryUser.objects.filter(tenant=tenant).delete()

        catalog_map: dict[str, CapabilityCatalogEntry] = {}
        for entry in catalog_entries:
            catalog_entry = CapabilityCatalogEntry.objects.create(
                tenant=tenant,
                external_id=entry["id"],
                name=entry["name"],
                description=entry.get("description", ""),
                category=entry.get("category", ""),
                service_url=entry["service_url"],
                metadata=entry.get("metadata", {}),
            )
            catalog_map[entry["id"]] = catalog_entry
            for task in entry.get("service_tasks", []):
                CatalogServiceTask.objects.create(
                    tenant=tenant,
                    catalog_entry=catalog_entry,
                    external_id=task["id"],
                    name=task["name"],
                    url=task["url"],
                )

        role_map: dict[str, RbacRole] = {}
        for role in rbac.get("roles", []):
            role_obj = RbacRole.objects.create(
                tenant=tenant,
                external_id=role["id"],
                name=role["name"],
                description=role.get("description", ""),
            )
            role_map[role["id"]] = role_obj

        permission_map: dict[str, RbacPermission] = {}
        for permission in rbac.get("permissions", []):
            permission_obj = RbacPermission.objects.create(
                tenant=tenant,
                external_id=permission["id"],
                name=permission["name"],
                description=permission.get("description", ""),
            )
            permission_map[permission["id"]] = permission_obj

        for role_permission in rbac.get("role_permissions", []):
            RbacRolePermission.objects.create(
                tenant=tenant,
                role=role_map[role_permission["role_id"]],
                permission=permission_map[role_permission["permission_id"]],
            )

        for user in users:
            user_obj = DirectoryUser.objects.create(
                tenant=tenant,
                external_id=user["id"],
                email=user["email"],
                display_name=user.get("display_name", ""),
                is_active=user.get("is_active", True),
            )
            for role_id in user.get("role_ids", []):
                DirectoryUserRole.objects.create(
                    tenant=tenant,
                    user=user_obj,
                    role=role_map[role_id],
                )

        endpoint.last_synced_at = payload_entry.fetched_at
        endpoint.last_sync_status = "synced"
        endpoint.last_sync_error = ""
        endpoint.save(
            update_fields=["last_synced_at", "last_sync_status", "last_sync_error"]
        )

    return DiscoverySyncResult(tenant_id=tenant.id, status="synced", errors=[])
