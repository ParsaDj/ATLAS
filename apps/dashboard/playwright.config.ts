import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:8011",
    viewport: { width: 1440, height: 1000 },
    trace: "retain-on-failure",
  },
  webServer: {
    command: `${process.env.ATLAS_TEST_PYTHON || "python3"} ../../scripts/dashboard_test_server.py`,
    url: "http://127.0.0.1:8011/health",
    reuseExistingServer: false,
    timeout: 30000,
  },
});
