// Tests der Karte ohne Browser: happy-dom stellt ein nachgebautes DOM bereit (E67).
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "happy-dom",
    include: ["test/**/*.test.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**"],
      reporter: ["text"],
      thresholds: { lines: 90, functions: 90, branches: 90, statements: 90 },
    },
  },
});
