import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// Mock EventSource for jsdom (not natively available)
class MockEventSource {
  url: string;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 0;

  constructor(url: string) {
    this.url = url;
    // Auto-close after a tick to prevent hanging
    setTimeout(() => {
      if (this.onmessage) {
        this.onmessage({ data: "[DONE]" });
      }
    }, 0);
  }

  close() {
    this.readyState = 2;
  }
}

// @ts-expect-error mock for test env
globalThis.EventSource = MockEventSource;

// Mock gsap to avoid browser API issues in jsdom
vi.mock("gsap", () => {
  const noop = () => {};
  const gsap = {
    to: noop,
    from: noop,
    fromTo: noop,
    set: noop,
    context: (fn: () => void) => {
      fn();
      return { revert: noop };
    },
    timeline: () => ({
      to: noop,
      from: noop,
      fromTo: noop,
      addLabel: noop,
      add: noop,
      play: noop,
      pause: noop,
    }),
    defaults: noop,
    matchMedia: () => ({ add: noop, revert: noop }),
  };
  return { default: gsap };
});
