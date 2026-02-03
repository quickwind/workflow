# pyright: reportMissingImports=false
import hashlib
import hmac
import json
import urllib.error
from collections.abc import Mapping
from typing import Any, cast
from urllib.request import Request, urlopen

from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response  # type: ignore[reportMissingImports]
from rest_framework.views import APIView  # type: ignore[reportMissingImports]

from .notifications import send_user_task_notification
from .bpmn import validate_bpmn_xml
from .models import (
    AuditEvent,
    AuditEventType,
    CapabilityCatalogEntry,
    CatalogServiceTask,
    DirectoryUser,
    RbacRole,
    TenantDiscoveryEndpoint,
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowGroup,
    WorkflowInstance,
    WorkflowInstanceStatus,
    ServiceTask,
    ServiceTaskCallbackIdempotency,
    ServiceTaskExecutionMode,
    ServiceTaskStatus,
    UserTask,
    UserTaskCompletionIdempotency,
    UserTaskStatus,
)
from .serializers import (
    AuditEventSerializer,
    CapabilityCatalogEntrySerializer,
    DiscoveryEndpointSerializer,
    ServiceTaskSerializer,
    ServiceTaskStartSerializer,
    UserTaskCompleteSerializer,
    UserTaskSerializer,
    WorkflowDefinitionUploadSerializer,
    WorkflowDefinitionSerializer,
    WorkflowGroupSerializer,
    WorkflowGroupTreeSerializer,
    WorkflowDefinitionVersionDetailSerializer,
    WorkflowDefinitionVersionSummarySerializer,
    WorkflowInstanceDetailSerializer,
    WorkflowInstanceSerializer,
    WorkflowInstanceStartSerializer,
)
from .workflow_runtime import (
    WorkflowRuntimeError,
    resume_workflow_from_state,
    start_workflow_from_definition,
)


class HealthView(APIView):
    """
    Public health check endpoint.
    Used for monitoring and load balancer health checks.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "status": "ok",
            }
        )


class DiscoveryEndpointView(APIView):
    """
    Manage the tenant's discovery endpoint configuration.
    Each tenant can have one discovery endpoint to sync automation capabilities and RBAC data.
    """

    def get(self, request):
        manager = cast(Any, TenantDiscoveryEndpoint)._default_manager
        endpoint = manager.filter(tenant=request.tenant).first()
        if endpoint is None:
            return Response({"endpoint_url": "", "has_api_key": False})
        serializer = DiscoveryEndpointSerializer(endpoint)
        return Response(serializer.data)

    def post(self, request):
        manager = cast(Any, TenantDiscoveryEndpoint)._default_manager
        endpoint = manager.filter(tenant=request.tenant).first()
        serializer = DiscoveryEndpointSerializer(instance=endpoint, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(tenant=request.tenant)
        return Response(serializer.data)


class CapabilityCatalogListView(ListAPIView):
    """
    Lists automation capabilities synced from the tenant's discovery endpoint.
    """

    serializer_class = CapabilityCatalogEntrySerializer

    def get_queryset(self):
        manager = cast(Any, CapabilityCatalogEntry)._default_manager
        return manager.filter(tenant=self.request.tenant)


class WorkflowDefinitionUploadView(APIView):
    """
    Upload a BPMN file to create or update a workflow definition.
    Validates the BPMN XML and creates a new immutable version record.
    """
    def post(self, request):
@@
class WorkflowGroupListCreateView(APIView):
    """
    List or create hierarchical workflow groups (folders).
    Groups are used to organize workflow definitions in the designer UI.
    """
    def get(self, request):
@@
class WorkflowGroupDetailView(APIView):
    """
    Retrieve, update, or delete a specific workflow group.
    Prevents deletion of non-empty groups.
    """
    def get(self, request, group_id: int):
@@
class WorkflowGroupTreeView(APIView):
    """
    Returns a recursive tree structure of all workflow groups for the tenant.
    Used for rendering the folder tree in the frontend designer.
    """
    def get(self, request):
@@
class WorkflowDefinitionListView(ListAPIView):
    """
    List all workflow definitions for a tenant.
    Supports filtering by group_id.
    """
    serializer_class = WorkflowDefinitionSerializer
@@
class WorkflowDefinitionDetailView(APIView):
    """
    Retrieve or update metadata of a specific workflow definition.
    """
    def get(self, request, process_key: str):
@@
class WorkflowDefinitionVersionDetailView(APIView):
    """
    Retrieve details of a specific version of a workflow definition.
    Includes the BPMN XML.
    """
    def get(self, request, process_key: str, version: int):
@@
class WorkflowInstanceStartView(APIView):
    """
    Start a new execution instance of a specific workflow definition version.
    Initializes the engine state and runs automatic tasks.
    """
    def post(self, request, process_key: str, version: int):
@@
class WorkflowInstanceListView(ListAPIView):
    """
    List all execution instances for a specific process key.
    """
    serializer_class = WorkflowInstanceSerializer
@@
class WorkflowInstanceDetailView(APIView):
    """
    Retrieve full details of a workflow instance, including its BPMN XML,
    current execution status, and a unified state object for the viewer.
    """
    def get(self, request, instance_id: int):
@@
class UserTaskListView(ListAPIView):
    """
    List pending UserTasks for a tenant.
    Can be filtered by workflow instance.
    """
    serializer_class = UserTaskSerializer
@@
class UserTaskActorRoleListView(ListAPIView):
    """
    List all UserTasks for a tenant, with optional filtering by status, actor, or role.
    Used for inbox views and task management.
    """
    serializer_class = UserTaskSerializer
@@
class AuditEventListView(ListAPIView):
    """
    Query the audit trail for workflow events.
    Filterable by workflow instance or business key.
    """
    serializer_class = AuditEventSerializer
@@
class UserTaskCompleteView(APIView):
    """
    Submit human input to complete a UserTask and continue workflow execution.
    Enforces idempotency using the 'Idempotency-Key' header.
    """
    def post(self, request, task_id: int):
@@
class ServiceTaskListView(ListAPIView):
    """
    List ServiceTask execution records for a tenant.
    """
    serializer_class = ServiceTaskSerializer
@@
class ServiceTaskStartView(APIView):
    """
    Initiate execution of an automated ServiceTask.
    Performs the REST API call to the tenant's system.
    """
    def post(self, request, task_id: int):
@@
class ServiceTaskCallbackView(APIView):
    """
    Webhook endpoint for async ServiceTasks to report completion.
    Verifies HMAC signature using the tenant's API key.
    """
    def post(self, request, task_id: int):

        raw_payload = request.data
        payload_data = None
        if isinstance(raw_payload, Mapping):
            payload_data = raw_payload.get("data", raw_payload.get("payload"))
        serializer = UserTaskCompleteSerializer(
            data={
                "actor": raw_payload.get("actor")
                if isinstance(raw_payload, Mapping)
                else None,
                "action": raw_payload.get("action")
                if isinstance(raw_payload, Mapping)
                else None,
                "payload": payload_data,
            }
        )
        serializer.is_valid(raise_exception=True)
        validated_data = cast(dict[str, Any], serializer.validated_data)
        actor = str(validated_data.get("actor", ""))
        action = str(validated_data.get("action", ""))
        action_data = validated_data.get("payload")
        if action_data is None:
            action_data = {}

        request_hash_payload = json.dumps(
            {
                "actor": actor,
                "action": action,
                "data": action_data,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        request_hash = hashlib.sha256(request_hash_payload.encode("utf-8")).hexdigest()
        idempotency_key = request.headers.get("Idempotency-Key")

        task_manager = cast(Any, UserTask)._default_manager
        idempotency_manager = cast(Any, UserTaskCompletionIdempotency)._default_manager

        with cast(Any, transaction).atomic():
            task = (
                task_manager.select_for_update()
                .filter(tenant=request.tenant, id=task_id)
                .first()
            )
            if task is None:
                return Response(
                    {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
                )

            idempotency_record = None
            if idempotency_key:
                idempotency_record = (
                    idempotency_manager.select_for_update()
                    .filter(tenant=request.tenant, idempotency_key=idempotency_key)
                    .first()
                )
                if idempotency_record is not None:
                    if (
                        idempotency_record.user_task_id != task.id
                        or idempotency_record.request_hash != request_hash
                    ):
                        return Response(
                            {"detail": "Idempotency key conflict."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    return Response(idempotency_record.response_payload)

            if task.status == UserTaskStatus.COMPLETED:
                response_payload = UserTaskSerializer(task).data
                if idempotency_key:
                    idempotency_manager.create(
                        tenant=request.tenant,
                        user_task=task,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        response_payload=response_payload,
                    )
                return Response(response_payload)

            task.status = UserTaskStatus.COMPLETED
            task.actor_identity = actor
            task.action = action
            task.action_data = action_data
            task.completed_at = timezone.now()
            task.save(
                update_fields=[
                    "status",
                    "actor_identity",
                    "action",
                    "action_data",
                    "completed_at",
                    "updated_at",
                ]
            )

            _create_audit_event(
                request.tenant,
                AuditEventType.USER_TASK_COMPLETE,
                actor_identity=actor,
                correlation_id=task.workflow_instance.correlation_id,
                business_key=task.workflow_instance.business_key,
                workflow_instance=task.workflow_instance,
                definition_version=task.workflow_instance.definition_version,
                payload={
                    "task_id": task.task_id,
                    "action": action,
                    "action_data": action_data,
                },
            )

            response_payload = UserTaskSerializer(task).data
            if idempotency_key:
                idempotency_manager.create(
                    tenant=request.tenant,
                    user_task=task,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_payload=response_payload,
                )

        return Response(response_payload)


def _coerce_payload(payload: Any | None) -> Any:
    if payload is None:
        return {}
    return payload


def _normalize_result_payload(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    return {"result": payload}


def _parse_json_body(raw_body: bytes) -> Any:
    if not raw_body:
        return {}
    try:
        return json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"raw": raw_body.decode("utf-8", errors="replace")}


def _create_audit_event(
    tenant: Any,
    event_type: str,
    actor_identity: str = "",
    correlation_id: str = "",
    business_key: str = "",
    workflow_instance: WorkflowInstance | None = None,
    definition_version: WorkflowDefinitionVersion | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    manager = cast(Any, AuditEvent)._default_manager
    manager.create(
        tenant=tenant,
        event_type=event_type,
        actor_identity=actor_identity,
        correlation_id=correlation_id,
        business_key=business_key,
        workflow_instance=workflow_instance,
        definition_version=definition_version,
        payload=payload or {},
    )


def _to_iso(dt: Any | None) -> str | None:
    return dt.isoformat() if dt else None


def _map_user_task_state(task: UserTask) -> dict[str, Any]:
    status = "completed" if task.status == UserTaskStatus.COMPLETED else "waiting"
    user = None
    if task.actor_identity:
        user = {"id": task.actor_identity, "name": task.actor_identity}
    return {
        "elementId": task.task_id,
        "status": status,
        "started_at": _to_iso(task.created_at),
        "completed_at": _to_iso(task.completed_at),
        "user": user,
        "input_data": {},
        "output_data": task.action_data or {},
    }


def _map_service_task_state(task: ServiceTask) -> dict[str, Any]:
    if task.status == ServiceTaskStatus.COMPLETED:
        status = "completed"
    elif task.status == ServiceTaskStatus.FAILED:
        status = "failed"
    elif task.status in (ServiceTaskStatus.WAITING, ServiceTaskStatus.IN_PROGRESS):
        status = "in_progress"
    else:
        status = "waiting"

    element_id = task.element_id or task.task_id
    return {
        "elementId": element_id,
        "status": status,
        "started_at": _to_iso(task.started_at or task.created_at),
        "completed_at": _to_iso(task.completed_at),
        "user": None,
        "input_data": task.request_payload or {},
        "output_data": task.response_payload or {},
    }


def _build_instance_state(instance: WorkflowInstance) -> dict[str, Any]:
    user_tasks = instance.user_tasks.all().order_by("created_at")
    service_tasks = instance.service_tasks.all().order_by("created_at")

    tasks: list[dict[str, Any]] = [
        *[_map_user_task_state(task) for task in user_tasks],
        *[_map_service_task_state(task) for task in service_tasks],
    ]

    return {
        "tasks": tasks,
        "sequenceFlows": [],
    }


def _callback_signature(raw_key: str, body: bytes, timestamp: str) -> str:
    signature_payload = body + timestamp.encode("utf-8")
    return hmac.new(
        raw_key.encode("utf-8"), signature_payload, hashlib.sha256
    ).hexdigest()


def _callback_request_hash(body: bytes, timestamp: str) -> str:
    signature_payload = body + timestamp.encode("utf-8")
    return hashlib.sha256(signature_payload).hexdigest()


def _build_service_task_payload(
    instance: WorkflowInstance,
    service_task: ServiceTask,
    payload: Any,
    callback_url: str,
    execution_mode: str,
) -> dict[str, Any]:
    instance_id = cast(Any, instance).id
    service_task_id = cast(Any, service_task).id
    context: dict[str, Any] = {
        "workflow_instance_id": instance_id,
        "service_task_id": service_task_id,
        "task_id": service_task.task_id,
        "correlation_id": instance.correlation_id,
        "execution_mode": execution_mode,
    }
    if execution_mode == ServiceTaskExecutionMode.ASYNC and callback_url:
        context["callback_url"] = callback_url
    return {
        "payload": payload,
        "context": context,
    }


def _perform_service_task_request(
    url: str,
    payload: dict[str, Any],
    correlation_id: str,
) -> tuple[int, Any, str]:
    request_body = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    request = Request(url, data=request_body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json")
    if correlation_id:
        request.add_header("X-Correlation-Id", correlation_id)
    try:
        with urlopen(request, timeout=10) as response:
            response_body = response.read().decode("utf-8")
            response_payload = _parse_json_body(response_body.encode("utf-8"))
            return int(getattr(response, "status", 200)), response_payload, ""
    except urllib.error.HTTPError as exc:
        response_body = ""
        try:
            response_body = exc.read().decode("utf-8")
        except Exception:
            response_body = ""
        response_payload = _parse_json_body(response_body.encode("utf-8"))
        return (
            int(getattr(exc, "code", 500)),
            response_payload,
            "service_task_http_error",
        )
    except urllib.error.URLError as exc:
        return 0, {}, str(exc)


def _ensure_catalog_service_task_binding(
    tenant: Any,
    service_task: ServiceTask,
    catalog_entry_id: str,
    catalog_task_id: str,
) -> CatalogServiceTask | None:
    if not catalog_entry_id or not catalog_task_id:
        return None
    catalog_manager = cast(Any, CatalogServiceTask)._default_manager
    return (
        catalog_manager.select_related("catalog_entry")
        .filter(
            tenant=tenant,
            catalog_entry__external_id=catalog_entry_id,
            external_id=catalog_task_id,
        )
        .first()
    )


def _find_catalog_binding_from_definition(
    tenant: Any,
    definition_version: WorkflowDefinitionVersion,
    element_id: str,
    element_name: str,
) -> CatalogServiceTask | None:
    placeholders = definition_version.catalog_binding_placeholders or []
    if not isinstance(placeholders, list):
        return None
    catalog_keys = (
        "catalog_entry_id",
        "catalogentryid",
        "catalog_id",
        "catalogid",
        "capability_id",
        "capabilityid",
    )
    task_keys = (
        "service_task_id",
        "servicetaskid",
        "task_id",
        "taskid",
        "service_task",
        "servicetask",
    )

    for placeholder in placeholders:
        if not isinstance(placeholder, dict):
            continue
        if element_id and placeholder.get("element_id") != element_id:
            if element_name and placeholder.get("element_name") != element_name:
                continue
            if element_name and placeholder.get("element_name") == element_name:
                pass
        attrs = placeholder.get("placeholders")
        if not isinstance(attrs, dict):
            continue
        lowered = {str(key).lower(): str(value) for key, value in attrs.items()}
        catalog_entry_id = next(
            (lowered[key] for key in catalog_keys if key in lowered), ""
        )
        catalog_task_id = next(
            (lowered[key] for key in task_keys if key in lowered), ""
        )
        if not catalog_entry_id or not catalog_task_id:
            continue
        catalog_manager = cast(Any, CatalogServiceTask)._default_manager
        catalog_task = (
            catalog_manager.select_related("catalog_entry")
            .filter(
                tenant=tenant,
                catalog_entry__external_id=catalog_entry_id,
                external_id=catalog_task_id,
            )
            .first()
        )
        if catalog_task is not None:
            return catalog_task
    return None


def _create_user_tasks_for_instance(
    tenant: Any,
    instance: WorkflowInstance,
    waiting_user_tasks: list[Any],
) -> None:
    task_manager = cast(Any, UserTask)._default_manager
    task_ids = [task.task_id for task in waiting_user_tasks]
    existing = set(
        task_manager.filter(
            tenant=tenant,
            workflow_instance=instance,
            task_id__in=task_ids,
        ).values_list("task_id", flat=True)
    )
    new_tasks = [
        UserTask(
            tenant=tenant,
            workflow_instance=instance,
            task_id=task.task_id,
            name=task.name,
            task_type=task.task_type,
            status=UserTaskStatus.PENDING,
        )
        for task in waiting_user_tasks
        if task.task_id not in existing
    ]
    if new_tasks:
        task_manager.bulk_create(new_tasks)
        for user_task in new_tasks:
            send_user_task_notification(user_task)


def _create_service_tasks_for_instance(
    tenant: Any,
    instance: WorkflowInstance,
    waiting_service_tasks: list[Any],
) -> None:
    task_manager = cast(Any, ServiceTask)._default_manager
    task_ids = [task.task_id for task in waiting_service_tasks]
    existing = set(
        task_manager.filter(
            tenant=tenant,
            workflow_instance=instance,
            task_id__in=task_ids,
        ).values_list("task_id", flat=True)
    )
    new_tasks: list[ServiceTask] = []
    for task in waiting_service_tasks:
        if task.task_id in existing:
            continue
        catalog_task = _find_catalog_binding_from_definition(
            tenant,
            cast(Any, instance).definition_version,
            task.element_id,
            task.element_name,
        )
        new_tasks.append(
            ServiceTask(
                tenant=tenant,
                workflow_instance=instance,
                task_id=task.task_id,
                name=task.name,
                task_type=task.task_type,
                element_id=task.element_id,
                element_name=task.element_name,
                status=ServiceTaskStatus.PENDING,
                catalog_service_task=catalog_task,
            )
        )
    if new_tasks:
        task_manager.bulk_create(new_tasks)


class ServiceTaskListView(ListAPIView):
    serializer_class = ServiceTaskSerializer

    def get_queryset(self):
        manager = cast(Any, ServiceTask)._default_manager
        queryset = manager.filter(tenant=self.request.tenant)
        workflow_instance_id = self.request.query_params.get("workflow_instance_id")
        if workflow_instance_id:
            queryset = queryset.filter(workflow_instance_id=workflow_instance_id)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        return queryset.order_by("created_at")


class ServiceTaskStartView(APIView):
    def post(self, request, task_id: int):
        serializer = ServiceTaskStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = cast(dict[str, Any], serializer.validated_data)
        catalog_entry_id = str(validated_data.get("catalog_entry_id", "")).strip()
        catalog_task_id = str(validated_data.get("service_task_id", "")).strip()
        execution_mode = str(validated_data.get("execution_mode", "sync"))
        payload = _coerce_payload(validated_data.get("payload"))

        task_manager = cast(Any, ServiceTask)._default_manager
        with cast(Any, transaction).atomic():
            service_task = (
                task_manager.select_for_update()
                .select_related("workflow_instance", "catalog_service_task")
                .filter(tenant=request.tenant, id=task_id)
                .first()
            )
            if service_task is None:
                return Response(
                    {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
                )
            if service_task.status not in {
                ServiceTaskStatus.PENDING,
                ServiceTaskStatus.FAILED,
            }:
                return Response(ServiceTaskSerializer(service_task).data)
            bound_task = None
            if service_task.catalog_service_task is not None:
                bound_task = cast(Any, service_task.catalog_service_task)
                if (
                    catalog_entry_id
                    and str(bound_task.catalog_entry.external_id) != catalog_entry_id
                ):
                    return Response(
                        {"detail": "Catalog binding conflict."},
                        status=status.HTTP_409_CONFLICT,
                    )
                if catalog_task_id and str(bound_task.external_id) != catalog_task_id:
                    return Response(
                        {"detail": "Catalog binding conflict."},
                        status=status.HTTP_409_CONFLICT,
                    )
                bound_task = cast(CatalogServiceTask, bound_task)
            if bound_task is None:
                bound_task = _ensure_catalog_service_task_binding(
                    request.tenant, service_task, catalog_entry_id, catalog_task_id
                )
            if bound_task is None:
                bound_task = _find_catalog_binding_from_definition(
                    request.tenant,
                    cast(Any, service_task.workflow_instance).definition_version,
                    service_task.element_id,
                    service_task.element_name,
                )
            if bound_task is None:
                return Response(
                    {
                        "code": "missing_catalog_binding",
                        "message": "Catalog binding is required for service tasks.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            service_task.catalog_service_task = bound_task
            service_task.request_payload = payload
            service_task.execution_mode = execution_mode
            service_task.status = ServiceTaskStatus.IN_PROGRESS
            service_task.started_at = timezone.now()
            service_task.last_error = ""
            service_task.save(
                update_fields=[
                    "catalog_service_task",
                    "request_payload",
                    "execution_mode",
                    "status",
                    "started_at",
                    "last_error",
                    "updated_at",
                ]
            )

        instance = service_task.workflow_instance
        bound_task = cast(CatalogServiceTask, bound_task)
        catalog_entry = cast(Any, bound_task.catalog_entry)
        _create_audit_event(
            request.tenant,
            AuditEventType.SERVICE_TASK_START,
            correlation_id=instance.correlation_id,
            business_key=instance.business_key,
            workflow_instance=instance,
            definition_version=instance.definition_version,
            payload={
                "task_id": service_task.task_id,
                "execution_mode": execution_mode,
                "catalog_entry_id": str(catalog_entry.external_id),
                "service_task_id": str(bound_task.external_id),
            },
        )
        callback_url = ""
        if execution_mode == ServiceTaskExecutionMode.ASYNC:
            callback_path = reverse(
                "service-task-callback", kwargs={"task_id": task_id}
            )
            callback_url = request.build_absolute_uri(callback_path)
        request_payload = _build_service_task_payload(
            instance,
            service_task,
            payload,
            callback_url,
            execution_mode,
        )
        status_code, response_payload, error = _perform_service_task_request(
            str(bound_task.url),
            request_payload,
            instance.correlation_id,
        )
        if status_code and status_code >= 400:
            error = error or "service_task_http_error"

        with cast(Any, transaction).atomic():
            service_task = (
                task_manager.select_for_update()
                .select_related("workflow_instance")
                .filter(tenant=request.tenant, id=task_id)
                .first()
            )
            if service_task is None:
                return Response(
                    {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
                )
            if error:
                service_task.status = ServiceTaskStatus.FAILED
                service_task.last_error = error
                service_task.response_payload = _normalize_result_payload(
                    response_payload
                )
                service_task.completed_at = timezone.now()
                service_task.save(
                    update_fields=[
                        "status",
                        "last_error",
                        "response_payload",
                        "completed_at",
                        "updated_at",
                    ]
                )
                instance = service_task.workflow_instance
                instance.status = WorkflowInstanceStatus.FAILED
                instance.save(update_fields=["status", "updated_at"])
                return Response(ServiceTaskSerializer(service_task).data, status=502)

            if execution_mode == ServiceTaskExecutionMode.ASYNC:
                service_task.status = ServiceTaskStatus.WAITING
                service_task.response_payload = _normalize_result_payload(
                    response_payload
                )
                service_task.save(
                    update_fields=["status", "response_payload", "updated_at"]
                )
                return Response(ServiceTaskSerializer(service_task).data)

            result_payload = _normalize_result_payload(response_payload)
            run_result = resume_workflow_from_state(
                instance.definition_version,
                instance.serialized_state,
                completed_task_id=service_task.task_id,
                task_result=result_payload,
                correlation_id=instance.correlation_id,
                business_key=instance.business_key,
            )
            instance.status = run_result.status
            instance.serialized_state = run_result.serialized_state
            instance.save(update_fields=["status", "serialized_state", "updated_at"])

            _create_user_tasks_for_instance(
                request.tenant, instance, run_result.waiting_user_tasks
            )
            _create_service_tasks_for_instance(
                request.tenant, instance, run_result.waiting_service_tasks
            )

            service_task.status = ServiceTaskStatus.COMPLETED
            service_task.response_payload = result_payload
            service_task.completed_at = timezone.now()
            service_task.save(
                update_fields=[
                    "status",
                    "response_payload",
                    "completed_at",
                    "updated_at",
                ]
            )

        return Response(ServiceTaskSerializer(service_task).data)


class ServiceTaskCallbackView(APIView):
    def post(self, request, task_id: int):
        raw_key = request.headers.get("X-Tenant-Api-Key", "")
        timestamp = request.headers.get("X-Callback-Timestamp", "")
        signature = request.headers.get("X-Callback-Signature", "")
        if not raw_key:
            return Response(
                {"detail": "Missing tenant API key."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not timestamp or not signature:
            return Response(
                {"detail": "Missing callback signature headers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        body = request.body or b""
        expected_signature = _callback_signature(raw_key, body, timestamp)
        if not hmac.compare_digest(expected_signature, signature):
            return Response(
                {"detail": "Invalid callback signature."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        idempotency_key = request.headers.get("Idempotency-Key")
        request_hash = _callback_request_hash(body, timestamp)

        task_manager = cast(Any, ServiceTask)._default_manager
        idempotency_manager = cast(Any, ServiceTaskCallbackIdempotency)._default_manager

        with cast(Any, transaction).atomic():
            service_task = (
                task_manager.select_for_update()
                .select_related("workflow_instance")
                .filter(tenant=request.tenant, id=task_id)
                .first()
            )
            if service_task is None:
                return Response(
                    {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
                )

            if idempotency_key:
                idempotency_record = (
                    idempotency_manager.select_for_update()
                    .filter(tenant=request.tenant, idempotency_key=idempotency_key)
                    .first()
                )
                if idempotency_record is not None:
                    if (
                        idempotency_record.service_task_id != service_task.id
                        or idempotency_record.request_hash != request_hash
                    ):
                        return Response(
                            {"detail": "Idempotency key conflict."},
                            status=status.HTTP_409_CONFLICT,
                        )
                    return Response(idempotency_record.response_payload)

            if service_task.status == ServiceTaskStatus.COMPLETED:
                response_payload = ServiceTaskSerializer(service_task).data
                if idempotency_key:
                    idempotency_manager.create(
                        tenant=request.tenant,
                        service_task=service_task,
                        idempotency_key=idempotency_key,
                        request_hash=request_hash,
                        response_payload=response_payload,
                    )
                return Response(response_payload)

        callback_payload = _parse_json_body(body)
        callback_status = str(callback_payload.get("status", "")).lower()
        result_data = callback_payload.get("data")
        if result_data is None:
            result_data = callback_payload.get("result", callback_payload)

        with cast(Any, transaction).atomic():
            service_task = (
                task_manager.select_for_update()
                .select_related("workflow_instance")
                .filter(tenant=request.tenant, id=task_id)
                .first()
            )
            if service_task is None:
                return Response(
                    {"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND
                )
            instance = service_task.workflow_instance
            if callback_status == "failed":
                service_task.status = ServiceTaskStatus.FAILED
                service_task.last_error = str(callback_payload.get("error", ""))
                service_task.response_payload = _normalize_result_payload(result_data)
                service_task.completed_at = timezone.now()
                service_task.save(
                    update_fields=[
                        "status",
                        "last_error",
                        "response_payload",
                        "completed_at",
                        "updated_at",
                    ]
                )
                instance.status = WorkflowInstanceStatus.FAILED
                instance.save(update_fields=["status", "updated_at"])
                response_payload = ServiceTaskSerializer(service_task).data
            else:
                result_payload = _normalize_result_payload(result_data)
                run_result = resume_workflow_from_state(
                    instance.definition_version,
                    instance.serialized_state,
                    completed_task_id=service_task.task_id,
                    task_result=result_payload,
                    correlation_id=instance.correlation_id,
                    business_key=instance.business_key,
                )
                instance.status = run_result.status
                instance.serialized_state = run_result.serialized_state
                instance.save(
                    update_fields=["status", "serialized_state", "updated_at"]
                )
                _create_user_tasks_for_instance(
                    request.tenant, instance, run_result.waiting_user_tasks
                )
                _create_service_tasks_for_instance(
                    request.tenant, instance, run_result.waiting_service_tasks
                )
                service_task.status = ServiceTaskStatus.COMPLETED
                service_task.response_payload = result_payload
                service_task.completed_at = timezone.now()
                service_task.save(
                    update_fields=[
                        "status",
                        "response_payload",
                        "completed_at",
                        "updated_at",
                    ]
                )
                response_payload = ServiceTaskSerializer(service_task).data

            _create_audit_event(
                request.tenant,
                AuditEventType.SERVICE_TASK_CALLBACK,
                correlation_id=instance.correlation_id,
                business_key=instance.business_key,
                workflow_instance=instance,
                definition_version=instance.definition_version,
                payload={
                    "task_id": service_task.task_id,
                    "status": service_task.status,
                    "callback_status": callback_status,
                    "error": service_task.last_error,
                },
            )
            if idempotency_key:
                idempotency_manager.create(
                    tenant=request.tenant,
                    service_task=service_task,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                    response_payload=response_payload,
                )

        return Response(response_payload)


health_view = cast(Any, HealthView).as_view()
discovery_endpoint_view = cast(Any, DiscoveryEndpointView).as_view()
capability_catalog_list_view = cast(Any, CapabilityCatalogListView).as_view()
workflow_definition_upload_view = cast(Any, WorkflowDefinitionUploadView).as_view()
workflow_definition_version_detail_view = cast(
    Any, WorkflowDefinitionVersionDetailView
).as_view()
workflow_instance_start_view = cast(Any, WorkflowInstanceStartView).as_view()
workflow_instance_detail_view = cast(Any, WorkflowInstanceDetailView).as_view()
user_task_list_view = cast(Any, UserTaskListView).as_view()
user_task_actor_role_list_view = cast(Any, UserTaskActorRoleListView).as_view()
audit_event_list_view = cast(Any, AuditEventListView).as_view()
user_task_complete_view = cast(Any, UserTaskCompleteView).as_view()
service_task_list_view = cast(Any, ServiceTaskListView).as_view()
service_task_start_view = cast(Any, ServiceTaskStartView).as_view()
service_task_callback_view = cast(Any, ServiceTaskCallbackView).as_view()

workflow_group_list_create_view = cast(Any, WorkflowGroupListCreateView).as_view()
workflow_group_detail_view = cast(Any, WorkflowGroupDetailView).as_view()
workflow_group_tree_view = cast(Any, WorkflowGroupTreeView).as_view()

workflow_definition_list_view = cast(Any, WorkflowDefinitionListView).as_view()
workflow_definition_detail_view = cast(Any, WorkflowDefinitionDetailView).as_view()

workflow_instance_list_view = cast(Any, WorkflowInstanceListView).as_view()


# Create your views here.
