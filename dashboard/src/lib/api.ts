import type {
  Job,
  JobListResponse,
  JobListParams,
  CreateJobBody,
  HealthResponse,
  MetricsResponse,
  WorkersResponse,
} from './types';

const API_BASE = '/api';
const API_KEY = 'forge_dev_key_123';

/* ── Generic Fetch Wrapper ───────────────────────────────── */
async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY,
    ...(options.headers as Record<string, string> || {}),
  };

  const res = await fetch(url, { ...options, headers });

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({}));
    throw new ApiError(
      res.status,
      errorBody.detail || res.statusText,
      res.headers.get('Retry-After')
    );
  }

  return res.json() as Promise<T>;
}

/* ── Custom Error Class ──────────────────────────────────── */
export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public retryAfter: string | null = null
  ) {
    super(`API Error ${status}: ${detail}`);
    this.name = 'ApiError';
  }
}

/* ── Jobs ────────────────────────────────────────────────── */
export async function fetchJobs(params: JobListParams = {}): Promise<JobListResponse> {
  const searchParams = new URLSearchParams();
  if (params.status) searchParams.set('status', params.status);
  if (params.page) searchParams.set('page', String(params.page));
  if (params.per_page) searchParams.set('per_page', String(params.per_page));

  const qs = searchParams.toString();
  return request<JobListResponse>(`/jobs${qs ? `?${qs}` : ''}`);
}

export async function fetchJob(id: string): Promise<Job> {
  return request<Job>(`/jobs/${id}`);
}

export async function createJob(body: CreateJobBody): Promise<Job> {
  return request<Job>('/jobs', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function deleteJob(id: string): Promise<void> {
  const res = await fetch(`/api/jobs/${id}`, {
    method: 'DELETE',
    headers: {
      'X-API-Key': 'forge_dev_key_123',
    },
  });
  if (!res.ok) {
    throw new Error('Failed to delete job');
  }
}

/* ── Dead Letter Queue ───────────────────────────────────── */
export async function fetchDlqJobs(
  params: { page?: number; per_page?: number } = {}
): Promise<JobListResponse> {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set('page', String(params.page));
  if (params.per_page) searchParams.set('per_page', String(params.per_page));

  const qs = searchParams.toString();
  return request<JobListResponse>(`/dlq${qs ? `?${qs}` : ''}`);
}

export async function retryDlqJob(id: string): Promise<Job> {
  return request<Job>(`/dlq/${id}/retry`, { method: 'POST' });
}

export async function discardDlqJob(id: string): Promise<void> {
  return request<void>(`/dlq/${id}`, { method: 'DELETE' });
}

export async function fetchMetrics(): Promise<MetricsResponse> {
  return request<MetricsResponse>('/metrics');
}

export async function fetchWorkers(): Promise<WorkersResponse> {
  return request<WorkersResponse>('/workers');
}

/* ── Health ──────────────────────────────────────────────── */
export async function fetchHealth(): Promise<HealthResponse> {
  // Health endpoint is at root, not under /api
  const res = await fetch('/health');
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  return res.json() as Promise<HealthResponse>;
}
