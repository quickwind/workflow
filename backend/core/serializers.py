from __future__ import annotations

from typing import Any, cast

from rest_framework import serializers

from .models import (
    AuditEvent,
    CapabilityCatalogEntry,
    CatalogServiceTask,
    TenantDiscoveryEndpoint,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    UserTask,
    UserTaskStatus,
    ServiceTask,
    ServiceTaskStatus,
)


class DiscoveryEndpointSerializer(serializers.ModelSerializer):
    has_api_key = serializers.SerializerMethodField()

    class Meta:
        model = TenantDiscoveryEndpoint
        fields = ("endpoint_url", "api_key", "has_api_key")
        extra_kwargs = {"api_key": {"write_only": True}}

    def get_has_api_key(self, obj: TenantDiscoveryEndpoint) -> bool:
        return bool(obj.api_key)


class CatalogServiceTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = CatalogServiceTask
        fields = ("external_id", "name", "url")


class CapabilityCatalogEntrySerializer(serializers.ModelSerializer):
    service_tasks = CatalogServiceTaskSerializer(many=True, read_only=True)

    class Meta:
        model = CapabilityCatalogEntry
        fields = (
            "external_id",
            "name",
            "description",
            "category",
            "service_url",
            "metadata",
            "service_tasks",
        )


class WorkflowDefinitionUploadSerializer(serializers.Serializer):
    bpmn = serializers.FileField()


class WorkflowDefinitionVersionSummarySerializer(serializers.ModelSerializer):
    process_key = serializers.CharField(source="definition.process_key", read_only=True)

    class Meta:
        model = WorkflowDefinitionVersion
        fields = (
            "process_key",
            "version",
            "form_schema_refs",
            "catalog_binding_placeholders",
            "created_at",
        )
        read_only_fields = fields


class WorkflowDefinitionVersionDetailSerializer(serializers.ModelSerializer):
    process_key = serializers.CharField(source="definition.process_key", read_only=True)

    class Meta:
        model = WorkflowDefinitionVersion
        fields = (
            "process_key",
            "version",
            "bpmn_xml",
            "form_schema_refs",
            "catalog_binding_placeholders",
            "created_at",
        )
        read_only_fields = fields


class WorkflowInstanceStartSerializer(serializers.Serializer):
    correlation_id = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )
    business_key = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )


class WorkflowInstanceSerializer(serializers.ModelSerializer):
    process_key = serializers.CharField(
        source="definition_version.definition.process_key", read_only=True
    )
    version = serializers.IntegerField(
        source="definition_version.version", read_only=True
    )

    class Meta:
        model = WorkflowInstance
        fields = (
            "id",
            "process_key",
            "version",
            "status",
            "correlation_id",
            "business_key",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class WorkflowInstanceDetailSerializer(serializers.ModelSerializer):
    process_key = serializers.CharField(
        source="definition_version.definition.process_key", read_only=True
    )
    version = serializers.IntegerField(
        source="definition_version.version", read_only=True
    )
    active_user_tasks = serializers.SerializerMethodField()
    active_service_tasks = serializers.SerializerMethodField()

    class Meta:
        model = WorkflowInstance
        fields = (
            "id",
            "process_key",
            "version",
            "status",
            "correlation_id",
            "business_key",
            "created_at",
            "updated_at",
            "active_user_tasks",
            "active_service_tasks",
        )
        read_only_fields = fields

    def get_active_user_tasks(self, obj: WorkflowInstance):
        instance = cast(Any, obj)
        queryset = instance.user_tasks.filter(
            tenant=obj.tenant,
            status=UserTaskStatus.PENDING,
        ).order_by("created_at")
        return UserTaskSerializer(queryset, many=True).data

    def get_active_service_tasks(self, obj: WorkflowInstance):
        instance = cast(Any, obj)
        queryset = instance.service_tasks.filter(
            tenant=obj.tenant,
            status__in=[
                ServiceTaskStatus.PENDING,
                ServiceTaskStatus.IN_PROGRESS,
                ServiceTaskStatus.WAITING,
            ],
        ).order_by("created_at")
        return ServiceTaskSerializer(queryset, many=True).data


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = (
            "id",
            "event_type",
            "actor_identity",
            "correlation_id",
            "business_key",
            "workflow_instance_id",
            "definition_version_id",
            "payload",
            "created_at",
        )
        read_only_fields = fields


class UserTaskSerializer(serializers.ModelSerializer):
    process_key = serializers.CharField(
        source="workflow_instance.definition_version.definition.process_key",
        read_only=True,
    )
    workflow_version = serializers.IntegerField(
        source="workflow_instance.definition_version.version", read_only=True
    )
    workflow_instance_status = serializers.CharField(
        source="workflow_instance.status", read_only=True
    )

    class Meta:
        model = UserTask
        fields = (
            "id",
            "task_id",
            "name",
            "task_type",
            "status",
            "actor_identity",
            "action",
            "action_data",
            "completed_at",
            "workflow_instance_id",
            "workflow_instance_status",
            "process_key",
            "workflow_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class ServiceTaskSerializer(serializers.ModelSerializer):
    process_key = serializers.CharField(
        source="workflow_instance.definition_version.definition.process_key",
        read_only=True,
    )
    workflow_version = serializers.IntegerField(
        source="workflow_instance.definition_version.version", read_only=True
    )
    workflow_instance_status = serializers.CharField(
        source="workflow_instance.status", read_only=True
    )
    catalog_entry_id = serializers.CharField(
        source="catalog_service_task.catalog_entry.external_id", read_only=True
    )
    catalog_service_task_id = serializers.CharField(
        source="catalog_service_task.external_id", read_only=True
    )

    class Meta:
        model = ServiceTask
        fields = (
            "id",
            "task_id",
            "name",
            "task_type",
            "element_id",
            "element_name",
            "status",
            "execution_mode",
            "catalog_entry_id",
            "catalog_service_task_id",
            "started_at",
            "completed_at",
            "workflow_instance_id",
            "workflow_instance_status",
            "process_key",
            "workflow_version",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class UserTaskCompleteSerializer(serializers.Serializer):
    actor = serializers.CharField(max_length=200)
    action = serializers.CharField(max_length=200)
    payload = serializers.JSONField(required=False)


class ServiceTaskStartSerializer(serializers.Serializer):
    catalog_entry_id = serializers.CharField(
        max_length=120, required=False, allow_blank=True
    )
    service_task_id = serializers.CharField(
        max_length=120, required=False, allow_blank=True
    )
    execution_mode = serializers.ChoiceField(choices=["sync", "async"], required=False)
    payload = serializers.JSONField(required=False)
