import { useState } from "react";
import { ChevronRight, Terminal } from "lucide-react";
import type { RunEvent } from "../api/client";

interface DebugPanelProps {
  events: RunEvent[];
}

/**
 * Collapsible debug log panel — shows raw SSE event stream
 * for troubleshooting when the workflow hangs or errors.
 */
export function DebugPanel({ events }: DebugPanelProps) {
  const [isOpen, setIsOpen] = useState(false);

  const errorCount = events.filter((e) => e.event_type === "error").length;

  function formatTime(ts: number): string {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString("zh-CN", { hour12: false });
  }

  return (
    <div className="debug-panel">
      <button
        className={`debug-toggle ${isOpen ? "debug-toggle--open" : ""}`}
        onClick={() => setIsOpen(!isOpen)}
        type="button"
      >
        <Terminal size={14} />
        <ChevronRight size={14} />
        <span>调试日志</span>
        <span className="debug-toggle-count">{events.length}</span>
        {errorCount > 0 && (
          <span className="debug-toggle-count debug-toggle-count--error">
            {errorCount} 错误
          </span>
        )}
      </button>

      {isOpen && (
        <div className="debug-content">
          {events.length === 0 ? (
            <p className="debug-empty">等待事件…</p>
          ) : (
            events.map((event, idx) => (
              <div
                key={idx}
                className={`debug-entry ${event.event_type === "error" ? "debug-entry--error" : ""}`}
              >
                <span className="debug-time">{formatTime(event.timestamp)}</span>
                <span className="debug-type">{event.event_type}</span>
                <span className="debug-gate">{event.gate}</span>
                <span className="debug-msg">
                  {event.agent ? `[${event.agent}] ` : ""}
                  {event.message}
                </span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
