import type { ArtifactRow, EvidenceRow, ObjectRow, StepRow, TaskRow } from '../types';

const BASE = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  let body: unknown = {};
  try {
    body = await res.json();
  } catch {
    body = {};
  }
  if (!res.ok) {
    const msg = (body as { error?: string }).error;
    throw new Error(msg || `请求失败（HTTP ${res.status}）`);
  }
  return body as T;
}

export interface CreateTaskPayload {
  product_line: 'dd' | 'pr';
  task_type: string;
  input: Record<string, unknown>;
  object_id?: number;
}

export const api = {
  listObjects: (q: string = '') =>
    request<{ objects: ObjectRow[]; count: number }>(
      `/objects?q=${encodeURIComponent(q)}`,
    ),
  createObject: (data: {
    object_type: string;
    display_name: string;
    natural_key?: string;
    display_meta?: string;
  }) =>
    request<{ object_id: number }>('/objects', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  getObject: (id: number) =>
    request<{ object: ObjectRow; tasks: TaskRow[]; artifacts: ArtifactRow[] }>(
      `/objects/${id}`,
    ),
  listTasks: (params: { product_line?: string; status?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.product_line) qs.set('product_line', params.product_line);
    if (params.status) qs.set('status', params.status);
    return request<{ tasks: TaskRow[]; count: number }>(`/tasks?${qs.toString()}`);
  },
  getTask: (id: string) =>
    request<{ task: TaskRow; steps: StepRow[] }>(`/tasks/${id}`),
  createTask: (data: CreateTaskPayload) =>
    request<{ task_id: string; status: string }>('/tasks', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
  cancelTask: (id: string) =>
    request<{ task_id: string; canceled: boolean }>(`/tasks/${id}/cancel`, {
      method: 'POST',
    }),
  listArtifacts: (params: { task_id?: string; object_id?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.task_id) qs.set('task_id', params.task_id);
    if (params.object_id != null) qs.set('object_id', String(params.object_id));
    return request<{ artifacts: ArtifactRow[]; count: number }>(
      `/artifacts?${qs.toString()}`,
    );
  },
  listEvidence: (params: { task_id?: string; object_id?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.task_id) qs.set('task_id', params.task_id);
    if (params.object_id != null) qs.set('object_id', String(params.object_id));
    return request<{ evidence: EvidenceRow[]; count: number }>(
      `/evidence?${qs.toString()}`,
    );
  },
};
