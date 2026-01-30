from __future__ import annotations

from django.urls import path

from .views import (
    audit_event_list_view,
    capability_catalog_list_view,
    discovery_endpoint_view,
    health_view,
    service_task_callback_view,
    service_task_list_view,
    service_task_start_view,
    user_task_complete_view,
    user_task_list_view,
    user_task_actor_role_list_view,
    workflow_definition_upload_view,
    workflow_definition_list_view,
    workflow_definition_detail_view,
    workflow_definition_version_detail_view,
    workflow_instance_detail_view,
    workflow_instance_start_view,
    workflow_group_detail_view,
    workflow_group_list_create_view,
    workflow_group_tree_view,
)

urlpatterns = [
    path("health", health_view, name="health"),
    path(
        "discovery/endpoint",
        discovery_endpoint_view,
        name="discovery-endpoint",
    ),
    path(
        "discovery/catalog",
        capability_catalog_list_view,
        name="discovery-catalog",
    ),
    path(
        "workflows",
        workflow_definition_upload_view,
        name="workflow-upload",
    ),
    path(
        "workflows/list",
        workflow_definition_list_view,
        name="workflow-definition-list",
    ),
    path(
        "workflows/<str:process_key>",
        workflow_definition_detail_view,
        name="workflow-definition-detail",
    ),
    path(
        "workflow-groups",
        workflow_group_list_create_view,
        name="workflow-group-list-create",
    ),
    path(
        "workflow-groups/tree",
        workflow_group_tree_view,
        name="workflow-group-tree",
    ),
    path(
        "workflow-groups/<int:group_id>",
        workflow_group_detail_view,
        name="workflow-group-detail",
    ),
    path(
        "workflows/<str:process_key>/versions/<int:version>",
        workflow_definition_version_detail_view,
        name="workflow-version-detail",
    ),
    path(
        "workflows/<str:process_key>/versions/<int:version>/instances",
        workflow_instance_start_view,
        name="workflow-instance-start",
    ),
    path(
        "instances/<int:instance_id>",
        workflow_instance_detail_view,
        name="workflow-instance-detail",
    ),
    path(
        "instances/tasks",
        user_task_actor_role_list_view,
        name="user-task-actor-role-list",
    ),
    path("tasks", user_task_list_view, name="user-task-list"),
    path("audit", audit_event_list_view, name="audit-event-list"),
    path("audit/events", audit_event_list_view, name="audit-event-list-legacy"),
    path(
        "tasks/<int:task_id>/complete",
        user_task_complete_view,
        name="user-task-complete",
    ),
    path("service-tasks", service_task_list_view, name="service-task-list"),
    path(
        "service-tasks/<int:task_id>/start",
        service_task_start_view,
        name="service-task-start",
    ),
    path(
        "service-tasks/<int:task_id>/callback",
        service_task_callback_view,
        name="service-task-callback",
    ),
]
