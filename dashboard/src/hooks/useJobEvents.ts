import { useState, useEffect, useRef, useCallback } from 'react';
import type { JobEvent } from '../lib/types';

/**
 * useJobEvents — Custom React hook for live WebSocket job event streaming.
 *
 * Connects to the native WebSocket endpoint at /ws/jobs.
 * Auto-reconnects with exponential backoff (1s → 2s → 4s → ... → 30s cap).
 *
 * Returns:
 *   - lastEvent: The most recent JobEvent received, or null.
 *   - isConnected: Whether the WebSocket connection is currently open.
 *   - events: Rolling buffer of recent events (last 100).
 */

const WS_URL = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/jobs`;
const MAX_RECONNECT_DELAY = 30_000;
const INITIAL_RECONNECT_DELAY = 1_000;
const EVENT_BUFFER_SIZE = 100;

export function useJobEvents() {
  const [lastEvent, setLastEvent] = useState<JobEvent | null>(null);
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        setIsConnected(true);
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY;
        console.log('[Forge WS] Connected to', WS_URL);
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const data: JobEvent = JSON.parse(event.data);
          setLastEvent(data);
          setEvents((prev) => {
            const next = [data, ...prev];
            return next.length > EVENT_BUFFER_SIZE
              ? next.slice(0, EVENT_BUFFER_SIZE)
              : next;
          });
        } catch (err) {
          console.warn('[Forge WS] Failed to parse message:', err);
        }
      };

      ws.onclose = (event) => {
        if (!mountedRef.current) return;
        setIsConnected(false);
        console.log(`[Forge WS] Disconnected (code=${event.code}). Reconnecting in ${reconnectDelayRef.current}ms...`);
        scheduleReconnect();
      };

      ws.onerror = (err) => {
        console.warn('[Forge WS] Error:', err);
        ws.close();
      };
    } catch (err) {
      console.error('[Forge WS] Connection failed:', err);
      scheduleReconnect();
    }
  }, []);

  const scheduleReconnect = useCallback(() => {
    if (!mountedRef.current) return;
    const delay = reconnectDelayRef.current;
    reconnectTimerRef.current = setTimeout(() => {
      reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY);
      connect();
    }, delay);
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  return { lastEvent, events, isConnected };
}
