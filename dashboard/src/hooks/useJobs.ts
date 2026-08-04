import { useState, useEffect, useCallback, useRef } from 'react';
import type { Job, JobListParams, JobListResponse, JobEvent } from '../lib/types';
import { fetchJobs } from '../lib/api';

/**
 * useJobs — Manages job list state with server fetching + live WebSocket patching.
 *
 * Design choice: Optimistic in-place patching.
 * When a WebSocket event arrives, we mutate the local jobs array's status field
 * directly instead of re-fetching the entire list from the API. This gives
 * instant UI feedback (sub-millisecond) and avoids hammering the API on every
 * state transition.
 *
 * Alternative not chosen: Full re-fetch on every WebSocket event.
 * Simpler to reason about (always consistent with the server), but creates
 * O(n) API calls per second under load — exactly the thundering-herd pattern
 * our Redis cache layer was designed to mitigate. In-place patching keeps
 * the dashboard snappy without adding backend pressure.
 *
 * Caveat: The local patch only updates `status`. Fields like `attempts`,
 * `updated_at`, and `error` won't reflect until the next poll/refetch.
 * For a dashboard, this is acceptable — status is the primary visual indicator.
 */

interface UseJobsOptions {
  params: JobListParams;
  /** Auto-refresh interval in ms. 0 = no auto-refresh. */
  refreshInterval?: number;
}

interface UseJobsReturn {
  jobs: Job[];
  total: number;
  page: number;
  perPage: number;
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
}

export function useJobs(
  { params, refreshInterval = 0 }: UseJobsOptions,
  lastEvent: JobEvent | null
): UseJobsReturn {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(20);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Track the latest params to avoid stale closures in the interval
  const paramsRef = useRef(params);
  paramsRef.current = params;

  const doFetch = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data: JobListResponse = await fetchJobs(paramsRef.current);
      setJobs(data.jobs);
      setTotal(data.total);
      setPage(data.page);
      setPerPage(data.per_page);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch jobs');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetch on mount and when params change
  useEffect(() => {
    doFetch();
  }, [params.status, params.page, params.per_page, doFetch]);

  // Optional auto-refresh polling
  useEffect(() => {
    if (refreshInterval <= 0) return;
    const timer = setInterval(doFetch, refreshInterval);
    return () => clearInterval(timer);
  }, [refreshInterval, doFetch]);

  // ── Live WebSocket Patching ───────────────────────────────
  // When a JobEvent arrives, patch the matching job in our local list.
  useEffect(() => {
    if (!lastEvent) return;

    setJobs((prev) =>
      prev.map((job) =>
        job.id === lastEvent.job_id
          ? { ...job, status: lastEvent.new_status }
          : job
      )
    );
  }, [lastEvent]);

  return { jobs, total, page, perPage, isLoading, error, refetch: doFetch };
}
