import BpmnViewer from 'bpmn-js/lib/Viewer';

import type {
  InstanceState,
  InstanceTaskState,
  RenderOptions,
  RenderResult,
  TaskStatus
} from './types';

const TASK_ELEMENT_TYPES = new Set<string>([
  'bpmn:UserTask',
  'bpmn:ServiceTask',
  'bpmn:ScriptTask',
  'bpmn:SendTask',
  'bpmn:ManualTask',
  'bpmn:BusinessRuleTask',
  'bpmn:CallActivity',
  'bpmn:SubProcess'
]);

const MARKER_BY_STATUS: Record<TaskStatus, string> = {
  completed: 'instance-completed',
  in_progress: 'instance-in-progress',
  waiting: 'instance-in-progress',
  failed: 'instance-failed',
  not_started: 'instance-not-started'
};

const STYLE_TAG_ID = 'bpmn-instance-viewer-styles';

const DEFAULT_STYLES = `
.djs-element.instance-completed .djs-visual > :first-child { fill: #C8E6C9 !important; stroke: #2E7D32 !important; }
.djs-element.instance-in-progress .djs-visual > :first-child { fill: #BBDEFB !important; stroke: #1565C0 !important; }
.djs-element.instance-failed .djs-visual > :first-child { fill: #FFCDD2 !important; stroke: #C62828 !important; }
.djs-element.instance-not-started .djs-visual > :first-child { fill: #E0E0E0 !important; stroke: #9E9E9E !important; }
.djs-connection.instance-flow-traversed path { stroke: #2E7D32 !important; stroke-width: 4 !important; }

.instance-overlay {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.instance-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #1e1e1e;
  box-shadow: 0 0 0 2px white;
}

.instance-tooltip {
  position: absolute;
  bottom: 14px;
  right: -6px;
  min-width: 220px;
  max-width: 360px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid #e0e0e0;
  background: #ffffff;
  color: #1b1b1b;
  font-size: 12px;
  line-height: 1.4;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
  display: none;
  z-index: 10;
  white-space: normal;
}

.instance-overlay:hover .instance-tooltip {
  display: block;
}

.instance-tooltip h4 {
  margin: 0 0 6px 0;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.4px;
}

.instance-tooltip .row {
  display: grid;
  grid-template-columns: 90px 1fr;
  gap: 6px;
  margin-bottom: 4px;
}

.instance-tooltip pre {
  background: #f6f7f9;
  padding: 6px;
  border-radius: 6px;
  max-height: 160px;
  overflow: auto;
  margin: 6px 0 0 0;
}
`;

function ensureStyles(): void {
  if (typeof document === 'undefined') return;
  if (document.getElementById(STYLE_TAG_ID)) return;

  const tag = document.createElement('style');
  tag.id = STYLE_TAG_ID;
  tag.textContent = DEFAULT_STYLES;
  document.head.appendChild(tag);
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function formatJson(value: Record<string, unknown> | null | undefined): string {
  if (!value || typeof value !== 'object' || Object.keys(value).length === 0) return '{}';
  return JSON.stringify(value, null, 2);
}

function buildTooltip(task: InstanceTaskState): string {
  const userLabel = task.user ? task.user.name || task.user.id : 'n/a';
  const input = formatJson(task.input_data);
  const output = formatJson(task.output_data);

  return [
    '<div class="instance-overlay">',
    '<div class="instance-dot"></div>',
    '<div class="instance-tooltip">',
    '<h4>Task details</h4>',
    `<div class="row"><span>Status</span><span>${escapeHtml(task.status)}</span></div>`,
    `<div class="row"><span>Started</span><span>${escapeHtml(task.started_at || 'n/a')}</span></div>`,
    `<div class="row"><span>Completed</span><span>${escapeHtml(task.completed_at || 'n/a')}</span></div>`,
    `<div class="row"><span>User</span><span>${escapeHtml(userLabel)}</span></div>`,
    `<div class="row"><span>Input</span><span></span></div>`,
    `<pre>${escapeHtml(input)}</pre>`,
    `<div class="row"><span>Output</span><span></span></div>`,
    `<pre>${escapeHtml(output)}</pre>`,
    '</div>',
    '</div>'
  ].join('');
}

export async function render(
  container: HTMLElement,
  bpmnXml: string,
  state: InstanceState,
  options: RenderOptions = {}
): Promise<RenderResult> {
  if (!container) {
    throw new Error('render: container is required');
  }

  ensureStyles();
  container.innerHTML = '';

  const viewer = new BpmnViewer({ container });
  await viewer.importXML(bpmnXml);

  const canvas = viewer.get('canvas');
  const elementRegistry = viewer.get('elementRegistry');
  const overlays = viewer.get('overlays');

  if (options.fitViewport !== false) {
    canvas.zoom('fit-viewport');
  }

  const taskByElement = new Map<string, InstanceTaskState>();
  for (const task of state.tasks || []) {
    taskByElement.set(task.elementId, task);
  }

  const taskElements = elementRegistry.filter((element: any) =>
    TASK_ELEMENT_TYPES.has(element.type)
  );

  for (const element of taskElements) {
    canvas.addMarker(element.id, MARKER_BY_STATUS.not_started);
  }

  for (const task of state.tasks || []) {
    const element = elementRegistry.get(task.elementId);
    if (!element) continue;
    canvas.removeMarker(task.elementId, MARKER_BY_STATUS.not_started);
    canvas.addMarker(task.elementId, MARKER_BY_STATUS[task.status]);
    overlays.add(task.elementId, {
      position: { bottom: 6, right: 6 },
      html: buildTooltip(task)
    });
  }

  for (const flow of state.sequenceFlows || []) {
    if (!flow?.elementId) continue;
    const element = elementRegistry.get(flow.elementId);
    if (!element) continue;
    if (flow.status === 'traversed') {
      canvas.addMarker(flow.elementId, 'instance-flow-traversed');
    }
  }

  return {
    viewer,
    destroy: () => viewer.destroy()
  };
}
