import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterModule, ActivatedRoute } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import {
  WorkflowDefinitionListItem,
  WorkflowInstanceListItem,
  WorkflowsApiService
} from '../core/workflows-api.service';

@Component({
  selector: 'app-instances',
  imports: [CommonModule, FormsModule, RouterModule],
  templateUrl: './instances.component.html',
  styleUrl: './instances.component.css'
})
export class InstancesComponent {
  workflows: WorkflowDefinitionListItem[] = [];
  instances: WorkflowInstanceListItem[] = [];

  processKey = '';
  status = 'Loading workflows...';

  constructor(
    private readonly workflowsApi: WorkflowsApiService,
    private readonly route: ActivatedRoute
  ) {}

  async ngOnInit(): Promise<void> {
    const queryProcessKey = this.route.snapshot.queryParamMap.get('processKey') || '';
    await this.loadWorkflows(queryProcessKey);
  }

  async loadWorkflows(initialProcessKey: string): Promise<void> {
    try {
      this.workflows = await firstValueFrom(this.workflowsApi.listWorkflowDefinitions());
      if (initialProcessKey) {
        this.processKey = initialProcessKey;
      } else if (!this.processKey && this.workflows.length) {
        this.processKey = this.workflows[0].processKey;
      }
      await this.loadInstances();
    } catch (err) {
      this.status = 'Failed to load workflows';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }

  async loadInstances(): Promise<void> {
    const key = this.processKey.trim();
    if (!key) {
      this.status = 'Select a workflow to list instances';
      this.instances = [];
      return;
    }

    this.status = `Loading instances for ${key}...`;
    try {
      this.instances = await firstValueFrom(this.workflowsApi.listWorkflowInstances(key));
      this.status = this.instances.length ? 'Ready' : 'No instances found';
    } catch (err) {
      this.status = 'Failed to load instances';
      // eslint-disable-next-line no-console
      console.error(err);
    }
  }
}
