import React, { useEffect, useState } from 'react';
import { Activity, Database, Server, Wifi, WifiOff } from 'lucide-react';
import { fetchHealth } from '../lib/api';
import type { HealthResponse } from '../lib/types';
import { useJobEvents } from '../hooks/useJobEvents';

export const OverviewPage: React.FC = () => {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const { isConnected, events } = useJobEvents();

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch((err) => console.error('Failed to fetch health:', err));
  }, []);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Overview</h1>
        <p className="mt-1 text-sm text-text-secondary">
          System health and live event feed
        </p>
      </div>

      {/* Health Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Database */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-text-secondary">PostgreSQL</span>
            <Database className="w-4 h-4 text-text-muted" />
          </div>
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                health?.database === 'connected' ? 'bg-status-succeeded' : 'bg-status-failed'
              }`}
            />
            <span className="text-lg font-semibold text-text-primary">
              {health?.database ?? '—'}
            </span>
          </div>
        </div>

        {/* Redis */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-text-secondary">Redis</span>
            <Server className="w-4 h-4 text-text-muted" />
          </div>
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                health?.redis === 'connected' ? 'bg-status-succeeded' : 'bg-status-failed'
              }`}
            />
            <span className="text-lg font-semibold text-text-primary">
              {health?.redis ?? '—'}
            </span>
          </div>
        </div>

        {/* WebSocket */}
        <div className="rounded-xl border border-border bg-bg-secondary p-5">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-medium text-text-secondary">WebSocket</span>
            {isConnected ? (
              <Wifi className="w-4 h-4 text-status-succeeded" />
            ) : (
              <WifiOff className="w-4 h-4 text-status-failed" />
            )}
          </div>
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                isConnected ? 'bg-status-succeeded' : 'bg-status-failed'
              }`}
            />
            <span className="text-lg font-semibold text-text-primary">
              {isConnected ? 'connected' : 'disconnected'}
            </span>
          </div>
        </div>
      </div>

      {/* Live Event Feed */}
      <div className="rounded-xl border border-border bg-bg-secondary">
        <div className="flex items-center gap-2 px-5 py-4 border-b border-border">
          <Activity className="w-4 h-4 text-accent" />
          <h2 className="text-sm font-semibold text-text-primary">Live Event Feed</h2>
          <span className="ml-auto text-xs text-text-muted">{events.length} events</span>
        </div>
        <div className="max-h-80 overflow-y-auto">
          {events.length === 0 ? (
            <div className="px-5 py-10 text-center text-sm text-text-muted">
              No events received yet. Create a job to see live updates.
            </div>
          ) : (
            <div className="divide-y divide-border">
              {events.map((event, i) => (
                <div key={`${event.job_id}-${event.timestamp}-${i}`} className="px-5 py-3 flex items-center gap-4">
                  <code className="text-xs text-text-muted font-mono w-20 shrink-0 truncate">
                    {event.job_id.slice(0, 8)}
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
                  <span className="ml-auto text-xs text-text-muted">
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
