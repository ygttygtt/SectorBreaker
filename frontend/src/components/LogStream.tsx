import { useEffect, useRef } from "react";
import gsap from "gsap";
import type { RunEvent } from "../api/client";

interface LogStreamProps {
  events: RunEvent[];
}

function formatTime(timestamp: number): string {
  const d = new Date(timestamp * 1000);
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function eventColor(eventType: string): string {
  switch (eventType) {
    case "gate_start":
    case "step_start":
      return "#d4a017";
    case "gate_complete":
    case "step_complete":
      return "#106b5d";
    case "artifact_created":
      return "#2d5d9f";
    case "evidence_collected":
      return "#6d5d9f";
    case "error":
      return "#dc3545";
    default:
      return "#6d716f";
  }
}

export function LogStream({ events }: LogStreamProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const prevCountRef = useRef(0);

  // Animate new entries
  useEffect(() => {
    if (!containerRef.current) return;
    const entries = containerRef.current.querySelectorAll(".log-entry");
    const newEntries = Array.from(entries).slice(prevCountRef.current);

    if (newEntries.length > 0) {
      gsap.from(newEntries, {
        x: 20,
        opacity: 0,
        duration: 0.3,
        stagger: 0.05,
        ease: "power2.out",
      });
    }

    prevCountRef.current = entries.length;

    // Auto-scroll to bottom
    containerRef.current.scrollTop = containerRef.current.scrollHeight;
  }, [events]);

  return (
    <div ref={containerRef} className="log-stream">
      {events.length === 0 ? (
        <div className="log-empty">等待事件...</div>
      ) : (
        events.map((event, idx) => (
          <div key={idx} className="log-entry">
            <span className="log-time">{formatTime(event.timestamp)}</span>
            {event.agent && <span className="log-agent">{event.agent}</span>}
            <span className="log-msg" style={{ color: eventColor(event.event_type) }}>
              {event.message}
            </span>
          </div>
        ))
      )}
    </div>
  );
}
