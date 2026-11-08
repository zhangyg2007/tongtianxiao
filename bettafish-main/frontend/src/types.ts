export interface ObjectRow {
  object_id: number;
  object_type: 'company' | 'person' | 'event';
  natural_key: string | null;
  display_name: string;
  display_meta: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface TaskRow {
  task_id: string;
  product_line: 'dd' | 'pr';
  task_type: string;
  object_id: number | null;
  status: 'queued' | 'running' | 'waiting_input' | 'succeeded' | 'failed' | 'canceled';
  progress: number;
  stage: string | null;
  input: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: { code?: string; message?: string } | null;
  requested_by: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface StepRow {
  step_id: number;
  task_id: string;
  seq: number;
  name: string;
  status: 'running' | 'succeeded' | 'failed' | string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  detail: Record<string, unknown> | null;
}

export interface EvidenceRow {
  evidence_id: number;
  object_id: number;
  task_id: string | null;
  fact: string;
  fact_type: string;
  value_json: Record<string, unknown> | null;
  source_type: string;
  source_name: string | null;
  source_url: string;
  quote: string | null;
  published_at: string | null;
  captured_at: string;
  confidence: number;
  confidence_reason: string | null;
  verify_status: string;
}

export interface ArtifactRow {
  artifact_id: string;
  task_id: string;
  object_id: number | null;
  artifact_type: string;
  template_code: string | null;
  version: number;
  status: string;
  storage_path: string | null;
  title: string | null;
  created_at: string;
}
