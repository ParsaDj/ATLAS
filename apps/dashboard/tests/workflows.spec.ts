import { test, expect } from "@playwright/test";

const password = "atlas-browser-admin-password";
const bridgeHeaders = {
  "X-ATLAS-Bridge-Key": "atlas-browser-bridge-key-1234567890",
};
let csrf = "";

test.beforeAll(async ({ request }) => {
  const login = await request.post("/api/auth/login", {
    data: { username: "atlas-admin", password },
  });
  expect(login.ok()).toBeTruthy();
  csrf = (await login.json()).csrf_token;
  for (let n = 1; n <= 5; n++) {
    const created = await request.post("/api/missions", {
      data: { robot_id: `robot-${n}`, waypoints: [{ x: 7, y: n }] },
      headers: { "X-CSRF-Token": csrf },
    });
    expect(created.ok()).toBeTruthy();
    const mission = await created.json();
    expect(
      (
        await request.post(`/api/missions/${mission.id}/approve`, {
          headers: { "X-CSRF-Token": csrf },
        })
      ).ok(),
    ).toBeTruthy();
    expect(
      (
        await request.post("/api/telemetry", {
          headers: {
            "X-ATLAS-Bridge-Key": "atlas-browser-bridge-key-1234567890",
          },
          data: {
            event_id: `browser-seed-${n}-${mission.id}`,
            robot_id: `robot-${n}`,
            mission_id: mission.id,
            occurred_at: new Date().toISOString(),
            position: { x: 2 * n, y: n },
            battery: n === 2 ? 12 : 85,
            sensor_status: n === 3 ? "failed" : "ok",
            mission_status: "completed",
          },
        })
      ).ok(),
    ).toBeTruthy();
  }
});

test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Username").fill("atlas-admin");
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(
    page.getByRole("heading", { name: "Operations overview" }),
  ).toBeVisible();
});

test("operator follows failed mission and triggering telemetry", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Operations overview" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: /^Robot [1-5]$/ }),
  ).toHaveCount(5);
  await page.getByRole("button", { name: /sensor failure robot-3/ }).first().click();
  const drawer = page.getByRole("dialog", { name: "Incident evidence" });
  await expect(
    drawer.getByText(/^browser-seed-3-/).first(),
  ).toBeVisible();
  await expect(drawer.getByText(/Battery 85% · sensor failed/)).toBeVisible();
  await drawer.getByRole("button", { name: "Investigate incident" }).click();
  await expect(
    drawer.getByRole("region", { name: "Investigation result" }),
  ).toContainText("supports a sensor-path mission failure");
  await expect(drawer.getByText(/document:DOC-SENSOR-001/)).toBeVisible();
  await expect(drawer.getByText(/do not distinguish hardware/)).toBeVisible();
  await drawer.getByRole("button", { name: "Open linked mission" }).click();
  await expect(
    page
      .getByRole("dialog", { name: "Mission details" })
      .getByText("failed", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/^browser-seed-3-/)).toBeVisible();
});

test("operator creates, approves and cancels a mission", async ({
  page,
  request,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Robot 5", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Create mission", exact: false })
    .click();
  await page.getByLabel("Assigned robot").selectOption("robot-5");
  await page.getByLabel("X coordinate 1", { exact: true }).fill("5");
  await page.getByRole("button", { name: "Save mission proposal" }).click();
  const drawer = page.getByRole("dialog", { name: "Mission details" });
  await expect(drawer.getByText("pending", { exact: true })).toBeVisible();
  await drawer.getByRole("button", { name: "Approve mission" }).click();
  await expect(drawer.getByText("running", { exact: true })).toBeVisible();
  await drawer.getByLabel("Cancellation reason").fill("Operator browser test");
  await drawer
    .getByRole("button", { name: "Cancel mission", exact: true })
    .click();
  await expect(drawer.getByText("cancelled", { exact: true })).toBeVisible();
  const response = await request.get(
    "/api/missions?robot_id=robot-5&status=cancelled",
    { headers: bridgeHeaders },
  );
  const records = await response.json();
  expect(records).toHaveLength(1);
  expect(records[0].waypoints[0]).toEqual({ x: 5, y: 2 });
  expect(records[0].cancellation_reason).toBe("Operator browser test");
});

test("API outage flags stale data while preserving the last fleet snapshot", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Robot 1", exact: true }),
  ).toBeVisible();
  await page.route("**/api/robots", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Test service unavailable" }),
    }),
  );
  await expect(page.getByText(/Connection interrupted/)).toBeVisible({
    timeout: 10000,
  });
  await expect(page.getByRole("alert")).toContainText(
    "Test service unavailable",
  );
  await expect(
    page.getByRole("heading", { name: "Robot 1", exact: true }),
  ).toBeVisible();
  await page.unroute("**/api/robots");
  await page.getByRole("button", { name: "Retry connection" }).click();
  await expect(page.getByText(/API connected/)).toBeVisible();
});

test("mobile navigation keeps incident and mission workflows accessible", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Incidents" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Incident center" }),
  ).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Missions" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Inspection missions" }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
});

test("administrator creates a user and reviews the audit trail", async ({
  page,
}) => {
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Administration" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Security & audit" }),
  ).toBeVisible();
  await page.getByLabel("Username").fill("browser-operator");
  await page.getByLabel("Temporary password").fill("browser-operator-password");
  await page.getByLabel("Role").selectOption("operator");
  await page.getByRole("button", { name: "Create user" }).click();
  await expect(
    page.getByText("browser-operator", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("user create", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("heading", { name: "Operations sign in" }),
  ).toBeVisible();
});

test("administrator drafts and approves technical guidance", async ({ page }) => {
  await page
    .getByRole("navigation")
    .getByRole("button", { name: "Knowledge" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Technical knowledge" }),
  ).toBeVisible();
  await expect(page.getByText("DOC-SENSOR-001@1.0")).toBeVisible();

  await page.getByLabel("Document ID").fill("DOC-SENSOR-UI-001");
  await page.getByLabel("Version").fill("1.0");
  await page.getByLabel("Fault classification").selectOption("sensor_failure");
  await page.getByLabel("Title").fill("Browser-tested sensor response");
  await page
    .getByLabel("Technical content")
    .fill("Inspect the synthetic sensor connector and verify calibration records before retrying.");
  await page
    .getByLabel("Recommended next step")
    .fill("Run the documented calibration check and review its output.");
  await page.getByRole("button", { name: "Create draft revision" }).click();
  await expect(
    page.getByText("Draft revision created. Review it before approval."),
  ).toBeVisible();

  const revision = page.locator("article").filter({ hasText: "DOC-SENSOR-UI-001@1.0" });
  await expect(revision.getByText("draft", { exact: true })).toBeVisible();
  await revision.getByRole("button", { name: "Approve revision" }).click();
  await expect(
    page.getByText("DOC-SENSOR-UI-001 version 1.0 approved."),
  ).toBeVisible();
  await expect(revision.getByText("approved", { exact: true })).toBeVisible();
});

test("approved maintenance ticket is completed by its assigned technician", async ({
  page,
  request,
}) => {
  const adminLogin = await request.post("/api/auth/login", {
    data: { username: "atlas-admin", password },
  });
  expect(adminLogin.ok()).toBeTruthy();
  const adminCsrf = (await adminLogin.json()).csrf_token;
  const created = await request.post("/api/users", {
    headers: { "X-CSRF-Token": adminCsrf },
    data: {
      username: "ticket-tech",
      password: "ticket-technician-password",
      role: "technician",
    },
  });
  expect(created.ok()).toBeTruthy();

  await page.goto("/");
  await page.getByRole("button", { name: /sensor failure robot-3/ }).first().click();
  const drawer = page.getByRole("dialog", { name: "Incident evidence" });
  await drawer
    .getByLabel("Work summary")
    .fill("Inspect and calibrate the failed inspection sensor");
  await drawer.getByLabel("Assigned technician username").fill("ticket-tech");
  await drawer.getByRole("button", { name: "Draft maintenance ticket" }).click();
  await expect(drawer.getByText("draft", { exact: true })).toBeVisible();
  await drawer
    .getByRole("button", { name: "Approve maintenance work" })
    .click();
  await expect(drawer.getByText("approved", { exact: true })).toBeVisible();
  await drawer.getByRole("button", { name: "Close" }).click();
  await page.getByRole("button", { name: "Sign out" }).click();

  await page.getByLabel("Username").fill("ticket-tech");
  await page.getByLabel("Password").fill("ticket-technician-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: /Incidents/ }).click();
  await page
    .getByRole("row")
    .filter({ hasText: "sensor failure" })
    .first()
    .getByRole("button", { name: /Investigate/ })
    .click();
  const technicianDrawer = page.getByRole("dialog", {
    name: "Incident evidence",
  });
  await technicianDrawer
    .getByRole("button", { name: "Start maintenance work" })
    .click();
  await technicianDrawer
    .getByLabel("Resolution")
    .fill("Recalibrated the sensor and verified healthy observations.");
  await technicianDrawer
    .getByRole("button", { name: "Resolve ticket and incident" })
    .click();
  await expect(technicianDrawer.getByText("resolved", { exact: true })).toHaveCount(2);
});

test("operator downloads incident and inspection reports", async ({ page }) => {
  const { readFile } = await import("node:fs/promises");
  await page.goto("/");
  await page.getByRole("button", { name: /Incidents/ }).click();
  await page
    .getByRole("row")
    .filter({ hasText: "sensor failure" })
    .first()
    .getByRole("button", { name: /Investigate/ })
    .click();
  const incidentDrawer = page.getByRole("dialog", { name: "Incident evidence" });
  const [incidentDownload] = await Promise.all([
    page.waitForEvent("download"),
    incidentDrawer.getByRole("button", { name: "Download incident report" }).click(),
  ]);
  expect(incidentDownload.suggestedFilename()).toMatch(/^atlas-incident-.+\.html$/);
  const incidentPath = await incidentDownload.path();
  expect(await readFile(incidentPath!, "utf8")).toContain(
    "Evidence-based investigation",
  );

  await incidentDrawer.getByRole("button", { name: "Open linked mission" }).click();
  const missionDrawer = page.getByRole("dialog", { name: "Mission details" });
  const [missionDownload] = await Promise.all([
    page.waitForEvent("download"),
    missionDrawer
      .getByRole("button", { name: "Download inspection report" })
      .click(),
  ]);
  expect(missionDownload.suggestedFilename()).toMatch(/^atlas-mission-.+\.html$/);
  const missionPath = await missionDownload.path();
  expect(await readFile(missionPath!, "utf8")).toContain("Telemetry summary");
});

test("operator edits, proposes and approves a replacement mission", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Incidents/ }).click();
  await page
    .getByRole("row")
    .filter({ hasText: "sensor failure" })
    .first()
    .getByRole("button", { name: /Investigate/ })
    .click();
  const drawer = page.getByRole("dialog", { name: "Incident evidence" });
  await drawer.getByLabel("Replacement waypoint 1 X").fill("9");
  await drawer.getByRole("button", { name: "Propose replacement mission" }).click();
  await expect(drawer.getByText("pending", { exact: true })).toBeVisible();
  await drawer.getByRole("button", { name: "Approve replacement mission" }).click();
  await expect(drawer.getByText("running", { exact: true })).toBeVisible();
  await drawer.getByRole("button", { name: "Open replacement mission" }).click();
  const missionDrawer = page.getByRole("dialog", { name: "Mission details" });
  await expect(missionDrawer.getByText("1 · (9, 3)")).toBeVisible();
});

test("approved dashboard mission executes in a real worker process", async ({
  page,
  request,
}) => {
  const { spawn } = await import("node:child_process");
  const { resolve } = await import("node:path");
  const python = process.env.ATLAS_TEST_PYTHON || "python3";
  const executable = python.includes("/") ? resolve(python) : python;
  const worker = spawn(
    executable,
    [
      "-m",
      "simulator.worker",
      "--url",
      "http://127.0.0.1:8011",
      "--interval",
      "0.1",
    ],
    {
      cwd: resolve("../.."),
      stdio: "ignore",
      env: {
        ...process.env,
        ATLAS_TELEMETRY_API_KEY: "atlas-browser-bridge-key-1234567890",
      },
    },
  );
  let workerError: Error | undefined;
  worker.on("error", (error) => {
    workerError = error;
  });
  try {
    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Robot 1", exact: true }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Create mission", exact: false })
      .click();
    await page.getByLabel("Assigned robot").selectOption("robot-1");
    await page.getByRole("button", { name: "Save mission proposal" }).click();
    const drawer = page.getByRole("dialog", { name: "Mission details" });
    await drawer.getByRole("button", { name: "Approve mission" }).click();
    await expect(drawer.getByText("completed", { exact: true })).toBeVisible({
      timeout: 30000,
    });
    await expect(drawer.getByText("2 of 2 waypoints reached")).toBeVisible();
    expect(workerError).toBeUndefined();
    const missions = await (
      await request.get("/api/missions?robot_id=robot-1&status=completed", {
        headers: bridgeHeaders,
      })
    ).json();
    expect(
      missions.some(
        (mission: { completed_waypoints: number }) =>
          mission.completed_waypoints === 2,
      ),
    ).toBeTruthy();
  } finally {
    if (worker.exitCode === null) {
      const exited = new Promise<void>((resolveExit) =>
        worker.once("exit", () => resolveExit()),
      );
      worker.kill("SIGTERM");
      await exited;
    }
  }
});
