import { describe, it, expect } from "vitest";
import { safeUrl } from "./safeUrl";

describe("safeUrl", () => {
  it("accepts http and https", () => {
    expect(safeUrl("http://example.com/x")).toBe("http://example.com/x");
    expect(safeUrl("https://example.com/y?a=1")).toBe("https://example.com/y?a=1");
  });
  it("rejects dangerous and non-http schemes", () => {
    expect(safeUrl("javascript:alert(1)")).toBeNull();
    expect(safeUrl("data:text/html,<script>")).toBeNull();
    expect(safeUrl("vbscript:msgbox")).toBeNull();
    expect(safeUrl("ftp://example.com")).toBeNull();
  });
  it("rejects empty, null, and garbage", () => {
    expect(safeUrl("")).toBeNull();
    expect(safeUrl(null)).toBeNull();
    expect(safeUrl(undefined)).toBeNull();
    expect(safeUrl("not a url")).toBeNull();
    expect(safeUrl(42)).toBeNull();
  });
});
