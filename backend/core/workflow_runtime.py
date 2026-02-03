from __future__ import annotations

"""
Core workflow runtime integration with SpiffWorkflow.
Handles BPMN parsing, instance execution, state serialization, and ScriptTask sandboxing.
"""

import os
import tempfile
from dataclasses import dataclass
from typing import Any, Iterable, TYPE_CHECKING, cast

if TYPE_CHECKING:
    from .models import WorkflowDefinitionVersion


class WorkflowRuntimeError(RuntimeError):
    """Base exception for workflow runtime failures."""

    pass


class ScriptTaskExecutionError(RuntimeError):
    """Raised when a ScriptTask fails to execute within the sandbox."""

    pass


@dataclass(frozen=True)
class WorkflowRunResult:
    """
    Result of a workflow execution run.
    Contains the updated state and lists of tasks that require external action.
    """

    status: str
    serialized_state: dict[str, Any]
    waiting_user_tasks: list["UserTaskSnapshot"]
    waiting_service_tasks: list["ServiceTaskSnapshot"]
    error_message: str | None = None


@dataclass(frozen=True)
class UserTaskSnapshot:
    """Snapshot of a UserTask that is waiting for human interaction."""

    task_id: str
    name: str
    task_type: str


@dataclass(frozen=True)
class ServiceTaskSnapshot:
    """Snapshot of a ServiceTask that is waiting for external REST API execution."""

    task_id: str
    name: str
    task_type: str
    element_id: str
    element_name: str


# Element types that cause the engine to pause and wait for external input/callback.
WAITING_TASK_SPEC_NAMES = {
    "UserTask",
    "ManualTask",
    "ServiceTask",
    "SendTask",
    "ExternalTask",
}

# Suffix used to identify ScriptTasks in various SpiffWorkflow versions.
SCRIPT_TASK_SPEC_SUFFIX = "ScriptTask"

# Safe built-in functions allowed within the RestrictedPython sandbox.
SCRIPT_BUILTINS_ALLOWLIST = {
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "Exception",
    "float",
    "int",
    "isinstance",
    "len",
    "list",
    "max",
    "min",
    "range",
    "round",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
}

# Element types considered 'user tasks' for assignment and notifications.
USER_WAITING_TASK_SPEC_NAMES = {
    "UserTask",
    "ManualTask",
}


def start_workflow_from_definition(
    definition_version: "WorkflowDefinitionVersion",
    correlation_id: str = "",
    business_key: str = "",
) -> WorkflowRunResult:
    """
    Initializes and starts a new workflow instance from a specific BPMN version.
    Runs automated tasks until the first waiting point is reached.
    """
    workflow = _build_workflow(definition_version)
    _attach_identifiers(workflow, correlation_id, business_key)
    status, error_message = _run_until_waiting(workflow)
    if status == "failed":
        waiting_user_tasks = []
        waiting_service_tasks = []
    else:
        # After running, collect any tasks that are now waiting for external action.
        waiting_user_tasks = _collect_waiting_user_tasks(workflow)
        waiting_service_tasks = _collect_waiting_service_tasks(workflow)
    serialized_state = _serialize_workflow(workflow)
    return WorkflowRunResult(
        status=status,
        serialized_state=serialized_state,
        waiting_user_tasks=waiting_user_tasks,
        waiting_service_tasks=waiting_service_tasks,
        error_message=error_message,
    )


def resume_workflow_from_state(
    definition_version: "WorkflowDefinitionVersion",
    serialized_state: dict[str, Any],
    completed_task_id: str | None = None,
    task_result: Any | None = None,
    correlation_id: str = "",
    business_key: str = "",
) -> WorkflowRunResult:
    """
    Resumes a workflow instance from a serialized state.
    Optionally completes a task with a result before continuing execution.
    """
    workflow = _load_workflow_from_state(definition_version, serialized_state)
    _attach_identifiers(workflow, correlation_id, business_key)
    if completed_task_id:
        task = _find_ready_task_by_id(workflow, completed_task_id)
        if task is None:
            raise WorkflowRuntimeError("Task not found in workflow state.")
        _apply_task_result(workflow, task, task_result)
        _complete_task(workflow, task)
    
    # After potentially completing a task, run the engine until it hits the next waiting state.
    status, error_message = _run_until_waiting(workflow)
    if status == "failed":
        waiting_user_tasks = []
        waiting_service_tasks = []
    else:
        waiting_user_tasks = _collect_waiting_user_tasks(workflow)
        waiting_service_tasks = _collect_waiting_service_tasks(workflow)
    updated_state = _serialize_workflow(workflow)
    return WorkflowRunResult(
        status=status,
        serialized_state=updated_state,
        waiting_user_tasks=waiting_user_tasks,
        waiting_service_tasks=waiting_service_tasks,
        error_message=error_message,
    )


def _build_workflow(definition_version: "WorkflowDefinitionVersion") -> Any:
    """Initializes a SpiffWorkflow object from a BPMN definition."""
    parser_class = _load_bpmn_parser()
    workflow_class = _load_workflow_class()
    parser = parser_class()
    _add_bpmn_xml(parser, cast(str, definition_version.bpmn_xml))
    definition = cast(Any, definition_version.definition)
    spec = _get_workflow_spec(parser, cast(str, definition.process_key))
    return workflow_class(spec)


def _add_bpmn_xml(parser: Any, bpmn_xml: str) -> None:
    """Adds BPMN XML to the parser, handling API variations."""
    if hasattr(parser, "add_bpmn_string"):
        try:
            parser.add_bpmn_string(bpmn_xml)
            return
        except TypeError:
            parser.add_bpmn_string(bpmn_xml, "definition.bpmn")
            return
    if hasattr(parser, "add_bpmn_file"):
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".bpmn", delete=False
            ) as handle:
                handle.write(bpmn_xml)
                temp_path = handle.name
            parser.add_bpmn_file(temp_path)
            return
        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
    raise WorkflowRuntimeError("Unsupported SpiffWorkflow parser API.")


def _get_workflow_spec(parser: Any, process_key: str) -> Any:
    """Extracts the workflow specification from the parser."""
    if not hasattr(parser, "get_spec"):
        raise WorkflowRuntimeError("SpiffWorkflow parser missing get_spec().")
    try:
        return parser.get_spec(process_key)
    except TypeError:
        return parser.get_spec()
    except KeyError as exc:
        raise WorkflowRuntimeError("Workflow spec not found for process key.") from exc


def _attach_identifiers(workflow: Any, correlation_id: str, business_key: str) -> None:
    """Attaches correlation and business keys to the workflow data."""
    data = getattr(workflow, "data", None)
    if not isinstance(data, dict):
        return
    if correlation_id:
        data["correlation_id"] = correlation_id
    if business_key:
        data["business_key"] = business_key


def _run_until_waiting(workflow: Any) -> tuple[str, str | None]:
    """
    Main execution loop. Continuously runs ready tasks until no more automatic
    tasks are available, or a waiting task (e.g., UserTask) is encountered.
    """
    error_message = None
    while True:
        ready_tasks = list(_get_ready_tasks(workflow))
        if not ready_tasks:
            break
        progressed = False
        for task in ready_tasks:
            # If a task is a "waiting" task, the loop will stop.
            if _is_waiting_task(task):
                continue
            try:
                _run_task(workflow, task)
            except ScriptTaskExecutionError as exc:
                error_message = str(exc)
                return "failed", error_message
            progressed = True
        if not progressed:
            break
    return _determine_status(workflow), error_message


def _get_ready_tasks(workflow: Any) -> Iterable[Any]:
    """Gets the list of ready tasks from the workflow engine."""
    task_state = _load_task_state()
    if task_state is not None and hasattr(workflow, "get_tasks"):
        return workflow.get_tasks(task_state.READY)
    if hasattr(workflow, "get_ready_tasks"):
        return workflow.get_ready_tasks()
    if hasattr(workflow, "get_tasks"):
        try:
            return workflow.get_tasks("READY")
        except Exception:
            return []
    return []


def _is_waiting_task(task: Any) -> bool:
    """Checks if a task is a type that requires external intervention."""
    spec = getattr(task, "task_spec", None)
    if spec is None:
        return False
    if getattr(spec, "manual", False):
        return True
    return spec.__class__.__name__ in WAITING_TASK_SPEC_NAMES


def _run_task(workflow: Any, task: Any) -> None:
    """Executes a single workflow task, handling ScriptTasks specially."""
    spec = getattr(task, "task_spec", None)
    if _is_script_task(task):
        _run_script_task(workflow, task)
        _complete_script_task(workflow, task)
        return
    if spec is not None and hasattr(spec, "run"):
        spec.run(task)
        return
    if hasattr(task, "run"):
        task.run()
        return
    if hasattr(workflow, "run_task_from_id"):
        workflow.run_task_from_id(task.id)
        return
    if hasattr(workflow, "run_task"):
        workflow.run_task(task)
        return
    raise WorkflowRuntimeError("Unable to run workflow task.")


def _determine_status(workflow: Any) -> str:
    """Determines the overall status of the workflow instance."""
    if _has_waiting_tasks(workflow):
        return "waiting"
    is_completed = getattr(workflow, "is_completed", None)
    if callable(is_completed) and is_completed():
        return "completed"
    is_complete = getattr(workflow, "is_complete", None)
    if callable(is_complete) and is_complete():
        return "completed"
    return "completed" if not list(_get_ready_tasks(workflow)) else "running"


def _is_script_task(task: Any) -> bool:
    """Checks if a task is a ScriptTask."""
    spec = getattr(task, "task_spec", None)
    if spec is None:
        return False
    spec_name = spec.__class__.__name__
    if spec_name == "ScriptTask":
        return True
    return spec_name.endswith(SCRIPT_TASK_SPEC_SUFFIX)


def _run_script_task(workflow: Any, task: Any) -> None:
    """
    Executes a ScriptTask in a sandboxed environment using RestrictedPython.
    """
    spec = getattr(task, "task_spec", None)
    script_source = _extract_script_source(task, spec)
    if script_source is None or not script_source.strip():
        raise ScriptTaskExecutionError(_format_script_error(task, "missing script"))
    
    code = _compile_restricted_script(script_source, task)
    globals_dict = _build_script_globals(task)
    workflow_data = _ensure_data_dict(workflow, "data")
    task_data = _ensure_data_dict(task, "data")
    
    # Expose 'data' and 'task_data' to the script's local scope.
    locals_dict = {
        "data": workflow_data,
        "task_data": task_data,
    }
    try:
        exec(code, globals_dict, locals_dict)
    except Exception as exc:
        raise ScriptTaskExecutionError(
            _format_script_error(task, f"runtime error: {exc}")
        ) from exc
    
    # If the script sets a 'result' variable, apply it to the task.
    if "result" in locals_dict:
        _apply_task_result(workflow, task, locals_dict.get("result"))


def _complete_script_task(workflow: Any, task: Any) -> None:
    """Marks a ScriptTask as complete within the workflow engine."""
    if hasattr(task, "complete"):
        task.complete()
        return
    if hasattr(workflow, "complete_task_from_id"):
        workflow.complete_task_from_id(task.id)
        return
    raise ScriptTaskExecutionError(
        _format_script_error(task, "unable to mark task complete")
    )


def _extract_script_source(task: Any, spec: Any | None) -> str | None:
    """Extracts the script content from a ScriptTask specification."""
    if spec is None:
        return None
    for attr_name in ("script", "script_text", "script_body", "scriptBody"):
        value = getattr(spec, attr_name, None)
        if value is not None:
            return str(value)
    return None


def _compile_restricted_script(script_source: str, task: Any) -> Any:
    """Compiles Python source code in a restricted, sandboxed environment."""
    try:
        from RestrictedPython import compile_restricted
    except ImportError as exc:
        raise ScriptTaskExecutionError(
            _format_script_error(task, "RestrictedPython is not installed")
        ) from exc
    result = compile_restricted(script_source, filename="<script_task>", mode="exec")
    errors = getattr(result, "errors", None)
    if errors:
        raise ScriptTaskExecutionError(
            _format_script_error(task, f"compile error: {', '.join(errors)}")
        )
    return getattr(result, "code", result)


def _build_script_globals(task: Any) -> dict[str, Any]:
    """Builds the safe global environment for executing a ScriptTask."""
    try:
        from RestrictedPython.Guards import (
            guarded_getattr,
            guarded_getitem,
            guarded_getiter,
            safe_builtins,
            full_write_guard,
        )
        from RestrictedPython.PrintCollector import PrintCollector
    except ImportError as exc:
        raise ScriptTaskExecutionError(
            _format_script_error(task, "RestrictedPython is not installed")
        ) from exc
    builtins_map = {
        name: safe_builtins[name]
        for name in SCRIPT_BUILTINS_ALLOWLIST
        if name in safe_builtins
    }
    return {
        "__builtins__": builtins_map,
        "_getattr_": guarded_getattr,
        "_getitem_": guarded_getitem,
        "_getiter_": guarded_getiter,
        "_write_": full_write_guard,
        "_print_": PrintCollector,
    }


def _ensure_data_dict(target: Any, attr_name: str) -> dict[str, Any]:
    """Ensures that a 'data' attribute exists and is a dictionary."""
    current = getattr(target, attr_name, None)
    if isinstance(current, dict):
        return current
    data: dict[str, Any] = {}
    try:
        setattr(target, attr_name, data)
    except Exception:
        pass
    return data


def _format_script_error(task: Any, detail: str) -> str:
    """Creates a formatted error message for ScriptTask failures."""
    task_id = str(getattr(task, "id", ""))
    task_name = str(getattr(task, "name", ""))
    parts = ["ScriptTask execution failed"]
    if task_name:
        parts.append(f"name={task_name}")
    if task_id:
        parts.append(f"id={task_id}")
    if detail:
        parts.append(detail)
    return ": ".join([parts[0], ", ".join(parts[1:])])


def _has_waiting_tasks(workflow: Any) -> bool:
    """Checks if there are any tasks in a waiting state."""
    for task in _get_ready_tasks(workflow):
        if _is_waiting_task(task):
            return True
    return False


def _collect_waiting_user_tasks(workflow: Any) -> list[UserTaskSnapshot]:
    """Collects snapshots of all ready tasks that are of a user-facing type."""
    snapshots: list[UserTaskSnapshot] = []
    for task in _get_ready_tasks(workflow):
        if not _is_waiting_task(task):
            continue
        spec = getattr(task, "task_spec", None)
        spec_type = ""
        spec_name = ""
        if spec is not None:
            spec_type = spec.__class__.__name__
            spec_name = str(getattr(spec, "name", ""))
        if spec_type not in USER_WAITING_TASK_SPEC_NAMES:
            continue
        task_name = str(getattr(task, "name", "")) or spec_name
        task_id = str(getattr(task, "id", ""))
        snapshots.append(
            UserTaskSnapshot(
                task_id=task_id,
                name=task_name,
                task_type=spec_type,
            )
        )
    return snapshots


def _collect_waiting_service_tasks(workflow: Any) -> list[ServiceTaskSnapshot]:
    """Collects snapshots of all ready tasks that are ServiceTasks."""
    snapshots: list[ServiceTaskSnapshot] = []
    for task in _get_ready_tasks(workflow):
        if not _is_waiting_task(task):
            continue
        spec = getattr(task, "task_spec", None)
        spec_type = ""
        spec_name = ""
        spec_element_id = ""
        if spec is not None:
            spec_type = spec.__class__.__name__
            spec_name = str(getattr(spec, "name", ""))
            spec_element_id = str(
                getattr(spec, "bpmn_id", "") or getattr(spec, "id", "") or ""
            )
        if spec_type != "ServiceTask":
            continue
        task_name = str(getattr(task, "name", "")) or spec_name
        task_id = str(getattr(task, "id", ""))
        snapshots.append(
            ServiceTaskSnapshot(
                task_id=task_id,
                name=task_name,
                task_type=spec_type,
                element_id=spec_element_id,
                element_name=spec_name,
            )
        )
    return snapshots


def _serialize_workflow(workflow: Any) -> dict[str, Any]:
    """Serializes the workflow state to a JSON-compatible dictionary."""
    serializer_class = _load_json_serializer()
    serializer = serializer_class()
    return serializer.serialize_workflow(workflow)


def _load_workflow_from_state(
    definition_version: "WorkflowDefinitionVersion",
    serialized_state: dict[str, Any],
) -> Any:
    """Deserializes a workflow from a stored state dictionary."""
    workflow = _build_workflow(definition_version)
    serializer_class = _load_json_serializer()
    serializer = serializer_class()
    deserialized = None
    spec = getattr(workflow, "spec", None)
    if spec is not None:
        deserialized = _deserialize_with_fallback(serializer, spec, serialized_state)
    if deserialized is None:
        deserialized = _deserialize_with_fallback(
            serializer, workflow, serialized_state
        )
    return deserialized if deserialized is not None else workflow


def _deserialize_with_fallback(
    serializer: Any, target: Any, state: dict[str, Any]
) -> Any:
    """Handles different versions of the SpiffWorkflow deserialize API."""
    try:
        result = serializer.deserialize_workflow(target, state)
        return result if result is not None else target
    except TypeError:
        try:
            result = serializer.deserialize_workflow(state)
            return result
        except TypeError as exc:
            raise WorkflowRuntimeError(
                "Unsupported SpiffWorkflow deserialize API."
            ) from exc


def _load_bpmn_parser() -> Any:
    """Dynamically imports the BpmnParser, trying multiple paths."""
    try:
        from SpiffWorkflow.bpmn.parser import BpmnParser

        return BpmnParser
    except ImportError:
        try:
            from SpiffWorkflow.bpmn.parser.BpmnParser import BpmnParser

            return BpmnParser
        except ImportError as exc:
            raise WorkflowRuntimeError(
                "SpiffWorkflow BPMN parser is unavailable."
            ) from exc


def _load_workflow_class() -> Any:
    """Dynamically imports the BpmnWorkflow class."""
    try:
        from SpiffWorkflow.bpmn.workflow import BpmnWorkflow

        return BpmnWorkflow
    except ImportError as exc:
        raise WorkflowRuntimeError(
            "SpiffWorkflow BPMN workflow class is unavailable."
        ) from exc


def _load_json_serializer() -> Any:
    """Dynamically imports the JSONSerializer, trying multiple paths."""
    try:
        from SpiffWorkflow.serializer.json import JSONSerializer

        return JSONSerializer
    except ImportError:
        try:
            from SpiffWorkflow.serializer import JSONSerializer

            return JSONSerializer
        except ImportError as exc:
            raise WorkflowRuntimeError(
                "SpiffWorkflow JSON serializer is unavailable."
            ) from exc


def _load_task_state() -> Any | None:
    """Dynamically imports the TaskState enum."""
    try:
        from SpiffWorkflow.task import TaskState

        return TaskState
    except ImportError:
        return None


def _find_ready_task_by_id(workflow: Any, task_id: str) -> Any | None:
    """Finds a task within the workflow engine's ready list by its ID."""
    if hasattr(workflow, "get_task_from_id"):
        try:
            task = workflow.get_task_from_id(task_id)
            if task is not None:
                return task
        except Exception:
            pass
    for task in _get_ready_tasks(workflow):
        if str(getattr(task, "id", "")) == str(task_id):
            return task
    return None


def _apply_task_result(workflow: Any, task: Any, task_result: Any | None) -> None:
    """Applies the result of a completed task to the workflow data."""
    if task_result is None:
        return
    result_payload: dict[str, Any]
    if isinstance(task_result, dict):
        result_payload = task_result
    else:
        result_payload = {"result": task_result}
    if hasattr(task, "data"):
        task_data = getattr(task, "data", None)
        if isinstance(task_data, dict):
            task_data.update(result_payload)
        else:
            try:
                setattr(task, "data", result_payload)
            except Exception:
                pass
    if hasattr(workflow, "data"):
        workflow_data = getattr(workflow, "data", None)
        if isinstance(workflow_data, dict):
            # Store results in a dedicated namespace to avoid polluting the main data scope.
            service_results = workflow_data.setdefault("service_task_results", {})
            if isinstance(service_results, dict):
                service_results[str(getattr(task, "id", ""))] = result_payload


def _complete_task(workflow: Any, task: Any) -> None:
    """Marks a task as complete in the workflow engine."""
    if hasattr(task, "complete"):
        task.complete()
        return
    if hasattr(workflow, "complete_task_from_id"):
        workflow.complete_task_from_id(task.id)
        return
    _run_task(workflow, task)
