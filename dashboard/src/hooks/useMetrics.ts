import { useState, useEffect, useRef } from 'react';
import type { JobEvent, MetricsResponse } from '../lib/types';
import { fetchMetrics } from '../lib/api';

export interface MinuteMetric {
  time: string;
  processed: number;
  enqueued: number;
  failed: number;
}

export interface SystemMetrics {
  statusCounts: {
    queued: number;
    running: number;
    succeeded: number;
    failed: number;
    retrying: number;
    dead: number;
  };
  priorityBreakdown: {
    high: number;
    normal: number;
    low: number;
  };
  totalJobs: number;
  activeRunning: number;
  dlqCount: number;
  successRate: number;
  throughputHistory: MinuteMetric[];
}

const HISTORY_MINUTES = 10;

function formatMinuteLabel(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function generateInitialHistory(): MinuteMetric[] {
  const history: MinuteMetric[] = [];
  const now = new Date();
  for (let i = HISTORY_MINUTES - 1; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 60 * 1000);
    history.push({
      time: formatMinuteLabel(d),
      processed: 0,
      enqueued: 0,
      failed: 0,
    });
  }
  return history;
}

export function useMetrics(lastEvent: JobEvent | null) {
  const [metrics, setMetrics] = useState<SystemMetrics>({
    statusCounts: {
      queued: 0,
      running: 0,
      succeeded: 0,
      failed: 0,
      retrying: 0,
      dead: 0,
    },
    priorityBreakdown: {
      high: 0,
      normal: 0,
      low: 0,
    },
    totalJobs: 0,
    activeRunning: 0,
    dlqCount: 0,
    successRate: 100,
    throughputHistory: generateInitialHistory(),
  });

  const [isLoading, setIsLoading] = useState(true);
  const lastProcessedEventRef = useRef<JobEvent | null>(null);

  // Initial fetch from backend API
  useEffect(() => {
    fetchMetrics()
      .then((data: MetricsResponse) => {
        const succeeded = data.status_counts.succeeded || 0;
        const failed = data.status_counts.failed || 0;
        const dead = data.status_counts.dead || 0;
        const completed = succeeded + failed + dead;
        const successRate = completed > 0 ? (succeeded / completed) * 100 : 100;

        setMetrics((prev) => ({
          ...prev,
          statusCounts: {
            queued: data.status_counts.queued || 0,
            running: data.status_counts.running || 0,
            succeeded,
            failed,
            retrying: data.status_counts.retrying || 0,
            dead,
          },
          priorityBreakdown: data.priority_breakdown || { high: 0, normal: 0, low: 0 },
          totalJobs: data.total_jobs || 0,
          activeRunning: data.active_running || 0,
          dlqCount: data.dlq_count || 0,
          successRate: Number(successRate.toFixed(1)),
        }));
      })
      .catch((err) => console.error('Failed to load initial metrics:', err))
      .finally(() => setIsLoading(false));
  }, []);

  // Update minute label buckets every 60 seconds if idle
  useEffect(() => {
    const interval = setInterval(() => {
      const currentTimeLabel = formatMinuteLabel(new Date());
      setMetrics((prev) => {
        const history = [...prev.throughputHistory];
        if (history[history.length - 1]?.time !== currentTimeLabel) {
          const nextHistory = [
            ...history.slice(1),
            { time: currentTimeLabel, processed: 0, enqueued: 0, failed: 0 },
          ];
          return { ...prev, throughputHistory: nextHistory };
        }
        return prev;
      });
    }, 10_000);

    return () => clearInterval(interval);
  }, []);

  // Real-time WebSocket event handler (instantly reacts without polling)
  useEffect(() => {
    if (!lastEvent || lastEvent === lastProcessedEventRef.current) return;
    lastProcessedEventRef.current = lastEvent;

    const { old_status, new_status } = lastEvent;
    const nowLabel = formatMinuteLabel(new Date());

    setMetrics((prev) => {
      const counts = { ...prev.statusCounts };

      // Decrement old status count if existed
      if (old_status && counts[old_status] !== undefined && counts[old_status] > 0) {
        counts[old_status] -= 1;
      }

      // Increment new status count
      if (new_status && counts[new_status] !== undefined) {
        counts[new_status] += 1;
      }

      // Re-calculate derived metrics
      const totalJobs = old_status === null ? prev.totalJobs + 1 : prev.totalJobs;
      const succeeded = counts.succeeded;
      const failed = counts.failed;
      const dead = counts.dead;
      const completed = succeeded + failed + dead;
      const successRate = completed > 0 ? (succeeded / completed) * 100 : 100;

      // Priority estimate update for queued
      const priorityBreakdown = { ...prev.priorityBreakdown };
      if (new_status === 'queued' && old_status === null) {
        priorityBreakdown.normal += 1; // Default fallback for incoming live queue count
      } else if (old_status === 'queued' && counts.queued === 0) {
        priorityBreakdown.high = 0;
        priorityBreakdown.normal = 0;
        priorityBreakdown.low = 0;
      }

      // Throughput history update
      const history = [...prev.throughputHistory];
      const lastIndex = history.length - 1;
      let currentBucket = history[lastIndex];

      if (!currentBucket || currentBucket.time !== nowLabel) {
        currentBucket = { time: nowLabel, processed: 0, enqueued: 0, failed: 0 };
        history.shift();
        history.push(currentBucket);
      } else {
        currentBucket = { ...currentBucket };
        history[lastIndex] = currentBucket;
      }

      if (new_status === 'queued') {
        currentBucket.enqueued += 1;
      }
      if (new_status === 'succeeded' || new_status === 'failed' || new_status === 'dead') {
        currentBucket.processed += 1;
        if (new_status === 'failed' || new_status === 'dead') {
          currentBucket.failed += 1;
        }
      }

      return {
        ...prev,
        statusCounts: counts,
        priorityBreakdown,
        totalJobs,
        activeRunning: counts.running,
        dlqCount: counts.dead,
        successRate: Number(successRate.toFixed(1)),
        throughputHistory: history,
      };
    });
  }, [lastEvent]);

  return { metrics, isLoading };
}
