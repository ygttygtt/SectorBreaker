import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";

// Mock ResizeObserver for React Flow
class ResizeObserverMock {
  callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;

// Mock getBoundingClientRect for React Flow nodes
Element.prototype.getBoundingClientRect = () => ({
  x: 0, y: 0, width: 200, height: 100,
  top: 0, right: 200, bottom: 100, left: 0,
  toJSON: () => {},
});

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
  const noop = (..._args: unknown[]) => {};
  const gsap = {
    to: noop,
    from: noop,
    fromTo: noop,
    set: noop,
    context: (fn: () => void, _scope?: unknown) => {
      // Don't call fn immediately - let React handle the effect timing
      return { revert: noop, add: noop };
    },
    timeline: (_opts?: unknown) => ({
      to: noop,
      from: noop,
      fromTo: noop,
      addLabel: noop,
      add: noop,
      play: noop,
      pause: noop,
      kill: noop,
    }),
    defaults: noop,
    matchMedia: () => ({ add: noop, revert: noop }),
    quickTo: () => noop,
  };
  return { __esModule: true, default: gsap };
});
