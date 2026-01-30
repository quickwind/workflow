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
  @ViewChild('viewerHost', { static: true }) private readonly viewerHost!: ElementRef<HTMLDivElement>;

  instance: WorkflowInstanceDetail | null = null;
  status = 'Loading instance...';
  private renderResult: RenderResult | null = null;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly workflowsApi: WorkflowsApiService,
    private readonly destroyRef: DestroyRef
  ) {
    this.destroyRef.onDestroy(() => this.cleanup());
  }

  async ngAfterViewInit(): Promise<void> {
    const instanceId = Number(this.route.snapshot.paramMap.get('instanceId'));
    if (!Number.isFinite(instanceId)) {
      this.status = 'Invalid instance id';
      return;
    }

    try {
      this.instance = await firstValueFrom(this.workflowsApi.getWorkflowInstance(instanceId));
      if (!this.instance.bpmnXml) {
        this.status = 'Missing BPMN XML for instance';
        return;
      }
      this.renderResult = await render(this.viewerHost.nativeElement, this.instance.bpmnXml, this.instance.state);
      this.status = 'Ready';
    } catch (err) {
      this.status = 'Failed to load instance';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

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
