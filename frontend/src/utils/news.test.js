import { describe, it, expect } from "vitest";
import { buildNewsParams, computeHasMore, mergeNewsItems } from "./news";

describe("buildNewsParams", () => {
  it("drops empty event_type/search", () => {
    expect(buildNewsParams({ eventType: "", search: "" }, 1, 20)).toEqual({ page: 1, per_page: 20 });
  });
  it("includes non-empty filters", () => {
    expect(buildNewsParams({ eventType: "sighting", search: "bondi" }, 2, 20)).toEqual({
      page: 2, per_page: 20, event_type: "sighting", search: "bondi",
    });
  });
});

describe("computeHasMore", () => {
  it("is false when meta is null", () => {
    expect(computeHasMore(null)).toBe(false);
  });
  it("is true when more pages remain", () => {
    expect(computeHasMore({ page: 1, per_page: 20, total: 50 })).toBe(true);
  });
  it("is false on the last page", () => {
    expect(computeHasMore({ page: 3, per_page: 20, total: 60 })).toBe(false);
  });
});

describe("mergeNewsItems", () => {
  it("appends and de-dupes by id", () => {
    const prev = [{ id: "a" }, { id: "b" }];
    const next = [{ id: "b" }, { id: "c" }];
    expect(mergeNewsItems(prev, next).map((i) => i.id)).toEqual(["a", "b", "c"]);
  });
});
