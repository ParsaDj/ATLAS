import { test, expect } from "@playwright/test";

test.beforeAll(async ({ request }) => {
  for (let n = 1; n <= 5; n++) {
    const created = await request.post("/api/missions", {
      data: { robot_id: `robot-${n}`, waypoints: [{ x: 7, y: n }] },
    });
    expect(created.ok()).toBeTruthy();
    const mission = await created.json();
    expect(
      (await request.post(`/api/missions/${mission.id}/approve`)).ok(),
    ).toBeTruthy();
    expect(
      (
        await request.post("/api/telemetry", {
          data: {
            event_id: `browser-seed-${n}`,
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
  await page.getByRole("button", { name: /sensor failure robot-3/ }).click();
  const drawer = page.getByRole("dialog", { name: "Incident evidence" });
  await expect(
    drawer.getByText("browser-seed-3", { exact: true }).first(),
  ).toBeVisible();
  await expect(drawer.getByText(/Battery 85% · sensor failed/)).toBeVisible();
  await drawer.getByRole("button", { name: "Open linked mission" }).click();
  await expect(
    page
      .getByRole("dialog", { name: "Mission details" })
      .getByText("failed", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("browser-seed-3", { exact: true })).toBeVisible();
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
