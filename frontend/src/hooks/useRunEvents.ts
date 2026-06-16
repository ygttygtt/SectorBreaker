import { useEffect, useRef, useState, useCallback } from "react";
import type { RunEvent } from "../api/client";

export interface UseRunEventsOptions {
  runId: string | null;
  onEvent?: (event: RunEvent) => void;
  onComplete?: () => void;
  onError?: (error: string) => void;
}

export function useRunEvents({ runId, onEvent, onComplete, onError }: UseRunEventsOptions) {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

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

    es.onmessage = (msg) => {
      if (msg.data === "[DONE]") {
        es.close();
        setIsConnected(false);
        onComplete?.();
        return;
      }
      try {
        const event: RunEvent = JSON.parse(msg.data);
        setEvents((prev) => [...prev, event]);
        onEvent?.(event);
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setIsConnected(false);
      onError?.("SSE 连接断开");
      es.close();
    };

    return () => {
      es.close();
      setIsConnected(false);
    };
  }, [runId, onEvent, onComplete, onError, reset]);

  return { events, isConnected, reset };
}
