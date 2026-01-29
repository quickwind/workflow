import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { environment } from '../../environments/environment';
import { map, Observable } from 'rxjs';

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
  }): Observable<unknown> {
    const formData = new FormData();
    const blob = new Blob([params.bpmnXml], { type: 'application/xml' });
    formData.append('bpmn', blob, `${params.processKey || 'workflow'}.bpmn`);
    return this.http.post(this.url('/api/workflows'), formData);
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
