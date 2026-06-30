import { defineConfig } from "vitest/config";

// SP2 tests are pure-logic unit tests (no DOM), so the default node environment
// is sufficient — no jsdom / React Testing Library harness.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.{js,jsx}"],
  },
});
