import { defineConfig } from "vite";
export default defineConfig({
  base: "./",
  build: { chunkSizeWarningLimit: 650 },
  test: { include: ["tests/**/*.test.ts"], maxWorkers: 1 },
} as Parameters<typeof defineConfig>[0]);
