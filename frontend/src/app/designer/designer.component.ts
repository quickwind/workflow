import {
  AfterViewInit,
  Component,
  DestroyRef,
  ElementRef,
  Inject,
  PLATFORM_ID,
  ViewChild
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import {
  WorkflowDefinitionListItem,
  WorkflowGroupTreeNode,
  WorkflowsApiService
} from '../core/workflows-api.service';

type BpmnImportResult = { warnings?: unknown[] };
type BpmnSaveXmlResult = { xml: string };

@Component({
  selector: 'app-designer',
  imports: [CommonModule, FormsModule],
  templateUrl: './designer.component.html',
  styleUrl: './designer.component.css'
})
export class DesignerComponent implements AfterViewInit {
  @ViewChild('bpmnCanvas', { static: true }) private readonly bpmnCanvas!: ElementRef<HTMLDivElement>;
  @ViewChild('propertiesPanel', { static: true })
  private readonly propertiesPanel!: ElementRef<HTMLDivElement>;
  @ViewChild('formEditor', { static: true }) private readonly formEditorHost!: ElementRef<HTMLDivElement>;

  processKey = 'example_process';
  version = 1;

  workflowName = 'Example Workflow';
  workflowDescription = '';

  groupFilterKind: 'all' | 'ungrouped' | 'group' = 'all';
  selectedGroupId: number | null = null;
  groupTree: WorkflowGroupTreeNode[] = [];
  workflowList: WorkflowDefinitionListItem[] = [];

  selectedWorkflowKey: string | null = null;
  workflowGroupId: number | null = null;

  status = 'Idle';

  private readonly isBrowser: boolean;
  private bpmnModeler: any | null = null;
  private formEditor: any | null = null;

  private groupNameById = new Map<number, string>();
  private groupParentById = new Map<number, number | null>();
  private groupDescriptionById = new Map<number, string>();

  private currentFormSchema: any = {
    type: 'default',
    components: [
      {
        key: 'exampleField',
        label: 'Example Field',
        type: 'textfield'
      }
    ]
  };

  private readonly defaultBpmnXml = `<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
  id="Definitions_1"
  targetNamespace="http://bpmn.io/schema/bpmn">
  <bpmn:process id="Process_1" isExecutable="true">
    <bpmn:startEvent id="StartEvent_1" />
  </bpmn:process>
  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="Process_1">
      <bpmndi:BPMNShape id="StartEvent_1_di" bpmnElement="StartEvent_1">
        <dc:Bounds x="172" y="102" width="36" height="36" />
      </bpmndi:BPMNShape>
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>`;

  constructor(
    @Inject(PLATFORM_ID) platformId: object,
    private readonly destroyRef: DestroyRef,
    private readonly workflowsApi: WorkflowsApiService
  ) {
    this.isBrowser = isPlatformBrowser(platformId);
    this.status = this.isBrowser ? 'Initializing editors...' : 'Browser-only editor (SSR disabled)';
  }

  async ngAfterViewInit(): Promise<void> {
    if (!this.isBrowser) return;

    await this.initBpmnModeler();
    await this.initFormEditor();

    await this.refreshSidebar();

    this.status = 'Ready';
  }

  async refreshSidebar(): Promise<void> {
    if (!this.isBrowser) return;

    this.status = 'Loading workflows...';
    try {
      const [tree] = await Promise.all([
        firstValueFrom(this.workflowsApi.getWorkflowGroupsTree())
      ]);
      this.groupTree = tree;
      this.rebuildGroupIndexes(tree);

      await this.refreshWorkflowList();
    } catch (err) {
      this.status = 'Sidebar load failed';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  async refreshWorkflowList(): Promise<void> {
    if (!this.isBrowser) return;
    try {
      const list = await firstValueFrom(
        this.workflowsApi.listWorkflowDefinitions({
          groupId: this.groupFilterKind === 'group' ? this.selectedGroupId : undefined,
          ungrouped: this.groupFilterKind === 'ungrouped'
        })
      );
      this.workflowList = list;
    } catch (err) {
      this.status = 'Workflow list failed';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  async setGroupFilterAll(): Promise<void> {
    this.groupFilterKind = 'all';
    this.selectedGroupId = null;
    await this.refreshWorkflowList();
  }

  async setGroupFilterUngrouped(): Promise<void> {
    this.groupFilterKind = 'ungrouped';
    this.selectedGroupId = null;
    await this.refreshWorkflowList();
  }

  async setGroupFilterGroup(groupId: number): Promise<void> {
    this.groupFilterKind = 'group';
    this.selectedGroupId = groupId;
    await this.refreshWorkflowList();
  }

  async selectWorkflow(def: WorkflowDefinitionListItem): Promise<void> {
    if (!this.isBrowser) return;

    this.selectedWorkflowKey = def.processKey;
    this.processKey = def.processKey;
    this.workflowName = def.name || def.processKey;
    this.workflowDescription = def.description || '';
    this.workflowGroupId = def.groupId ?? null;

    const latest = def.latestVersion;
    if (!latest || !Number.isFinite(latest)) {
      this.version = 1;
      this.status = 'No versions found';
      return;
    }

    this.version = latest;
    await this.loadFromApi();
  }

  async createGroup(parentId: number | null): Promise<void> {
    if (!this.isBrowser) return;

    const name = (window.prompt('New group name', '') || '').trim();
    if (!name) return;

    const description = (window.prompt('Group description (optional)', '') || '').trim();

    this.status = 'Creating group...';
    try {
      const created = await firstValueFrom(
        this.workflowsApi.createWorkflowGroup({ name, parentId, description })
      );
      await this.refreshSidebar();
      await this.setGroupFilterGroup(created.id);
      this.status = 'Ready';
    } catch (err) {
      this.status = 'Create group failed';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  async renameSelectedGroup(): Promise<void> {
    if (!this.isBrowser) return;
    if (this.groupFilterKind !== 'group' || !this.selectedGroupId) return;

    const currentName = this.groupNameById.get(this.selectedGroupId) || '';
    const currentDescription = this.groupDescriptionById.get(this.selectedGroupId) || '';
    const name = (window.prompt('Rename group', currentName) || '').trim();

    const description = (window.prompt('Edit description (optional)', currentDescription) || '').trim();
    if (!name && description === currentDescription) return;
    if (!name) return;

    this.status = 'Renaming group...';
    try {
      await firstValueFrom(
        this.workflowsApi.patchWorkflowGroup(this.selectedGroupId, { name, description })
      );
      await this.refreshSidebar();
      await this.setGroupFilterGroup(this.selectedGroupId);
      this.status = 'Ready';
    } catch (err) {
      this.status = 'Rename failed';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  async moveSelectedGroup(): Promise<void> {
    if (!this.isBrowser) return;
    if (this.groupFilterKind !== 'group' || !this.selectedGroupId) return;

    const currentParentId = this.groupParentById.get(this.selectedGroupId) ?? null;
    const hint = currentParentId ? String(currentParentId) : '';
    const raw = window.prompt('Move group: new parent id (blank = root)', hint);
    if (raw === null) return;

    const trimmed = raw.trim();
    const parentId = trimmed === '' ? null : Number(trimmed);
    if (trimmed !== '' && !Number.isFinite(parentId)) return;

    this.status = 'Moving group...';
    try {
      await firstValueFrom(this.workflowsApi.patchWorkflowGroup(this.selectedGroupId, { parentId }));
      await this.refreshSidebar();
      await this.setGroupFilterGroup(this.selectedGroupId);
      this.status = 'Ready';
    } catch (err) {
      this.status = 'Move failed';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  async deleteSelectedGroup(): Promise<void> {
    if (!this.isBrowser) return;
    if (this.groupFilterKind !== 'group' || !this.selectedGroupId) return;

    const groupName = this.groupNameById.get(this.selectedGroupId) || `#${this.selectedGroupId}`;
    const ok = window.confirm(`Delete group "${groupName}"? (must be empty)`);
    if (!ok) return;

    this.status = 'Deleting group...';
    try {
      await firstValueFrom(this.workflowsApi.deleteWorkflowGroup(this.selectedGroupId));
      await this.refreshSidebar();
      await this.setGroupFilterAll();
      this.status = 'Ready';
    } catch (err) {
      this.status = 'Delete failed';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  assignWorkflowToSelectedGroup(): void {
    if (this.groupFilterKind !== 'group' || !this.selectedGroupId) return;
    this.workflowGroupId = this.selectedGroupId;
  }

  clearWorkflowGroup(): void {
    this.workflowGroupId = null;
  }

  get workflowGroupLabel(): string {
    if (this.workflowGroupId === null) return 'Ungrouped';
    return this.groupNameById.get(this.workflowGroupId) || `Group #${this.workflowGroupId}`;
  }

  private rebuildGroupIndexes(tree: WorkflowGroupTreeNode[]): void {
    this.groupNameById = new Map<number, string>();
    this.groupParentById = new Map<number, number | null>();
    this.groupDescriptionById = new Map<number, string>();

    const walk = (nodes: WorkflowGroupTreeNode[], parentId: number | null) => {
      for (const node of nodes) {
        this.groupNameById.set(node.id, node.name);
        this.groupParentById.set(node.id, parentId);
        this.groupDescriptionById.set(node.id, node.description || '');
        walk(node.children || [], node.id);
      }
    };

    walk(tree || [], null);
  }

  async resetToDefaults(): Promise<void> {
    if (!this.isBrowser || !this.bpmnModeler || !this.formEditor) return;

    this.status = 'Resetting...';

    await this.importBpmnXml(this.defaultBpmnXml);
    await this.formEditor.importSchema(this.currentFormSchema);

    this.status = 'Ready';
  }

  // Step 4 wires these to backend.
  async loadFromApi(): Promise<void> {
    if (!this.isBrowser || !this.bpmnModeler || !this.formEditor) return;

    const processKey = (this.processKey || '').trim();
    if (!processKey) {
      this.status = 'Load: missing process key';
      return;
    }

    this.status = `Loading ${processKey}@${this.version}...`;

    try {
      const data = await firstValueFrom(this.workflowsApi.getWorkflowVersion(processKey, this.version));

      if (data.bpmnXml) {
        await this.importBpmnXml(data.bpmnXml);
      }

      if (data.formSchema && typeof data.formSchema === 'object') {
        this.currentFormSchema = data.formSchema;
        await this.formEditor.importSchema(this.currentFormSchema);
      }

      this.status = 'Ready';
    } catch (err) {
      this.status = `Load failed`; // keep short; details in console
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  async saveToApi(): Promise<void> {
    if (!this.isBrowser || !this.bpmnModeler || !this.formEditor) return;

    const processKey = (this.processKey || '').trim();
    if (!processKey) {
      this.status = 'Save: missing process key';
      return;
    }

    const name = (this.workflowName || '').trim() || processKey;
    const description = (this.workflowDescription || '').trim();
    const groupId = this.workflowGroupId;

    this.status = `Saving ${processKey}...`;

    try {
      const { xml } = await this.saveBpmnXml();
      const schema = this.formEditor.saveSchema();

      const uploadResult = await firstValueFrom(
        this.workflowsApi.uploadWorkflow({
          processKey,
          bpmnXml: xml,
          formSchema: schema,
          name,
          description,
          groupId
        })
      );

      let effectiveProcessKey = processKey;
      let returnedVersion: number | null = null;
      if (uploadResult && typeof uploadResult === 'object') {
        const r = uploadResult as Record<string, unknown>;
        const returnedKey =
          (typeof r['process_key'] === 'string' && (r['process_key'] as string)) ||
          (typeof r['processKey'] === 'string' && (r['processKey'] as string)) ||
          '';
        const versionRaw = r['version'];
        const parsedVersion = typeof versionRaw === 'number' ? versionRaw : Number(versionRaw);

        if (returnedKey) effectiveProcessKey = returnedKey;
        if (Number.isFinite(parsedVersion)) returnedVersion = parsedVersion;
      }

      await firstValueFrom(
        this.workflowsApi.patchWorkflowDefinition(effectiveProcessKey, {
          name,
          description,
          groupId
        })
      );

      this.processKey = effectiveProcessKey;
      this.workflowName = name;
      this.workflowDescription = description;
      if (returnedVersion !== null) this.version = returnedVersion;
      this.selectedWorkflowKey = effectiveProcessKey;

      await this.refreshWorkflowList();

      this.status = 'Saved';
      setTimeout(() => {
        if (this.status === 'Saved') this.status = 'Ready';
      }, 800);
    } catch (err) {
      this.status = 'Save failed';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  async downloadBpmn(): Promise<void> {
    if (!this.isBrowser || !this.bpmnModeler) return;
    const { xml } = await this.saveBpmnXml();
    this.downloadText(xml, `${this.processKey || 'workflow'}.bpmn`);
  }

  async downloadFormSchema(): Promise<void> {
    if (!this.isBrowser || !this.formEditor) return;
    const schema = this.formEditor.saveSchema();
    this.downloadText(JSON.stringify(schema, null, 2), `${this.processKey || 'workflow'}.form.json`);
  }

  private async initBpmnModeler(): Promise<void> {
    const BpmnModeler = (await import('bpmn-js/lib/Modeler')).default;
    const { BpmnPropertiesPanelModule, BpmnPropertiesProviderModule } = await import(
      'bpmn-js-properties-panel'
    );
    const spiffworkflowModule = (await import('bpmn-js-spiffworkflow')).default;

    const canvasEl = this.bpmnCanvas.nativeElement;
    const propertiesEl = this.propertiesPanel.nativeElement;

    const modeler = new BpmnModeler({
      container: canvasEl,
      propertiesPanel: {
        parent: propertiesEl
      },
      additionalModules: [BpmnPropertiesPanelModule, BpmnPropertiesProviderModule, spiffworkflowModule]
    });

    this.destroyRef.onDestroy(() => {
      try {
        modeler.destroy();
      } catch {
        // ignore
      }
    });

    this.bpmnModeler = modeler;

    await this.importBpmnXml(this.defaultBpmnXml);
  }

  private async initFormEditor(): Promise<void> {
    const { FormEditor } = await import('@bpmn-io/form-js');
    const hostEl = this.formEditorHost.nativeElement;

    const editor = new FormEditor({
      container: hostEl
    });

    this.destroyRef.onDestroy(() => {
      try {
        editor.destroy();
      } catch {
        // ignore
      }
    });

    this.formEditor = editor;
    await editor.importSchema(this.currentFormSchema);
  }

  private async importBpmnXml(xml: string): Promise<BpmnImportResult> {
    return await new Promise((resolve, reject) => {
      this.bpmnModeler.importXML(xml, (err: unknown, result: BpmnImportResult) => {
        if (err) reject(err);
        else resolve(result);
      });
    });
  }

  private async saveBpmnXml(): Promise<BpmnSaveXmlResult> {
    return await new Promise((resolve, reject) => {
      this.bpmnModeler.saveXML({ format: true }, (err: unknown, result: BpmnSaveXmlResult) => {
        if (err) reject(err);
        else resolve(result);
      });
    });
  }

  private downloadText(content: string, fileName: string): void {
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    a.click();
    URL.revokeObjectURL(url);
  }
}
