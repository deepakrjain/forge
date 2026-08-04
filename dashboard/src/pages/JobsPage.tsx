import React, { useState, useMemo } from 'react';
import { Plus, RefreshCw, Filter, Loader2 } from 'lucide-react';
import type { JobStatus, JobListParams } from '../lib/types';
import { useJobs } from '../hooks/useJobs';
import { useJobEvents } from '../hooks/useJobEvents';
import { StatusBadge } from '../components/StatusBadge';
import { Pagination } from '../components/Pagination';
import { SubmitJobModal } from '../components/SubmitJobModal';

const ALL_STATUSES: JobStatus[] = [
  'queued', 'running', 'succeeded', 'failed', 'retrying', 'dead',
];

const PER_PAGE = 20;

export const JobsPage: React.FC = () => {
  // ── Filters ────────────────────────────────────────────────
  const [statusFilter, setStatusFilter] = useState<JobStatus | ''>('');
  const [currentPage, setCurrentPage] = useState(1);
  const [showModal, setShowModal] = useState(false);

  // ── WebSocket events ───────────────────────────────────────
  const { lastEvent } = useJobEvents();

  // ── Stable params object (re-created only when filters change) ──
  const params: JobListParams = useMemo(
    () => ({
      status: statusFilter || undefined,
      page: currentPage,
      per_page: PER_PAGE,
    }),
    [statusFilter, currentPage]
  );

  // ── Data fetching + live patching ──────────────────────────
  const { jobs, total, page, perPage, isLoading, error, refetch } = useJobs(
    { params, refreshInterval: 30_000 },
    lastEvent
  );

  const handleStatusFilterChange = (value: string) => {
    setStatusFilter(value as JobStatus | '');
    setCurrentPage(1); // Reset to page 1 when filter changes
  };

  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage);
  };

  const handleJobCreated = () => {
    // Re-fetch to show the newly created job
    refetch();
  };

  const formatDate = (iso: string) => {
    const d = new Date(iso);
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  return (
    <div className="space-y-6">
      {/* ── Header ──────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Jobs</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Browse, filter, and submit jobs to the queue
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium
                     bg-accent text-white hover:bg-accent-hover transition-colors"
        >
          <Plus className="w-4 h-4" />
          Submit Job
        </button>
      </div>

      {/* ── Toolbar ─────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        {/* Status filter */}
        <div className="relative flex items-center gap-2">
          <Filter className="w-4 h-4 text-text-muted" />
          <select
            value={statusFilter}
            onChange={(e) => handleStatusFilterChange(e.target.value)}
            className="appearance-none rounded-lg border border-border bg-bg-secondary px-3 py-2
                       text-sm text-text-primary focus:border-accent focus:outline-none
                       focus:ring-1 focus:ring-accent transition-colors cursor-pointer pr-8"
          >
            <option value="">All statuses</option>
            {ALL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </div>

        {/* Refresh button */}
        <button
          onClick={refetch}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-border
                     text-sm text-text-secondary hover:text-text-primary hover:bg-bg-tertiary
                     disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>

        {/* Total count */}
        <span className="ml-auto text-xs text-text-muted">
          {total} job{total !== 1 ? 's' : ''} total
        </span>
      </div>

      {/* ── Error State ─────────────────────────────────────── */}
      {error && (
        <div className="rounded-xl border border-status-failed/30 bg-status-failed/10 px-5 py-4">
          <p className="text-sm text-status-failed">{error}</p>
          <button
            onClick={refetch}
            className="mt-2 text-xs text-status-failed underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Table ───────────────────────────────────────────── */}
      <div className="rounded-xl border border-border bg-bg-secondary overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="px-5 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  ID
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Type
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Status
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Priority
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Attempts
                </th>
                <th className="px-5 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Created
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && jobs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center">
                    <Loader2 className="w-5 h-5 mx-auto text-text-muted animate-spin" />
                    <p className="mt-2 text-sm text-text-muted">Loading jobs…</p>
                  </td>
                </tr>
              ) : jobs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center">
                    <p className="text-sm text-text-muted">
                      {statusFilter
                        ? `No jobs with status "${statusFilter}"`
                        : 'No jobs yet. Submit one to get started.'}
                    </p>
                  </td>
                </tr>
              ) : (
                jobs.map((job) => (
                  <tr
                    key={job.id}
                    className="hover:bg-bg-tertiary/50 transition-colors group"
                  >
                    <td className="px-5 py-3">
                      <code className="text-xs font-mono text-text-secondary group-hover:text-accent transition-colors">
                        {job.id.slice(0, 8)}…
                      </code>
                    </td>
                    <td className="px-5 py-3">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium
                                       bg-bg-elevated text-text-primary border border-border">
                        {job.job_type}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-5 py-3">
                      <span className={`text-xs font-mono ${
                        job.priority >= 7 ? 'text-status-failed' :
                        job.priority >= 4 ? 'text-status-queued' :
                        'text-text-secondary'
                      }`}>
                        {job.priority}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-xs text-text-secondary">
                        {job.attempts}/{job.max_attempts}
                      </span>
                    </td>
                    <td className="px-5 py-3">
                      <span className="text-xs text-text-muted">
                        {formatDate(job.created_at)}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > 0 && (
          <Pagination
            page={page}
            perPage={perPage}
            total={total}
            onPageChange={handlePageChange}
          />
        )}
      </div>

      {/* ── Submit Job Modal ────────────────────────────────── */}
      <SubmitJobModal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        onJobCreated={handleJobCreated}
      />
    </div>
  );
};
