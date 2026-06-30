import { describe, it, expect } from "vitest";
import { relativeTime } from "./formatters";

const iso = (msAgo) => new Date(Date.now() - msAgo).toISOString();

describe("relativeTime", () => {
  it("handles recent ranges", () => {
    expect(relativeTime(iso(5 * 1000))).toBe("just now");
    expect(relativeTime(iso(5 * 60 * 1000))).toBe("5m ago");
    expect(relativeTime(iso(3 * 3600 * 1000))).toBe("3h ago");
    expect(relativeTime(iso(2 * 86400 * 1000))).toBe("2d ago");
  });
  it("falls back to a date for old timestamps", () => {
    const out = relativeTime("2020-01-15T00:00:00Z");
    expect(out).toMatch(/2020/);
  });
  it("returns empty string for null/invalid", () => {
    expect(relativeTime(null)).toBe("");
    expect(relativeTime(undefined)).toBe("");
    expect(relativeTime("not a date")).toBe("");
  });
});
