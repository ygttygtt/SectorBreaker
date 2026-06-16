import { useEffect, useRef, useState, useCallback } from "react";
import type { RunEvent } from "../api/client";

export interface UseRunEventsOptions {
  runId: string | null;
  onEvent?: (event: RunEvent) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

/**
 * SSE hook — connects to /api/runs/{runId}/events.
 *
 * Uses refs for callbacks so the EventSource connection is stable
 * across re-renders. Only reconnects when runId changes.
 */
export function useRunEvents({ runId, onEvent, onComplete, onError }: UseRunEventsOptions) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Store latest callbacks in refs to avoid reconnecting on callback change
  const onEventRef = useRef(onEvent);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  onEventRef.current = onEvent;
  onCompleteRef.current = onComplete;
  onErrorRef.current = onError;

  const reset = useCallback(() => {
    setEvents([]);
    setIsConnected(false);
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!runId) {
      reset();
      return;
    }

    const es = new EventSource(`/api/runs/${runId}/events`);
    eventSourceRef.current = es;
    setIsConnected(true);

    // Track seen events to deduplicate on reconnect replay
    const seen = new Set<string>();

    es.onmessage = (msg) => {
      if (msg.data === "[DONE]") {
        es.close();
        setIsConnected(false);
        onCompleteRef.current?.();
        return;
      }
      try {
        const event: RunEvent = JSON.parse(msg.data);
        // Dedup key: timestamp + gate + event_type + message prefix
        const key = `${event.timestamp}-${event.gate}-${event.event_type}-${event.message?.slice(0, 30)}`;
        if (seen.has(key)) return;
        seen.add(key);
        setEvents((prev) => [...prev, event]);
        onEventRef.current?.(event);
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setIsConnected(false);
      onErrorRef.current?.("SSE 连接断开");
      es.close();
    };

    return () => {
      es.close();
      setIsConnected(false);
    };
    // Only reconnect when runId changes — callbacks are via refs
  }, [runId, reset]);

  return { events, isConnected, reset };
}
