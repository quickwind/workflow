from __future__ import annotations

import hashlib
from typing import Any, cast

from django.db import models


class Tenant(models.Model):
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TenantScopedModel(models.Model):
    tenant = models.ForeignKey(
        Tenant, on_delete=models.PROTECT, related_name="%(class)ss"
    )

    class Meta:
        abstract = True


class TenantApiKey(TenantScopedModel):
    name = models.CharField(max_length=120, blank=True)
    key_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def hash_key(raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    @classmethod
    def authenticate(cls, raw_key: str) -> "TenantApiKey | None":
        key_hash = cls.hash_key(raw_key)
        manager = cast(Any, TenantApiKey)._default_manager
        result = manager.select_related("tenant").filter(key_hash=key_hash).first()
        return cast("TenantApiKey | None", result)


class TenantDiscoveryEndpoint(TenantScopedModel):
    endpoint_url = models.URLField(max_length=500)
    api_key = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=40, blank=True)
    last_sync_error = models.TextField(blank=True)


class TenantDiscoveryPayload(TenantScopedModel):
    fetched_at = models.DateTimeField(auto_now_add=True)
    schema_version = models.CharField(max_length=32)
    payload = models.JSONField()
    is_valid = models.BooleanField()
    errors = models.JSONField(default=list, blank=True)


class CapabilityCatalogEntry(TenantScopedModel):
    external_id = models.CharField(max_length=120)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=120, blank=True)
    service_url = models.URLField(max_length=500)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_id"],
                name="uniq_catalog_entry_per_tenant",
            )
        ]


class CatalogServiceTask(TenantScopedModel):
    catalog_entry = models.ForeignKey(
        CapabilityCatalogEntry, on_delete=models.CASCADE, related_name="service_tasks"
    )
    external_id = models.CharField(max_length=120)
    name = models.CharField(max_length=200)
    url = models.URLField(max_length=500)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "catalog_entry", "external_id"],
                name="uniq_service_task_per_entry",
            )
        ]


class RbacRole(TenantScopedModel):
    external_id = models.CharField(max_length=120)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_id"],
                name="uniq_role_per_tenant",
            )
        ]


class RbacPermission(TenantScopedModel):
    external_id = models.CharField(max_length=120)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_id"],
                name="uniq_permission_per_tenant",
            )
        ]


class RbacRolePermission(TenantScopedModel):
    role = models.ForeignKey(
        "RbacRole", on_delete=models.CASCADE, related_name="role_permissions"
    )
    permission = models.ForeignKey(
        "RbacPermission", on_delete=models.CASCADE, related_name="role_permissions"
    )

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "role", "permission"],
                name="uniq_role_permission_per_tenant",
            )
        ]


class DirectoryUser(TenantScopedModel):
    external_id = models.CharField(max_length=120)
    email = models.EmailField(max_length=254)
    display_name = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_id"],
                name="uniq_directory_user_per_tenant",
            )
        ]


class DirectoryUserRole(TenantScopedModel):
    user = models.ForeignKey(
        "DirectoryUser", on_delete=models.CASCADE, related_name="user_roles"
    )
    role = models.ForeignKey(
        "RbacRole", on_delete=models.CASCADE, related_name="user_roles"
    )

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "role"],
                name="uniq_user_role_per_tenant",
            )
        ]


class WorkflowDefinition(TenantScopedModel):
    process_key = models.CharField(max_length=200)
    name = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "process_key"],
                name="uniq_workflow_definition_per_tenant",
            )
        ]


class WorkflowDefinitionVersion(TenantScopedModel):
    definition = models.ForeignKey(
        WorkflowDefinition, on_delete=models.CASCADE, related_name="versions"
    )
    version = models.PositiveIntegerField()
    bpmn_xml = models.TextField()
    form_schema_refs = models.JSONField(default=list, blank=True)
    catalog_binding_placeholders = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "definition", "version"],
                name="uniq_workflow_definition_version_per_tenant",
            )
        ]


class WorkflowInstanceStatus(models.TextChoices):
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowInstance(TenantScopedModel):
    definition_version = models.ForeignKey(
        WorkflowDefinitionVersion,
        on_delete=models.PROTECT,
        related_name="instances",
    )
    status = models.CharField(
        max_length=20,
        choices=WorkflowInstanceStatus.choices,
        default=WorkflowInstanceStatus.RUNNING,
    )
    correlation_id = models.CharField(max_length=200, blank=True)
    business_key = models.CharField(max_length=200, blank=True)
    serialized_state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AuditEventType(models.TextChoices):
    DEFINITION_UPLOAD = "definition_upload"
    INSTANCE_START = "instance_start"
    USER_TASK_COMPLETE = "user_task_complete"
    SERVICE_TASK_START = "service_task_start"
    SERVICE_TASK_CALLBACK = "service_task_callback"


class AuditEvent(TenantScopedModel):
    event_type = models.CharField(max_length=120, choices=AuditEventType.choices)
    actor_identity = models.CharField(max_length=200, blank=True)
    correlation_id = models.CharField(max_length=200, blank=True)
    business_key = models.CharField(max_length=200, blank=True)
    workflow_instance = models.ForeignKey(
        WorkflowInstance,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    definition_version = models.ForeignKey(
        WorkflowDefinitionVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_events",
    )
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        indexes = [
            models.Index(fields=["tenant", "workflow_instance"]),
            models.Index(fields=["tenant", "business_key"]),
            models.Index(fields=["tenant", "correlation_id"]),
            models.Index(fields=["tenant", "created_at"]),
        ]


class UserTaskStatus(models.TextChoices):
    PENDING = "pending"
    COMPLETED = "completed"


class UserTask(TenantScopedModel):
    workflow_instance = models.ForeignKey(
        WorkflowInstance, on_delete=models.CASCADE, related_name="user_tasks"
    )
    task_id = models.CharField(max_length=120)
    name = models.CharField(max_length=200, blank=True)
    task_type = models.CharField(max_length=120, blank=True)
    status = models.CharField(
        max_length=20,
        choices=UserTaskStatus.choices,
        default=UserTaskStatus.PENDING,
    )
    actor_identity = models.CharField(max_length=200, blank=True)
    action = models.CharField(max_length=200, blank=True)
    action_data = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workflow_instance", "task_id"],
                name="uniq_user_task_per_instance",
            )
        ]


class UserTaskCompletionIdempotency(TenantScopedModel):
    user_task = models.ForeignKey(
        UserTask, on_delete=models.CASCADE, related_name="idempotency_records"
    )
    idempotency_key = models.CharField(max_length=200)
    request_hash = models.CharField(max_length=64)
    response_payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uniq_user_task_idempotency_per_tenant",
            )
        ]


class ServiceTaskStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    IN_PROGRESS = "in_progress", "In progress"
    WAITING = "waiting", "Waiting"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class ServiceTaskExecutionMode(models.TextChoices):
    SYNC = "sync"
    ASYNC = "async"


class ServiceTask(TenantScopedModel):
    workflow_instance = models.ForeignKey(
        WorkflowInstance, on_delete=models.CASCADE, related_name="service_tasks"
    )
    task_id = models.CharField(max_length=120)
    name = models.CharField(max_length=200, blank=True)
    task_type = models.CharField(max_length=120, blank=True)
    element_id = models.CharField(max_length=200, blank=True)
    element_name = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ServiceTaskStatus.choices,
        default=ServiceTaskStatus.PENDING,
    )
    execution_mode = models.CharField(
        max_length=10,
        choices=ServiceTaskExecutionMode.choices,
        blank=True,
    )
    catalog_service_task = models.ForeignKey(
        CatalogServiceTask,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="service_task_executions",
    )
    request_payload = models.JSONField(default=dict, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "workflow_instance", "task_id"],
                name="uniq_service_task_per_instance",
            )
        ]


class ServiceTaskCallbackIdempotency(TenantScopedModel):
    service_task = models.ForeignKey(
        ServiceTask, on_delete=models.CASCADE, related_name="callback_idempotency"
    )
    idempotency_key = models.CharField(max_length=200)
    request_hash = models.CharField(max_length=64)
    response_payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                name="uniq_service_task_callback_idempotency_per_tenant",
            )
        ]
