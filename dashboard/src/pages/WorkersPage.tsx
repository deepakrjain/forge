import React, { useState, useEffect, useCallback } from 'react';
import {
  Cpu,
  RefreshCw,
  Clock,
  Activity,
  AlertTriangle,
  Loader2,
  Server,
  Zap,
} from 'lucide-react';
import { fetchWorkers } from '../lib/api';
import type { WorkerInfo } from '../lib/types';

export const WorkersPage: React.FC = () => {
  const [workers, setWorkers] = useState<WorkerInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState<number>(Date.now());

  const loadWorkers = useCallback(async () => {
    try {
      const data = await fetchWorkers();
      setWorkers(data.workers);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workers');
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Poll workers every 3 seconds
  useEffect(() => {
    loadWorkers();
    const interval = setInterval(loadWorkers, 3000);
    return () => clearInterval(interval);
  }, [loadWorkers]);

  // Update `now` ticker every second for accurate "last seen X s ago"
  useEffect(() => {
    const ticker = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(ticker);
  }, []);

  const getSecondsAgo = (lastSeenIso: string) => {
    const diff = Math.floor((now - new Date(lastSeenIso).getTime()) / 1000);
    return Math.max(0, diff);
  };

  const getWorkerStatus = (secondsAgo: number) => {
    if (secondsAgo <= 10) return { label: 'Online', color: 'status-succeeded', bg: 'bg-status-succeeded/10', border: 'border-status-succeeded/30' };
    if (secondsAgo <= 30) return { label: 'Stale', color: 'status-queued', bg: 'bg-status-queued/10', border: 'border-status-queued/30' };
    return { label: 'Offline', color: 'status-failed', bg: 'bg-status-failed/10', border: 'border-status-failed/30' };
  };

  const totalConcurrency = workers.reduce((sum, w) => sum + (w.concurrency || 0), 0);
  const totalActiveJobs = workers.reduce((sum, w) => sum + (w.active_jobs || 0), 0);
  const overallLoadPct = totalConcurrency > 0 ? Math.round((totalActiveJobs / totalConcurrency) * 100) : 0;

  return (
    <div className="space-y-8">
      {/* ── Header ──────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2.5">
            <Cpu className="w-6 h-6 text-accent" />
            Workers Pool
          </h1>
          <p className="mt-1 text-sm text-text-secondary">
            Live worker heartbeats, active concurrency slots, and load health
          </p>
        </div>

        <button
          onClick={loadWorkers}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-border
                     text-sm text-text-secondary hover:text-text-primary hover:bg-bg-tertiary
                     disabled:opacity-50 transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {/* ── Summary Stats ───────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Active Workers */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              Active Workers
            </span>
            <Server className="w-4 h-4 text-accent" />
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold font-mono text-text-primary">
              {workers.length}
            </span>
            <span className="text-xs text-text-muted">nodes</span>
          </div>
          <p className="mt-2 text-xs text-text-muted">Registered in Redis heartbeat cluster</p>
        </div>

        {/* Capacity */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              Total Concurrency
            </span>
            <Zap className="w-4 h-4 text-status-queued" />
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold font-mono text-text-primary">
              {totalConcurrency}
            </span>
            <span className="text-xs text-text-muted">parallel slots</span>
          </div>
          <p className="mt-2 text-xs text-text-muted">Combined worker task limit</p>
        </div>

        {/* System Load % */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              Current Load
            </span>
            <Activity className="w-4 h-4 text-status-running" />
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold font-mono text-text-primary">
              {overallLoadPct}%
            </span>
            <span className="text-xs text-text-muted">({totalActiveJobs} active)</span>
          </div>
          <div className="mt-2 w-full h-1.5 rounded-full bg-bg-primary overflow-hidden">
            <div
              className="h-full bg-accent transition-all duration-300"
              style={{ width: `${overallLoadPct}%` }}
            />
          </div>
        </div>
      </div>

      {/* ── Error Banner ────────────────────────────────────── */}
      {error && (
        <div className="rounded-xl border border-status-failed/30 bg-status-failed/10 px-5 py-4">
          <p className="text-sm text-status-failed">{error}</p>
        </div>
      )}

      {/* ── Workers Cards Grid ───────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-text-primary">Worker Instances</h2>
          <span className="text-xs text-text-muted">Heartbeat TTL: 10s</span>
        </div>

        {isLoading && workers.length === 0 ? (
          <div className="rounded-xl border border-border bg-bg-secondary p-12 text-center">
            <Loader2 className="w-6 h-6 mx-auto text-text-muted animate-spin" />
            <p className="mt-2 text-sm text-text-muted">Scanning worker heartbeats…</p>
          </div>
        ) : workers.length === 0 ? (
          <div className="rounded-xl border border-border bg-bg-secondary p-10 text-center flex flex-col items-center gap-3">
            <AlertTriangle className="w-8 h-8 text-status-queued" />
            <p className="text-sm font-medium text-text-primary">No Active Workers Found</p>
            <p className="text-xs text-text-muted max-w-md">
              Start a worker process locally using <code className="font-mono text-accent">python -m app.main</code> inside the <code className="font-mono">/worker</code> directory to see live worker telemetry here.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {workers.map((worker) => {
              const secondsAgo = getSecondsAgo(worker.last_seen);
              const status = getWorkerStatus(secondsAgo);
              const loadPct = worker.concurrency > 0
                ? Math.round((worker.active_jobs / worker.concurrency) * 100)
                : 0;

              return (
                <div
                  key={worker.worker_id}
                  className={`rounded-xl border ${status.border} bg-bg-secondary p-5 flex flex-col justify-between space-y-4 shadow-sm hover:border-accent/40 transition-all`}
                >
                  {/* Card Top: Worker ID & Status Badge */}
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Cpu className="w-4 h-4 text-accent" />
                      <span className="font-mono font-semibold text-sm text-text-primary">
                        {worker.worker_id}
                      </span>
                    </div>
                    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold ${status.bg} text-${status.color}`}>
                      <span className={`w-1.5 h-1.5 rounded-full bg-current ${status.label === 'Online' ? 'animate-pulse' : ''}`} />
                      {status.label}
                    </span>
                  </div>

                  {/* Load Progress Bar */}
                  <div className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-text-secondary font-medium">Task Concurrency</span>
                      <span className="font-mono font-semibold text-text-primary">
                        {worker.active_jobs} / {worker.concurrency} ({loadPct}%)
                      </span>
                    </div>
                    <div className="w-full h-2 rounded-full bg-bg-primary overflow-hidden">
                      <div
                        className={`h-full transition-all duration-300 ${
                          loadPct >= 90 ? 'bg-status-failed' :
                          loadPct >= 50 ? 'bg-status-queued' :
                          'bg-accent'
                        }`}
                        style={{ width: `${loadPct}%` }}
                      />
                    </div>
                  </div>

                  {/* Card Bottom Metadata */}
                  <div className="pt-3 border-t border-border flex items-center justify-between text-xs text-text-muted">
                    <div className="flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5" />
                      <span className={secondsAgo > 10 ? 'text-status-queued font-semibold' : ''}>
                        Heartbeat: {secondsAgo === 0 ? 'just now' : `${secondsAgo}s ago`}
                      </span>
                    </div>
                    <span className="font-mono text-[11px]">
                      Started: {new Date(worker.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
