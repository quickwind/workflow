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
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {
                "status": "ok",
            }
        )


class DiscoveryEndpointView(APIView):
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
    serializer_class = CapabilityCatalogEntrySerializer

    def get_queryset(self):
        manager = cast(Any, CapabilityCatalogEntry)._default_manager
        return manager.filter(tenant=self.request.tenant)


class WorkflowDefinitionUploadView(APIView):
    def post(self, request):
        serializer = WorkflowDefinitionUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = cast(dict[str, Any], serializer.validated_data)
        upload = validated_data.get("bpmn")
        if upload is None:
            return Response(
                {
                    "code": "invalid_bpmn",
                    "errors": [
                        {
                            "path": "bpmn",
                            "code": "required",
                            "message": "BPMN file is required.",
                        }
                    ],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_payload = upload.read()
        if isinstance(raw_payload, bytes):
            try:
                xml_text = raw_payload.decode("utf-8")
            except UnicodeDecodeError:
                return Response(
                    {
                        "code": "invalid_bpmn_xml",
                        "errors": [
                            {
                                "path": "",
                                "code": "invalid_bpmn_xml",
                                "message": "BPMN XML must be UTF-8.",
                            }
                        ],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            xml_text = str(raw_payload)

        snapshot, errors = validate_bpmn_xml(xml_text)
        if errors:
            has_unsupported = False
            for error in errors:
                if (
                    isinstance(error, dict)
                    and error.get("code") == "unsupported_bpmn_element"
                ):
                    has_unsupported = True
                    break
            code = "unsupported_bpmn_element" if has_unsupported else "invalid_bpmn"
            return Response(
                {"code": code, "errors": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if snapshot is None:
            return Response(
                {
                    "code": "invalid_bpmn",
                    "errors": [
                        {
                            "path": "",
                            "code": "invalid_bpmn",
                            "message": "Invalid BPMN payload.",
                        }
                    ],
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        definition_manager = cast(Any, WorkflowDefinition)._default_manager
        version_manager = cast(Any, WorkflowDefinitionVersion)._default_manager
        with cast(Any, transaction).atomic():
            definition, _ = definition_manager.get_or_create(
                tenant=request.tenant,
                process_key=snapshot.process_key,
                defaults={"name": snapshot.process_name},
            )
            latest = (
                version_manager.filter(
                    tenant=request.tenant,
                    definition=definition,
                )
                .order_by("-version")
                .first()
            )
            version_value = latest.version + 1 if latest else 1
            version_entry = version_manager.create(
                tenant=request.tenant,
                definition=definition,
                version=version_value,
                bpmn_xml=xml_text,
                form_schema_refs=snapshot.form_schema_refs,
                catalog_binding_placeholders=snapshot.catalog_binding_placeholders,
            )

        _create_audit_event(
            request.tenant,
            AuditEventType.DEFINITION_UPLOAD,
            definition_version=version_entry,
            payload={
                "process_key": snapshot.process_key,
                "version": version_value,
            },
        )
        response_serializer = WorkflowDefinitionVersionSummarySerializer(version_entry)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class WorkflowDefinitionVersionDetailView(APIView):
    def get(self, request, process_key: str, version: int):
        definition_manager = cast(Any, WorkflowDefinition)._default_manager
        version_manager = cast(Any, WorkflowDefinitionVersion)._default_manager
        definition = definition_manager.filter(
            tenant=request.tenant,
            process_key=process_key,
        ).first()
        if definition is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        version_entry = version_manager.filter(
            tenant=request.tenant,
            definition=definition,
            version=version,
        ).first()
        if version_entry is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        response_serializer = WorkflowDefinitionVersionDetailSerializer(version_entry)
        return Response(response_serializer.data)


class WorkflowInstanceStartView(APIView):
    def post(self, request, process_key: str, version: int):
        serializer = WorkflowInstanceStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = cast(dict[str, Any], serializer.validated_data)
        correlation_id = str(validated_data.get("correlation_id", ""))
        business_key = str(validated_data.get("business_key", ""))

        definition_manager = cast(Any, WorkflowDefinition)._default_manager
        version_manager = cast(Any, WorkflowDefinitionVersion)._default_manager
        instance_manager = cast(Any, WorkflowInstance)._default_manager

        definition = definition_manager.filter(
            tenant=request.tenant,
            process_key=process_key,
        ).first()
        if definition is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        version_entry = version_manager.filter(
            tenant=request.tenant,
            definition=definition,
            version=version,
        ).first()
        if version_entry is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            run_result = start_workflow_from_definition(
                version_entry,
                correlation_id=correlation_id,
                business_key=business_key,
            )
        except WorkflowRuntimeError as exc:
            return Response(
                {"code": "workflow_runtime_error", "message": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        instance = instance_manager.create(
            tenant=request.tenant,
            definition_version=version_entry,
            status=run_result.status,
            correlation_id=correlation_id,
            business_key=business_key,
            serialized_state=run_result.serialized_state,
        )

        _create_audit_event(
            request.tenant,
            AuditEventType.INSTANCE_START,
            correlation_id=correlation_id,
            business_key=business_key,
            workflow_instance=instance,
            definition_version=version_entry,
            payload={
                "process_key": process_key,
                "version": version,
                "status": run_result.status,
            },
        )
        _create_user_tasks_for_instance(
            request.tenant, instance, run_result.waiting_user_tasks
        )
        _create_service_tasks_for_instance(
            request.tenant, instance, run_result.waiting_service_tasks
        )

        response_serializer = WorkflowInstanceSerializer(instance)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class WorkflowInstanceDetailView(APIView):
    def get(self, request, instance_id: int):
        manager = cast(Any, WorkflowInstance)._default_manager
        instance = (
            manager.select_related(
                "definition_version", "definition_version__definition"
            )
            .filter(tenant=request.tenant, id=instance_id)
            .first()
        )
        if instance is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = WorkflowInstanceDetailSerializer(instance)
        return Response(serializer.data)


class UserTaskListView(ListAPIView):
    serializer_class = UserTaskSerializer

    def get_queryset(self):
        manager = cast(Any, UserTask)._default_manager
        queryset = manager.filter(
            tenant=self.request.tenant,
            status=UserTaskStatus.PENDING,
        )
        workflow_instance_id = self.request.query_params.get("workflow_instance_id")
        if workflow_instance_id:
            queryset = queryset.filter(workflow_instance_id=workflow_instance_id)
        return queryset.order_by("created_at")


class UserTaskActorRoleListView(ListAPIView):
    serializer_class = UserTaskSerializer

    def get_queryset(self):
        manager = cast(Any, UserTask)._default_manager
        queryset = manager.filter(tenant=self.request.tenant)
        workflow_instance_id = self.request.query_params.get("workflow_instance_id")
        if workflow_instance_id:
            queryset = queryset.filter(workflow_instance_id=workflow_instance_id)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        actor_identity = self.request.query_params.get("actor")
        if actor_identity:
            queryset = queryset.filter(actor_identity=actor_identity)
        role_external_id = self.request.query_params.get("role")
        if role_external_id:
            role_manager = cast(Any, RbacRole)._default_manager
            role_entry = role_manager.filter(
                tenant=self.request.tenant,
                external_id=role_external_id,
            ).first()
            if role_entry is None:
                return queryset.none()
            user_manager = cast(Any, DirectoryUser)._default_manager
            users = user_manager.filter(
                tenant=self.request.tenant,
                user_roles__role=role_entry,
                user_roles__tenant=self.request.tenant,
            ).distinct()
            identities = list(users.values_list("external_id", flat=True))
            identities.extend(list(users.values_list("email", flat=True)))
            if not identities:
                return queryset.none()
            queryset = queryset.filter(actor_identity__in=identities)
        return queryset.order_by("created_at")


class AuditEventListView(ListAPIView):
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        manager = cast(Any, AuditEvent)._default_manager
        queryset = manager.filter(tenant=self.request.tenant)
        workflow_instance_id = self.request.query_params.get("workflow_instance_id")
        if workflow_instance_id:
            queryset = queryset.filter(workflow_instance_id=workflow_instance_id)
        business_key = self.request.query_params.get("business_key")
        if business_key:
            queryset = queryset.filter(business_key=business_key)
        return queryset.order_by("-created_at")


class UserTaskCompleteView(APIView):
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


# Create your views here.
