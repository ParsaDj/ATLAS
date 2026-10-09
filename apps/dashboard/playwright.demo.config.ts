import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./demo",
  timeout: 60000,
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8011",
    viewport: { width: 1440, height: 1500 },
  },
  webServer: {
    command: `${process.env.ATLAS_TEST_PYTHON || "python3"} ../../scripts/dashboard_test_server.py`,
    url: "http://127.0.0.1:8011/health",
    reuseExistingServer: false,
    timeout: 120000,
  },
});
