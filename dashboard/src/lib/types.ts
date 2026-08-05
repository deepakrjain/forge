/* ── Job Status Type ──────────────────────────────────────── */
export type JobStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'retrying'
  | 'dead';

/* ── Core Job Interface ──────────────────────────────────── */
export interface Job {
  id: string;
  idempotency_key: string;
  job_type: string;
  payload: Record<string, unknown>;
  status: JobStatus;
  priority: number;
  attempts: number;
  max_attempts: number;
  created_at: string;
  updated_at: string;
  run_after: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
}

/* ── API Responses ───────────────────────────────────────── */
export interface JobListResponse {
  jobs: Job[];
  total: number;
  page: number;
  per_page: number;
}

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  database: string;
  redis: string;
  job_statuses: string[];
}

export interface MetricsResponse {
  status_counts: Record<JobStatus, number>;
  priority_breakdown: {
    high: number;
    normal: number;
    low: number;
  };
  total_jobs: number;
  active_running: number;
  dlq_count: number;
  success_rate: number;
}

export interface WorkerInfo {
  worker_id: string;
  active_jobs: number;
  concurrency: number;
  last_seen: string;
  started_at: string;
  status: string;
}

export interface WorkersResponse {
  workers: WorkerInfo[];
  total: number;
}

/* ── WebSocket Event Payload ─────────────────────────────── */
export interface JobEvent {
  job_id: string;
  old_status: JobStatus | null;
  new_status: JobStatus;
  timestamp: string;
}

/* ── API Query Parameters ────────────────────────────────── */
export interface JobListParams {
  status?: JobStatus;
  page?: number;
  per_page?: number;
}

export interface CreateJobBody {
  job_type: string;
  payload: Record<string, unknown>;
  idempotency_key: string;
  priority?: number;
  max_attempts?: number;
  run_after?: string | null;
}
