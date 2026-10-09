import { test, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";

const password = "atlas-browser-admin-password";
const bridgeKey = "atlas-browser-bridge-key-1234567890";
const artifacts = resolve("demo-artifacts");

test("capture the Robot 3 evidence-grounded failure story", async ({
  browser,
  request,
}, testInfo) => {
  await mkdir(artifacts, { recursive: true });
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:8011",
    viewport: { width: 1920, height: 1080 },
    recordVideo: {
      dir: testInfo.outputPath("video"),
      size: { width: 1920, height: 1080 },
    },
  });
  const page = await context.newPage();
  const login = await request.post("/api/auth/login", {
    data: { username: "atlas-admin", password },
  });
  expect(login.ok()).toBeTruthy();
  const csrf = (await login.json()).csrf_token;
  const missionResponse = await request.post("/api/missions", {
    headers: { "X-CSRF-Token": csrf },
    data: { robot_id: "robot-3", waypoints: [{ x: 4, y: 2 }] },
  });
  const mission = await missionResponse.json();
  expect(
    (
      await request.post(`/api/missions/${mission.id}/approve`, {
        headers: { "X-CSRF-Token": csrf },
      })
    ).ok(),
  ).toBeTruthy();

  const eventId = `portfolio-demo:${mission.id}:sensor-failed`;
  const telemetry = await request.post("/api/telemetry", {
    headers: { "X-ATLAS-Bridge-Key": bridgeKey },
    data: {
      event_id: eventId,
      robot_id: "robot-3",
      mission_id: mission.id,
      occurred_at: new Date().toISOString(),
      position: { x: 2, y: 1.5 },
      battery: 87,
      sensor_status: "failed",
      mission_status: "running",
    },
  });
  expect(telemetry.ok()).toBeTruthy();
  const incident = (await (
    await request.get(`/api/incidents?mission_id=${mission.id}`, {
      headers: { "X-ATLAS-Bridge-Key": bridgeKey },
    })
  ).json())[0];
  const provenance = await (await request.get("/version")).json();

  await page.goto("/");
  await page.getByLabel("Username").fill("atlas-admin");
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForTimeout(750);
  await page.getByRole("button", { name: /sensor failure robot-3/ }).click();
  const drawer = page.getByRole("dialog", { name: "Incident evidence" });
  await page.waitForTimeout(750);
  await drawer.getByRole("button", { name: "Investigate incident" }).click();
  const investigation = drawer.getByRole("region", {
    name: "Investigation result",
  });
  await expect(investigation).toContainText(
    "supports a sensor-path mission failure",
  );
  await expect(investigation.getByText(/event:portfolio-demo:/)).toBeVisible();
  await expect(investigation.getByText(/document:DOC-SENSOR-001/)).toBeVisible();
  await page.waitForTimeout(1500);

  await page.screenshot({
    path: resolve(artifacts, "atlas-incident-investigation.png"),
    fullPage: false,
  });
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    drawer.getByRole("button", { name: "Download incident report" }).click(),
  ]);
  await download.saveAs(resolve(artifacts, "atlas-incident-report.html"));

  const investigationResponse = await request.post(
    `/api/incidents/${incident.id}/investigate`,
    { headers: { "X-CSRF-Token": csrf } },
  );
  const result = await investigationResponse.json();
  await writeFile(
    resolve(artifacts, "atlas-demo-evidence.json"),
    JSON.stringify(
      {
        schema_version: "atlas-portfolio-demo-v1",
        atlas: provenance,
        scenario: "Robot 3 inspection sensor failure",
        mission: { id: mission.id, expected_status: "failed" },
        injected_event_id: eventId,
        incident: {
          id: incident.id,
          type: incident.type,
          event_ids: incident.event_ids,
        },
        investigation: {
          confidence: result.confidence,
          generated_by: result.generated_by,
          citations: result.citations,
          limitations: result.limitations,
          recommended_next_step: result.recommended_next_step,
        },
      },
      null,
      2,
    ) + "\n",
  );
  const video = page.video();
  await context.close();
  expect(video).not.toBeNull();
  await video?.saveAs(resolve(artifacts, "atlas-incident-investigation.webm"));
});
