import React, { useState, useEffect, useCallback } from 'react';
import {
  Skull,
  RotateCcw,
  Trash2,
  RefreshCw,
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  Loader2,
  CheckCircle2,
} from 'lucide-react';
import { fetchDlqJobs, retryDlqJob, discardDlqJob } from '../lib/api';
import type { Job } from '../lib/types';
import { useJobEvents } from '../hooks/useJobEvents';
import { StatusBadge } from '../components/StatusBadge';
import { Pagination } from '../components/Pagination';

const PER_PAGE = 20;

export const DlqPage: React.FC = () => {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Expanded job details row IDs
  const [expandedJobIds, setExpandedJobIds] = useState<Set<string>>(new Set());

  // Action loading state tracking per job ID
  const [actionLoadingIds, setActionLoadingIds] = useState<Set<string>>(new Set());
  const [actionSuccessMsg, setActionSuccessMsg] = useState<string | null>(null);

  const { lastEvent } = useJobEvents();

  const loadDlqJobs = useCallback(async (targetPage: number) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchDlqJobs({ page: targetPage, per_page: PER_PAGE });
      setJobs(data.jobs);
      setTotal(data.total);
      setPage(data.page);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch DLQ jobs');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDlqJobs(page);
  }, [page, loadDlqJobs]);

  // Live WebSocket patching: If a dead job is retried or modified externally, remove it from list
  useEffect(() => {
    if (!lastEvent) return;
    const { job_id, old_status } = lastEvent;

    if (old_status === 'dead') {
      setJobs((prev) => prev.filter((j) => j.id !== job_id));
      setTotal((prev) => Math.max(0, prev - 1));
    }
  }, [lastEvent]);

  const toggleExpand = (jobId: string) => {
    setExpandedJobIds((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
  };

  const handleRetry = async (jobId: string) => {
    setActionLoadingIds((prev) => new Set(prev).add(jobId));
    try {
      await retryDlqJob(jobId);
      setActionSuccessMsg(`Job ${jobId.slice(0, 8)} re-queued successfully.`);
      // Optimistically remove from local DLQ list
      setJobs((prev) => prev.filter((j) => j.id !== jobId));
      setTotal((prev) => Math.max(0, prev - 1));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry job');
    } finally {
      setActionLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
      setTimeout(() => setActionSuccessMsg(null), 4000);
    }
  };

  const handleDiscard = async (jobId: string) => {
    if (!window.confirm(`Permanently discard dead job ${jobId.slice(0, 8)}?`)) return;

    setActionLoadingIds((prev) => new Set(prev).add(jobId));
    try {
      await discardDlqJob(jobId);
      setActionSuccessMsg(`Job ${jobId.slice(0, 8)} discarded.`);
      setJobs((prev) => prev.filter((j) => j.id !== jobId));
      setTotal((prev) => Math.max(0, prev - 1));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to discard job');
    } finally {
      setActionLoadingIds((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
      setTimeout(() => setActionSuccessMsg(null), 4000);
    }
  };

  const formatDate = (iso: string) => {
    return new Date(iso).toLocaleDateString('en-US', {
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
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2.5">
            <Skull className="w-6 h-6 text-status-failed" />
            Dead Letter Queue
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            Inspect, retry, or discard jobs that have exhausted max retry attempts
          </p>
        </div>

        <button
          onClick={() => loadDlqJobs(page)}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-border
                     text-sm text-text-secondary hover:text-text-primary hover:bg-bg-tertiary
                     disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh DLQ
        </button>
      </div>

      {/* ── Action Toast Alert ──────────────────────────────── */}
      {actionSuccessMsg && (
        <div className="rounded-xl border border-status-succeeded/30 bg-status-succeeded/10 px-4 py-3 flex items-center gap-2">
          <CheckCircle2 className="w-4 h-4 text-status-succeeded shrink-0" />
          <span className="text-sm text-status-succeeded font-medium">{actionSuccessMsg}</span>
        </div>
      )}

      {/* ── Error Banner ────────────────────────────────────── */}
      {error && (
        <div className="rounded-xl border border-status-failed/30 bg-status-failed/10 px-5 py-4">
          <p className="text-sm text-status-failed">{error}</p>
        </div>
      )}

      {/* ── Table Container ─────────────────────────────────── */}
      <div className="rounded-xl border border-border bg-bg-secondary overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border">
                <th className="w-10 px-4 py-3"></th>
                <th className="px-4 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  ID
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Type
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Attempts
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Failed Error Message
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-text-muted uppercase tracking-wider">
                  Failed At
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-text-muted uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {isLoading && jobs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-5 py-12 text-center">
                    <Loader2 className="w-5 h-5 mx-auto text-text-muted animate-spin" />
                    <p className="mt-2 text-sm text-text-muted">Loading Dead Letter Queue…</p>
                  </td>
                </tr>
              ) : jobs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-5 py-12 text-center">
                    <div className="flex flex-col items-center gap-2">
                      <CheckCircle2 className="w-8 h-8 text-status-succeeded" />
                      <p className="text-sm font-medium text-text-primary">DLQ is clear!</p>
                      <p className="text-xs text-text-muted">
                        No dead jobs currently requiring intervention.
                      </p>
                    </div>
                  </td>
                </tr>
              ) : (
                jobs.map((job) => {
                  const isExpanded = expandedJobIds.has(job.id);
                  const isBusy = actionLoadingIds.has(job.id);

                  return (
                    <React.Fragment key={job.id}>
                      <tr className="hover:bg-bg-tertiary/40 transition-colors group">
                        {/* Expand Toggle */}
                        <td className="px-4 py-3 text-center">
                          <button
                            onClick={() => toggleExpand(job.id)}
                            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-bg-tertiary"
                          >
                            {isExpanded ? (
                              <ChevronDown className="w-4 h-4" />
                            ) : (
                              <ChevronRight className="w-4 h-4" />
                            )}
                          </button>
                        </td>

                        {/* ID */}
                        <td className="px-4 py-3">
                          <code className="text-xs font-mono text-text-secondary group-hover:text-accent transition-colors">
                            {job.id.slice(0, 8)}…
                          </code>
                        </td>

                        {/* Type */}
                        <td className="px-4 py-3">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-bg-elevated text-text-primary border border-border">
                            {job.job_type}
                          </span>
                        </td>

                        {/* Status */}
                        <td className="px-4 py-3">
                          <StatusBadge status={job.status} />
                        </td>

                        {/* Attempts */}
                        <td className="px-4 py-3">
                          <span className="text-xs font-mono text-status-failed font-semibold">
                            {job.attempts}/{job.max_attempts}
                          </span>
                        </td>

                        {/* Error Snippet */}
                        <td className="px-4 py-3 max-w-xs truncate">
                          <span className="text-xs font-mono text-status-failed/90 truncate block">
                            {job.error || 'Unknown execution failure'}
                          </span>
                        </td>

                        {/* Updated At */}
                        <td className="px-4 py-3">
                          <span className="text-xs text-text-muted">
                            {formatDate(job.updated_at)}
                          </span>
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-3 text-right space-x-2">
                          <button
                            onClick={() => handleRetry(job.id)}
                            disabled={isBusy}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium
                                       bg-accent-muted text-accent hover:bg-accent hover:text-white
                                       disabled:opacity-50 transition-all"
                            title="Reset attempts and re-enqueue job"
                          >
                            {isBusy ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <RotateCcw className="w-3 h-3" />
                            )}
                            Retry
                          </button>

                          <button
                            onClick={() => handleDiscard(job.id)}
                            disabled={isBusy}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium
                                       bg-status-failed/10 text-status-failed hover:bg-status-failed hover:text-white
                                       disabled:opacity-50 transition-all"
                            title="Discard job permanently"
                          >
                            <Trash2 className="w-3 h-3" />
                            Discard
                          </button>
                        </td>
                      </tr>

                      {/* Expanded Details Drawer */}
                      {isExpanded && (
                        <tr className="bg-bg-primary/60 border-b border-border">
                          <td colSpan={8} className="px-6 py-4 space-y-3">
                            <div className="flex items-center justify-between text-xs text-text-muted font-medium uppercase tracking-wider">
                              <span className="flex items-center gap-1.5 text-status-failed">
                                <AlertTriangle className="w-3.5 h-3.5" />
                                Execution Trace & Diagnostic Details
                              </span>
                              <span className="font-mono">Idempotency Key: {job.idempotency_key}</span>
                            </div>

                            {/* Full Error Stack Trace Box */}
                            <div className="rounded-lg border border-status-failed/30 bg-status-failed/5 p-3.5 font-mono text-xs text-status-failed overflow-x-auto">
                              <p className="font-semibold mb-1">Error Summary:</p>
                              {job.error || 'No error details logged.'}
                            </div>

                            {/* Payload Details */}
                            <div>
                              <span className="text-xs text-text-muted font-medium block mb-1">
                                Job Payload (JSON):
                              </span>
                              <pre className="rounded-lg border border-border bg-bg-secondary p-3 text-xs text-text-primary font-mono overflow-x-auto">
                                {JSON.stringify(job.payload, null, 2)}
                              </pre>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {total > 0 && (
          <Pagination
            page={page}
            perPage={PER_PAGE}
            total={total}
            onPageChange={(p) => setPage(p)}
          />
        )}
      </div>
    </div>
  );
};
