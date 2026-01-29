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
import { isPlatformBrowser } from '@angular/common';
import { firstValueFrom } from 'rxjs';
import { WorkflowsApiService } from '../core/workflows-api.service';

type BpmnImportResult = { warnings?: unknown[] };
type BpmnSaveXmlResult = { xml: string };

@Component({
  selector: 'app-designer',
  imports: [FormsModule],
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

  status = 'Idle';

  private readonly isBrowser: boolean;
  private bpmnModeler: any | null = null;
  private formEditor: any | null = null;

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

    this.status = 'Ready';
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

    this.status = `Saving ${processKey}...`;

    try {
      const { xml } = await this.saveBpmnXml();
      const schema = this.formEditor.saveSchema();

      await firstValueFrom(
        this.workflowsApi.uploadWorkflow({
          processKey,
          bpmnXml: xml,
          formSchema: schema
        })
      );

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
