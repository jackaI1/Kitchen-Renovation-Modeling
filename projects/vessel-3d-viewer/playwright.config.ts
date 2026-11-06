import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests/browser",
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:5178",
    launchOptions: {
      args: [
        "--use-gl=angle",
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
      ],
    },
  },
  webServer: {
    command: "npm start",
    url: "http://127.0.0.1:5178",
    env: { PORT: "5178" },
    reuseExistingServer: false,
    stdout: "pipe",
    stderr: "pipe",
  },
  reporter: "list",
});
