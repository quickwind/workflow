from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable
from xml.etree import ElementTree as ET

BPMN_MODEL_NS = "http://www.omg.org/spec/BPMN/20100524/MODEL"
BPMN_DI_NS = "http://www.omg.org/spec/BPMN/20100524/DI"
DI_NS = "http://www.omg.org/spec/DD/20100524/DI"
DC_NS = "http://www.omg.org/spec/DD/20100524/DC"

ALLOWED_NON_BPMN_NAMESPACES = {BPMN_DI_NS, DI_NS, DC_NS}

SUPPORTED_BPMN_ELEMENTS_V1 = {
    "definitions",
    "process",
    "startEvent",
    "endEvent",
    "sequenceFlow",
    "exclusiveGateway",
    "parallelGateway",
    "userTask",
    "serviceTask",
    "scriptTask",
    "sendTask",
    "subProcess",
    "incoming",
    "outgoing",
    "extensionElements",
    "documentation",
    "text",
    "conditionExpression",
    "script",
}

UNSUPPORTED_BPMN_ELEMENT_MESSAGES = {
    "boundaryEvent": "Boundary events are not supported.",
    "timerEventDefinition": "Timer events are not supported.",
    "messageEventDefinition": "Message events are not supported.",
    "signalEventDefinition": "Signal events are not supported.",
    "multiInstanceLoopCharacteristics": "Multi-instance is not supported.",
    "compensateEventDefinition": "Compensation is not supported.",
}

FORM_SCHEMA_ATTRIBUTE_NAMES = {"formKey", "formRef", "formId", "schemaRef", "schemaId"}
CATALOG_BINDING_ATTRIBUTE_MARKERS = ("catalog", "capability", "binding")


@dataclass(frozen=True)
class BpmnDefinitionSnapshot:
    process_key: str
    process_name: str
    form_schema_refs: list[dict[str, str]]
    catalog_binding_placeholders: list[dict[str, Any]]


def _split_tag(tag: str) -> tuple[str | None, str]:
    if tag.startswith("{"):
        namespace, _, local = tag[1:].partition("}")
        return namespace, local
    return None, tag


def _iter_elements_with_paths(
    root: ET.Element,
) -> Iterable[tuple[ET.Element, str]]:
    root_local = _split_tag(root.tag)[1]
    root_path = root_local
    yield root, root_path
    yield from _iter_child_elements(root, root_path)


def _iter_child_elements(
    element: ET.Element, parent_path: str
) -> Iterable[tuple[ET.Element, str]]:
    counts: dict[str, int] = {}
    for child in list(element):
        child_local = _split_tag(child.tag)[1]
        index = counts.get(child_local, 0)
        counts[child_local] = index + 1
        child_path = f"{parent_path}.{child_local}[{index}]"
        yield child, child_path
        yield from _iter_child_elements(child, child_path)


def _add_error(
    errors: list[dict[str, str]], path: str, code: str, message: str
) -> None:
    errors.append({"path": path, "code": code, "message": message})


def _sorted_errors(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    return sorted(
        errors, key=lambda item: (item["path"], item["code"], item["message"])
    )


def _collect_form_schema_refs(root: ET.Element) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for element in root.iter():
        element_type = _split_tag(element.tag)[1]
        element_id = element.attrib.get("id", "")
        for attr_name, attr_value in element.attrib.items():
            attr_local = _split_tag(attr_name)[1]
            if attr_local in FORM_SCHEMA_ATTRIBUTE_NAMES and attr_value:
                refs.append(
                    {
                        "element_id": element_id,
                        "element_type": element_type,
                        "form_key": str(attr_value),
                    }
                )
    return refs


def _collect_catalog_binding_placeholders(root: ET.Element) -> list[dict[str, Any]]:
    placeholders: list[dict[str, Any]] = []
    for element in root.iter():
        namespace, local = _split_tag(element.tag)
        if namespace != BPMN_MODEL_NS or local != "serviceTask":
            continue
        attrs: dict[str, str] = {}
        for attr_name, attr_value in element.attrib.items():
            attr_local = _split_tag(attr_name)[1]
            lowered = attr_local.lower()
            if any(marker in lowered for marker in CATALOG_BINDING_ATTRIBUTE_MARKERS):
                attrs[attr_local] = str(attr_value)
        if attrs:
            placeholders.append(
                {
                    "element_id": element.attrib.get("id", ""),
                    "element_name": element.attrib.get("name", ""),
                    "element_type": local,
                    "placeholders": attrs,
                }
            )
    return placeholders


def validate_bpmn_xml(
    xml_text: str,
) -> tuple[BpmnDefinitionSnapshot | None, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        _add_error(errors, "", "invalid_bpmn_xml", "Invalid BPMN XML.")
        return None, _sorted_errors(errors)

    process_elements = [
        element
        for element in root.iter()
        if _split_tag(element.tag)[0] == BPMN_MODEL_NS
        and _split_tag(element.tag)[1] == "process"
    ]

    process_key = ""
    process_name = ""
    if not process_elements:
        _add_error(errors, "process", "missing_process_key", "Process id is required.")
    elif len(process_elements) > 1:
        _add_error(
            errors,
            "process",
            "multiple_processes",
            "Only one process is supported.",
        )
    else:
        process = process_elements[0]
        process_key = process.attrib.get("id", "").strip()
        process_name = process.attrib.get("name", "")
        if not process_key:
            _add_error(
                errors, "process", "missing_process_key", "Process id is required."
            )

    for element, path in _iter_elements_with_paths(root):
        namespace, local = _split_tag(element.tag)
        if namespace == BPMN_MODEL_NS:
            if local in UNSUPPORTED_BPMN_ELEMENT_MESSAGES:
                _add_error(
                    errors,
                    path,
                    "unsupported_bpmn_element",
                    UNSUPPORTED_BPMN_ELEMENT_MESSAGES[local],
                )
            elif local not in SUPPORTED_BPMN_ELEMENTS_V1:
                _add_error(
                    errors,
                    path,
                    "unsupported_bpmn_element",
                    f"Unsupported BPMN element: {local}.",
                )

            for attr_name, attr_value in element.attrib.items():
                attr_local = _split_tag(attr_name)[1]
                if (
                    attr_local == "isForCompensation"
                    and str(attr_value).lower() == "true"
                ):
                    _add_error(
                        errors,
                        path,
                        "unsupported_bpmn_element",
                        "Compensation is not supported.",
                    )
        elif namespace not in ALLOWED_NON_BPMN_NAMESPACES and namespace is not None:
            continue

    if errors:
        return None, _sorted_errors(errors)

    form_schema_refs = _collect_form_schema_refs(root)
    catalog_binding_placeholders = _collect_catalog_binding_placeholders(root)
    snapshot = BpmnDefinitionSnapshot(
        process_key=process_key,
        process_name=process_name,
        form_schema_refs=form_schema_refs,
        catalog_binding_placeholders=catalog_binding_placeholders,
    )
    return snapshot, []
