import React, { useEffect, useState } from 'react';
import {
  Activity,
  CheckCircle2,
  Cpu,
  Database,
  Layers,
  Server,
  Skull,
  TrendingUp,
  Zap,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { fetchHealth } from '../lib/api';
import type { HealthResponse } from '../lib/types';
import { useJobEvents } from '../hooks/useJobEvents';
import { useMetrics } from '../hooks/useMetrics';

export const OverviewPage: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const { isConnected, events, lastEvent } = useJobEvents();
  const { metrics } = useMetrics(lastEvent);

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch((err) => console.error('Failed to fetch health:', err));
  }, []);

  const totalProcessed =
    metrics.statusCounts.succeeded +
    metrics.statusCounts.failed +
    metrics.statusCounts.dead;

  const totalQueued = metrics.statusCounts.queued;

  return (
    <div className="space-y-8">
      {/* ── Top Header ────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">System Overview</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Real-time metrics, throughput, and queue monitor
          </p>
        </div>
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-bg-secondary border border-border text-xs">
          <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-status-succeeded animate-pulse' : 'bg-status-failed'}`} />
          <span className="text-text-secondary">
            {isConnected ? 'Real-time WebSocket active' : 'Connecting to WebSocket…'}
          </span>
        </div>
      </div>

      {/* ── Summary Stat Cards ────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Processed */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              Total Processed
            </span>
            <div className="p-2 rounded-lg bg-accent/10 text-accent">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-text-primary font-mono">
              {totalProcessed}
            </span>
            <span className="text-xs text-text-muted">jobs</span>
          </div>
          <p className="mt-2 text-xs text-text-muted">
            {metrics.totalJobs} total jobs submitted
          </p>
        </div>

        {/* Success Rate */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              Success Rate
            </span>
            <div className="p-2 rounded-lg bg-status-succeeded/10 text-status-succeeded">
              <TrendingUp className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-text-primary font-mono">
              {metrics.successRate}%
            </span>
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-xs text-status-succeeded">{metrics.statusCounts.succeeded} ok</span>
            <span className="text-xs text-text-muted">•</span>
            <span className="text-xs text-status-failed">{metrics.statusCounts.failed} failed</span>
          </div>
        </div>

        {/* Active Jobs / Workers */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              Active Running
            </span>
            <div className="p-2 rounded-lg bg-status-running/10 text-status-running">
              <Cpu className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className="text-3xl font-bold text-text-primary font-mono">
              {metrics.activeRunning}
            </span>
            <span className="text-xs text-status-running font-medium">in-flight</span>
          </div>
          <p className="mt-2 text-xs text-text-muted">
            Workers executing jobs
          </p>
        </div>

        {/* DLQ Count */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-text-muted">
              Dead Letter Queue
            </span>
            <div className={`p-2 rounded-lg ${metrics.dlqCount > 0 ? 'bg-status-failed/20 text-status-failed' : 'bg-bg-tertiary text-text-muted'}`}>
              <Skull className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-4 flex items-baseline gap-2">
            <span className={`text-3xl font-bold font-mono ${metrics.dlqCount > 0 ? 'text-status-failed' : 'text-text-primary'}`}>
              {metrics.dlqCount}
            </span>
            <span className="text-xs text-text-muted">dead jobs</span>
          </div>
          <p className="mt-2 text-xs text-text-muted">
            Max retries exhausted
          </p>
        </div>
      </div>

      {/* ── Main Charts Grid ──────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Live Throughput Chart (2 cols) */}
        <div className="lg:col-span-2 rounded-xl border border-border bg-bg-secondary p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-base font-semibold text-text-primary flex items-center gap-2">
                <Zap className="w-4 h-4 text-accent" />
                Live Job Throughput
              </h2>
              <p className="text-xs text-text-secondary mt-0.5">
                Jobs processed and enqueued per minute (rolling window)
              </p>
            </div>
            <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-bg-tertiary text-text-secondary border border-border">
              Live Stream
            </span>
          </div>

          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={metrics.throughputHistory} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="colorProcessed" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="colorEnqueued" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="time" stroke="#64748b" fontSize={11} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={11} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#111827',
                    borderColor: '#1e293b',
                    borderRadius: '8px',
                    color: '#f1f5f9',
                    fontSize: '12px',
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="processed"
                  name="Processed"
                  stroke="#6366f1"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorProcessed)"
                />
                <Area
                  type="monotone"
                  dataKey="enqueued"
                  name="Enqueued"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  fillOpacity={1}
                  fill="url(#colorEnqueued)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Queue Depth Gauge & Priority Distribution (1 col) */}
        <div className="rounded-xl border border-border bg-bg-secondary p-6 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-base font-semibold text-text-primary flex items-center gap-2">
                <Layers className="w-4 h-4 text-status-queued" />
                Queue Depth Gauge
              </h2>
              <span className="text-xs font-mono font-semibold text-status-queued bg-status-queued/10 px-2 py-0.5 rounded">
                {totalQueued} Queued
              </span>
            </div>
            <p className="text-xs text-text-secondary mb-6">
              Current queue allocation by priority level
            </p>

            {/* Priority Bars */}
            <div className="space-y-4">
              {/* High Priority */}
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-medium text-text-primary">High Priority (≥ 7)</span>
                  <span className="font-mono text-status-failed">{metrics.priorityBreakdown.high}</span>
                </div>
                <div className="w-full h-2 rounded-full bg-bg-primary overflow-hidden">
                  <div
                    className="h-full bg-status-failed transition-all duration-300"
                    style={{ width: `${totalQueued > 0 ? (metrics.priorityBreakdown.high / totalQueued) * 100 : 0}%` }}
                  />
                </div>
              </div>

              {/* Normal Priority */}
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-medium text-text-primary">Normal Priority (4–6)</span>
                  <span className="font-mono text-status-queued">{metrics.priorityBreakdown.normal}</span>
                </div>
                <div className="w-full h-2 rounded-full bg-bg-primary overflow-hidden">
                  <div
                    className="h-full bg-status-queued transition-all duration-300"
                    style={{ width: `${totalQueued > 0 ? (metrics.priorityBreakdown.normal / totalQueued) * 100 : 0}%` }}
                  />
                </div>
              </div>

              {/* Low Priority */}
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="font-medium text-text-primary">Low Priority (0–3)</span>
                  <span className="font-mono text-text-secondary">{metrics.priorityBreakdown.low}</span>
                </div>
                <div className="w-full h-2 rounded-full bg-bg-primary overflow-hidden">
                  <div
                    className="h-full bg-text-muted transition-all duration-300"
                    style={{ width: `${totalQueued > 0 ? (metrics.priorityBreakdown.low / totalQueued) * 100 : 0}%` }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Infrastructure Health Badges */}
          <div className="mt-6 pt-4 border-t border-border space-y-2">
            <span className="text-xs font-semibold text-text-muted uppercase tracking-wider block mb-2">
              Infrastructure
            </span>
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2 text-text-secondary">
                <Database className="w-3.5 h-3.5" /> PostgreSQL
              </span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${health?.database === 'connected' ? 'bg-status-succeeded/10 text-status-succeeded' : 'bg-status-failed/10 text-status-failed'}`}>
                {health?.database ?? '…'}
              </span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="flex items-center gap-2 text-text-secondary">
                <Server className="w-3.5 h-3.5" /> Redis
              </span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${health?.redis === 'connected' ? 'bg-status-succeeded/10 text-status-succeeded' : 'bg-status-failed/10 text-status-failed'}`}>
                {health?.redis ?? '…'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Live Event Feed ──────────────────────────────────── */}
      <div className="rounded-xl border border-border bg-bg-secondary overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-accent" />
            <h2 className="text-sm font-semibold text-text-primary">Live Event Log</h2>
          </div>
          <span className="text-xs text-text-muted">{events.length} events buffered</span>
        </div>
        <div className="max-h-64 overflow-y-auto">
          {events.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-text-muted">
              No events received yet. Submit a job in the Jobs tab to see live WebSocket events here.
            </div>
          ) : (
            <div className="divide-y divide-border">
              {events.map((event, i) => (
                <div key={`${event.job_id}-${event.timestamp}-${i}`} className="px-5 py-3 flex items-center gap-4 hover:bg-bg-tertiary/40 transition-colors">
                  <code className="text-xs text-text-muted font-mono w-24 shrink-0 truncate">
                    {event.job_id.slice(0, 8)}…
                  </code>
                  <div className="flex items-center gap-2 text-xs">
                    {event.old_status && (
                      <span className={`status-badge status-${event.old_status}`}>
                        {event.old_status}
                      </span>
                    )}
                    <span className="text-text-muted">→</span>
                    <span className={`status-badge status-${event.new_status}`}>
                      {event.new_status}
                    </span>
                  </div>
                  <span className="ml-auto text-xs text-text-muted font-mono">
                    {new Date(event.timestamp).toLocaleTimeString()}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
