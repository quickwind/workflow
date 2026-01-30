import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../environments/environment';
import { map, Observable } from 'rxjs';

import type { InstanceState } from 'bpmn-instance-viewer-js';

declare global {
  interface Window {
    __APP_CONFIG__?: {
      apiBaseUrl?: string;
    };
  }
}

export type WorkflowVersion = {
  bpmnXml: string;
  formSchema: unknown | null;
};

export type WorkflowGroupTreeNode = {
  id: number;
  name: string;
  description: string;
  children: WorkflowGroupTreeNode[];
};

export type WorkflowGroup = {
  id: number;
  parentId: number | null;
  parentName: string;
  name: string;
  description: string;
  createdAt: string;
  updatedAt: string;
};

export type WorkflowDefinitionListItem = {
  processKey: string;
  name: string;
  description: string;
  groupId: number | null;
  groupName: string;
  latestVersion: number | null;
  createdAt: string;
  updatedAt: string;
};

export type WorkflowInstanceListItem = {
  id: number;
  processKey: string;
  version: number;
  status: string;
  correlationId: string;
  businessKey: string;
  createdAt: string;
  updatedAt: string;
};

export type WorkflowInstanceDetail = {
  id: number;
  processKey: string;
  version: number;
  status: string;
  correlationId: string;
  businessKey: string;
  createdAt: string;
  updatedAt: string;
  bpmnXml: string;
  state: InstanceState;
};

@Injectable({
  providedIn: 'root'
})
export class WorkflowsApiService {
  private readonly apiBaseUrl = (this.readApiBaseUrl() || '').replace(/\/$/, '');

  constructor(private readonly http: HttpClient) {}

  private readApiBaseUrl(): string {
    if (environment.apiBaseUrl) return environment.apiBaseUrl;
    if (typeof window === 'undefined') return '';
    return window.__APP_CONFIG__?.apiBaseUrl || '';
  }

  uploadWorkflow(params: {
    processKey: string;
    bpmnXml: string;
    formSchema: unknown | null;
    name?: string;
    description?: string;
    groupId?: number | null;
  }): Observable<unknown> {
    const formData = new FormData();
    const blob = new Blob([params.bpmnXml], { type: 'application/xml' });
    formData.append('bpmn', blob, `${params.processKey || 'workflow'}.bpmn`);

    if (typeof params.name === 'string') formData.append('name', params.name);
    if (typeof params.description === 'string') formData.append('description', params.description);
    if (typeof params.groupId === 'number') formData.append('group_id', String(params.groupId));
    else if (params.groupId === null) formData.append('group_id', '');

    return this.http.post(this.url('/api/workflows'), formData);
  }

  getWorkflowGroupsTree(): Observable<WorkflowGroupTreeNode[]> {
    return this.http
      .get<unknown>(this.url('/api/workflow-groups/tree'))
      .pipe(map((raw) => this.normalizeWorkflowGroupTree(raw)));
  }

  createWorkflowGroup(params: {
    name: string;
    parentId: number | null;
    description?: string;
  }): Observable<WorkflowGroup> {
    return this.http
      .post<unknown>(this.url('/api/workflow-groups'), {
        name: params.name,
        description: params.description ?? '',
        parent_id: params.parentId
      })
      .pipe(map((raw) => this.normalizeWorkflowGroup(raw)));
  }

  patchWorkflowGroup(
    groupId: number,
    params: { name?: string; description?: string; parentId?: number | null }
  ): Observable<WorkflowGroup> {
    const body: Record<string, unknown> = {};
    if (typeof params.name === 'string') body['name'] = params.name;
    if (typeof params.description === 'string') body['description'] = params.description;
    if ('parentId' in params) body['parent_id'] = params.parentId;

    return this.http
      .patch<unknown>(this.url(`/api/workflow-groups/${encodeURIComponent(String(groupId))}`), body)
      .pipe(map((raw) => this.normalizeWorkflowGroup(raw)));
  }

  deleteWorkflowGroup(groupId: number): Observable<void> {
    return this.http.delete<void>(this.url(`/api/workflow-groups/${encodeURIComponent(String(groupId))}`));
  }

  listWorkflowDefinitions(params?: { groupId?: number | null; ungrouped?: boolean }): Observable<
    WorkflowDefinitionListItem[]
  > {
    const query: string[] = [];
    if (params?.ungrouped) query.push(`group_id=`);
    else if (typeof params?.groupId === 'number') query.push(`group_id=${encodeURIComponent(String(params.groupId))}`);

    const suffix = query.length ? `?${query.join('&')}` : '';
    return this.http
      .get<unknown>(this.url(`/api/workflows/list${suffix}`))
      .pipe(map((raw) => this.normalizeWorkflowDefinitionList(raw)));
  }

  listWorkflowInstances(processKey: string): Observable<WorkflowInstanceListItem[]> {
    const safeKey = encodeURIComponent(processKey);
    return this.http
      .get<unknown>(this.url(`/api/workflows/${safeKey}/instances`))
      .pipe(map((raw) => this.normalizeWorkflowInstanceList(raw)));
  }

  getWorkflowInstance(instanceId: number): Observable<WorkflowInstanceDetail> {
    return this.http
      .get<unknown>(this.url(`/api/instances/${encodeURIComponent(String(instanceId))}`))
      .pipe(map((raw) => this.normalizeWorkflowInstanceDetail(raw)));
  }

  patchWorkflowDefinition(
    processKey: string,
    params: { name?: string; description?: string; groupId?: number | null }
  ): Observable<WorkflowDefinitionListItem> {
    const body: Record<string, unknown> = {};
    if (typeof params.name === 'string') body['name'] = params.name;
    if (typeof params.description === 'string') body['description'] = params.description;
    if ('groupId' in params) body['group_id'] = params.groupId;

    const safeKey = encodeURIComponent(processKey);
    return this.http
      .patch<unknown>(this.url(`/api/workflows/${safeKey}`), body)
      .pipe(map((raw) => this.normalizeWorkflowDefinitionListItem(raw)));
  }

  getWorkflowVersion(processKey: string, version: number): Observable<WorkflowVersion> {
    const safeKey = encodeURIComponent(processKey);
    const safeVersion = encodeURIComponent(String(version));

    return this.http
      .get<unknown>(this.url(`/api/workflows/${safeKey}/versions/${safeVersion}`))
      .pipe(map((raw) => this.normalizeWorkflowVersion(raw)));
  }

  private url(path: string): string {
    if (!this.apiBaseUrl) return path;
    if (path.startsWith('/')) return `${this.apiBaseUrl}${path}`;
    return `${this.apiBaseUrl}/${path}`;
  }

  private normalizeWorkflowGroupTree(raw: unknown): WorkflowGroupTreeNode[] {
    if (!Array.isArray(raw)) return [];
    return raw
      .map((node) => this.normalizeWorkflowGroupTreeNode(node))
      .filter((n): n is WorkflowGroupTreeNode => Boolean(n));
  }

  private normalizeWorkflowGroupTreeNode(raw: unknown): WorkflowGroupTreeNode | null {
    if (!raw || typeof raw !== 'object') return null;
    const r = raw as Record<string, unknown>;
    const id = Number(r['id']);
    if (!Number.isFinite(id)) return null;

    const name = typeof r['name'] === 'string' ? r['name'] : '';
    const description = typeof r['description'] === 'string' ? r['description'] : '';
    const childrenRaw = r['children'];
    const children = Array.isArray(childrenRaw)
      ? childrenRaw
          .map((child) => this.normalizeWorkflowGroupTreeNode(child))
          .filter((c): c is WorkflowGroupTreeNode => Boolean(c))
      : [];

    return { id, name, description, children };
  }

  private normalizeWorkflowGroup(raw: unknown): WorkflowGroup {
    if (!raw || typeof raw !== 'object') {
      return {
        id: 0,
        parentId: null,
        parentName: '',
        name: '',
        description: '',
        createdAt: '',
        updatedAt: ''
      };
    }

    const r = raw as Record<string, unknown>;

    const id = Number(r['id']);
    const parentIdRaw = r['parent_id'] ?? r['parentId'];
    const parentId = parentIdRaw === null || parentIdRaw === undefined ? null : Number(parentIdRaw);

    return {
      id: Number.isFinite(id) ? id : 0,
      parentId: parentId !== null && Number.isFinite(parentId) ? parentId : null,
      parentName: typeof r['parent_name'] === 'string' ? (r['parent_name'] as string) : '',
      name: typeof r['name'] === 'string' ? (r['name'] as string) : '',
      description: typeof r['description'] === 'string' ? (r['description'] as string) : '',
      createdAt: typeof r['created_at'] === 'string' ? (r['created_at'] as string) : '',
      updatedAt: typeof r['updated_at'] === 'string' ? (r['updated_at'] as string) : ''
    };
  }

  private normalizeWorkflowDefinitionList(raw: unknown): WorkflowDefinitionListItem[] {
    if (!Array.isArray(raw)) return [];
    return raw
      .map((item) => this.normalizeWorkflowDefinitionListItem(item))
      .filter((v): v is WorkflowDefinitionListItem => Boolean(v));
  }

  private normalizeWorkflowDefinitionListItem(raw: unknown): WorkflowDefinitionListItem {
    if (!raw || typeof raw !== 'object') {
      return {
        processKey: '',
        name: '',
        description: '',
        groupId: null,
        groupName: '',
        latestVersion: null,
        createdAt: '',
        updatedAt: ''
      };
    }

    const r = raw as Record<string, unknown>;
    const processKey = typeof r['process_key'] === 'string' ? (r['process_key'] as string) : '';
    const groupIdRaw = r['group_id'] ?? r['groupId'];
    const groupId = groupIdRaw === null || groupIdRaw === undefined ? null : Number(groupIdRaw);
    const latestRaw = r['latest_version'] ?? r['latestVersion'];
    const latest = latestRaw === null || latestRaw === undefined ? null : Number(latestRaw);

    return {
      processKey,
      name: typeof r['name'] === 'string' ? (r['name'] as string) : '',
      description: typeof r['description'] === 'string' ? (r['description'] as string) : '',
      groupId: groupId !== null && Number.isFinite(groupId) ? groupId : null,
      groupName: typeof r['group_name'] === 'string' ? (r['group_name'] as string) : '',
      latestVersion: latest !== null && Number.isFinite(latest) ? latest : null,
      createdAt: typeof r['created_at'] === 'string' ? (r['created_at'] as string) : '',
      updatedAt: typeof r['updated_at'] === 'string' ? (r['updated_at'] as string) : ''
    };
  }

  private normalizeWorkflowInstanceList(raw: unknown): WorkflowInstanceListItem[] {
    if (!Array.isArray(raw)) return [];
    return raw
      .map((item) => this.normalizeWorkflowInstanceListItem(item))
      .filter((v): v is WorkflowInstanceListItem => Boolean(v));
  }

  private normalizeWorkflowInstanceListItem(raw: unknown): WorkflowInstanceListItem {
    if (!raw || typeof raw !== 'object') {
      return {
        id: 0,
        processKey: '',
        version: 0,
        status: '',
        correlationId: '',
        businessKey: '',
        createdAt: '',
        updatedAt: ''
      };
    }

    const r = raw as Record<string, unknown>;
    const id = Number(r['id']);
    const version = Number(r['version']);

    return {
      id: Number.isFinite(id) ? id : 0,
      processKey: typeof r['process_key'] === 'string' ? (r['process_key'] as string) : '',
      version: Number.isFinite(version) ? version : 0,
      status: typeof r['status'] === 'string' ? (r['status'] as string) : '',
      correlationId: typeof r['correlation_id'] === 'string' ? (r['correlation_id'] as string) : '',
      businessKey: typeof r['business_key'] === 'string' ? (r['business_key'] as string) : '',
      createdAt: typeof r['created_at'] === 'string' ? (r['created_at'] as string) : '',
      updatedAt: typeof r['updated_at'] === 'string' ? (r['updated_at'] as string) : ''
    };
  }

  private normalizeWorkflowInstanceDetail(raw: unknown): WorkflowInstanceDetail {
    const base = this.normalizeWorkflowInstanceListItem(raw);
    if (!raw || typeof raw !== 'object') {
      return {
        ...base,
        bpmnXml: '',
        state: { tasks: [], sequenceFlows: [] }
      };
    }

    const r = raw as Record<string, unknown>;
    const bpmnXml = typeof r['bpmn_xml'] === 'string' ? (r['bpmn_xml'] as string) : '';
    const state = (r['state'] as InstanceState) || { tasks: [], sequenceFlows: [] };
    return {
      ...base,
      bpmnXml,
      state
    };
  }

  private normalizeWorkflowVersion(raw: unknown): WorkflowVersion {
    if (raw && typeof raw === 'object') {
      const r = raw as Record<string, unknown>;

      const bpmnXml =
        (typeof r['bpmn_xml'] === 'string' && (r['bpmn_xml'] as string)) ||
        (typeof r['bpmnXml'] === 'string' && (r['bpmnXml'] as string)) ||
        (typeof r['bpmn'] === 'string' && (r['bpmn'] as string)) ||
        (typeof r['xml'] === 'string' && (r['xml'] as string)) ||
        (typeof r['workflow'] === 'object' &&
          r['workflow'] &&
          typeof (r['workflow'] as Record<string, unknown>)['bpmn_xml'] === 'string' &&
          ((r['workflow'] as Record<string, unknown>)['bpmn_xml'] as string)) ||
        '';

      const formSchemaRaw =
        (r['form_schema'] as unknown) ??
        (r['formSchema'] as unknown) ??
        (typeof r['workflow'] === 'object' && r['workflow']
          ? (r['workflow'] as Record<string, unknown>)['form_schema'] ??
            (r['workflow'] as Record<string, unknown>)['formSchema']
          : null) ??
        null;

      const formSchema = this.coerceJsonObject(formSchemaRaw);

      return { bpmnXml, formSchema };
    }

    return { bpmnXml: '', formSchema: null };
  }

  private coerceJsonObject(value: unknown): unknown | null {
    if (!value) return null;
    if (typeof value === 'object') return value;
    if (typeof value === 'string') {
      try {
        const parsed = JSON.parse(value) as unknown;
        return parsed && typeof parsed === 'object' ? parsed : null;
      } catch {
        return null;
      }
    }
    return null;
  }
}
