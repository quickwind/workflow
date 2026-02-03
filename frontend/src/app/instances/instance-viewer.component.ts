/**
 * This component is responsible for displaying a single workflow instance.
 * It uses the 'bpmn-instance-viewer-js' extension to render the BPMN diagram
 * with status highlights and detailed tooltips for each task.
 */
import {
  AfterViewInit,
  Component,
  DestroyRef,
  ElementRef,
  ViewChild
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { render, type RenderResult } from 'bpmn-instance-viewer-js';
import { WorkflowsApiService, type WorkflowInstanceDetail } from '../core/workflows-api.service';

@Component({
  selector: 'app-instance-viewer',
  imports: [CommonModule],
  templateUrl: './instance-viewer.component.html',
  styleUrl: './instance-viewer.component.css'
})
export class InstanceViewerComponent implements AfterViewInit {
  // The DOM element where the BPMN viewer will be mounted.
  @ViewChild('viewerHost', { static: true }) private readonly viewerHost!: ElementRef<HTMLDivElement>;

  // --- Component State ---
  instance: WorkflowInstanceDetail | null = null;
  status = 'Loading instance...';
  
  // Holds the result from the viewer's render function, including the destroy method.
  private renderResult: RenderResult | null = null;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly workflowsApi: WorkflowsApiService,
    private readonly destroyRef: DestroyRef
  ) {
    // Register a cleanup function to be called when the component is destroyed.
    this.destroyRef.onDestroy(() => this.cleanup());
  }

  /**
   * After the view is initialized, this hook fetches the instance details from the
   * backend and uses the bpmn-instance-viewer-js extension to render the diagram.
   */
  async ngAfterViewInit(): Promise<void> {
    const instanceId = Number(this.route.snapshot.paramMap.get('instanceId'));
    if (!Number.isFinite(instanceId)) {
      this.status = 'Invalid instance id';
      return;
    }

    try {
      // 1. Fetch the detailed instance data from the API.
      this.instance = await firstValueFrom(this.workflowsApi.getWorkflowInstance(instanceId));
      if (!this.instance.bpmnXml) {
        this.status = 'Missing BPMN XML for instance';
        return;
      }
      
      // 2. Call the render function from the viewer extension, passing it the container,
      //    the BPMN XML, and the rich state object.
      this.renderResult = await render(this.viewerHost.nativeElement, this.instance.bpmnXml, this.instance.state);
      this.status = 'Ready';
    } catch (err) {
      this.status = 'Failed to load instance';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  /**
   * Cleans up the bpmn-js viewer instance to prevent memory leaks when the
   * component is destroyed.
   */
  private cleanup(): void {
    if (this.renderResult) {
      try {
        this.renderResult.destroy();
      } finally {
        this.renderResult = null;
      }
    }
  }
}
