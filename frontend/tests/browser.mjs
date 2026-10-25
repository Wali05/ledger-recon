import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "playwright";

// Exercise the built public demo, including persistence and keyboard review.
// Set DEMO_URL to use an existing preview; otherwise start and stop our own.
const url = process.env.DEMO_URL || "http://127.0.0.1:4180";
const screenshots = resolve(process.env.SCREENSHOT_DIR || "test-results");
const snapshot = JSON.parse(
  await readFile(new URL("../src/demo/snapshot.json", import.meta.url), "utf8"),
);
const server = process.env.DEMO_URL
  ? null
  : spawn(
      process.execPath,
      [
        "node_modules/vite/bin/vite.js",
        "preview",
        "--host",
        "127.0.0.1",
        "--port",
        "4180",
        "--strictPort",
      ],
      { stdio: "ignore" },
    );
let browser;
try {
  let ready = false;
  for (let attempt = 0; attempt < 60; attempt++) {
    try {
      ready = (await fetch(url)).ok;
    } catch {
      /* The preview is still starting. */
    }
    if (ready) break;
    await new Promise((done) => setTimeout(done, 250));
  }
  assert.ok(ready, "Demo preview did not start. Build the demo first.");
  await mkdir(screenshots, { recursive: true });
  browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1440 },
    locale: "en-GB",
    timezoneId: "UTC",
  });
  const page = await context.newPage();
  const errors = [];
  const apiRequests = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("request", (request) => {
    if (
      /\/(stats|breaks|reconcile|health)(\?|\/|$)/.test(
        new URL(request.url()).pathname,
      )
    )
      apiRequests.push(request.url());
  });
  await page.goto(url);
  const rows = page.locator("tbody tr");
  const total = snapshot.items.length;
  const openCount = () => page.locator(".stat-value").nth(1).innerText();
  await rows.first().waitFor();
  assert.equal(await rows.count(), 25);
  assert.equal(await page.locator(".run-panel").count(), 1);
  assert.equal(await page.locator(".stat-card").count(), 4);
  assert.equal(await openCount(), String(total));
  assert.match(
    await page.locator(".stat-value").nth(0).innerText(),
    /^\d+\.\d%$/,
  );
  // The queue opens least certain first.
  const order = { low: 0, medium: 1, high: 2 };
  const firstLevel = Math.min(
    ...snapshot.items.map((item) => order[item.confidence]),
  );
  assert.ok(
    (await rows.first().locator(".confidence").innerText())
      .toLowerCase()
      .includes(Object.keys(order)[firstLevel]),
  );
  await page.locator(".mix-list").waitFor();
  await page.screenshot({
    path: resolve(screenshots, "dashboard.png"),
    fullPage: false,
    animations: "disabled",
  });

  const firstTransaction = await rows.first().locator(".txn-id").innerText();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.waitForFunction(() =>
    document.querySelector(".pagination-info")?.textContent.includes("page 2"),
  );
  assert.notEqual(
    await rows.first().locator(".txn-id").innerText(),
    firstTransaction,
  );

  // Type filter from the select, then from the break mix panel.
  await page
    .getByLabel("Break type", { exact: true })
    .selectOption("DUPLICATE");
  await page.waitForFunction(() =>
    document.querySelector(".pagination-info")?.textContent.includes("page 1"),
  );
  await rows.first().waitFor();
  assert.ok(
    (await rows.locator("td:nth-child(3)").allTextContents()).every((text) =>
      text.includes("Duplicate"),
    ),
  );
  const splits = snapshot.items.filter(
    (item) => item.break_type === "SPLIT_SETTLEMENT",
  );
  await page.locator(".mix-row", { hasText: "Split settlement" }).click();
  await page.waitForFunction(
    (count) => document.querySelectorAll("tbody tr").length === count,
    splits.length,
  );
  await page.locator(".mix-row", { hasText: "Split settlement" }).click();
  await page.waitForFunction(
    () => document.getElementById("break-type")?.value === "ALL",
  );

  // Search matches group members, not just the row's own ID.
  const member = splits[0].related_rows[0].transaction_id;
  await page.keyboard.press("/");
  await page.keyboard.type(member);
  await page.waitForFunction(
    (id) =>
      document.querySelectorAll("tbody tr").length === 1 &&
      document.querySelector("tbody .txn-id")?.textContent === id,
    splits[0].transaction_id,
  );
  await page.getByLabel("Search transactions").fill("");
  await page.waitForFunction(
    () => document.querySelectorAll("tbody tr").length === 25,
  );

  await page.getByRole("button", { name: /^Transaction/ }).click();
  await page.waitForFunction(
    () =>
      document.querySelectorAll("th")[1]?.getAttribute("aria-sort") ===
      "ascending",
  );
  const firstSortedId = snapshot.items
    .map((item) => item.transaction_id)
    .sort()[0];
  await page.waitForFunction(
    (expected) =>
      document.querySelector("tbody .txn-id")?.textContent === expected,
    firstSortedId,
  );
  const transaction = await rows.first().locator(".txn-id").innerText();
  await rows
    .first()
    .getByRole("button", { name: /^View break/ })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("button", { name: "Mark resolved", exact: true })
    .waitFor();
  assert.match(await dialog.innerText(), /Why it was flagged/i);
  const box = await dialog.boundingBox();
  assert.ok(box.width <= 620 && box.width > 400);
  await dialog
    .getByLabel("Note for the record (optional)")
    .fill("Matched to bank fee");
  await dialog
    .getByRole("button", { name: "Mark resolved", exact: true })
    .click();
  await page.waitForFunction(
    (expected) =>
      document.querySelectorAll(".stat-value")[1]?.textContent === expected,
    String(total - 1),
  );
  await dialog.getByRole("button", { name: "Reopen", exact: true }).waitFor();
  const history = await dialog.locator(".history-list").innerText();
  assert.match(history, /resolved by demo visitor/i);
  assert.match(history, /Matched to bank fee/);
  await page.keyboard.press("Escape");
  assert.equal(await dialog.count(), 0);

  // Keyboard review: j moves, Enter opens the evidence for the active row.
  await page.locator("h1").click();
  await page.keyboard.press("j");
  await page.keyboard.press("j");
  const active = await page.locator("tbody tr.active .txn-id").innerText();
  await page.keyboard.press("Enter");
  await dialog.getByText(active, { exact: true }).first().waitFor();
  await page.locator(".split, .members, .compare").first().waitFor();
  await page.screenshot({
    path: resolve(screenshots, "break-detail.png"),
    animations: "disabled",
  });
  await page.keyboard.press("Escape");

  // Bulk review: two selected rows resolved with one note.
  await page.locator("tbody tr").nth(0).getByRole("checkbox").check();
  await page.locator("tbody tr").nth(1).getByRole("checkbox").check();
  await page.getByLabel("Note for the selected breaks").fill("Bulk check");
  await page
    .getByRole("button", { name: "Resolve selected", exact: true })
    .click();
  await page.waitForFunction(
    (expected) =>
      document.querySelectorAll(".stat-value")[1]?.textContent === expected,
    String(total - 3),
  );
  assert.equal(await page.locator(".bulk-bar").count(), 0);

  await page
    .getByRole("button", { name: "Replay sample results", exact: true })
    .click();
  await page.waitForFunction(() =>
    document.querySelector(".job-status")?.textContent.includes("complete"),
  );
  await page.reload();
  await rows.first().waitFor();
  assert.equal(await openCount(), String(total - 3));
  await page.getByRole("button", { name: "Resolved", exact: true }).click();
  await page.waitForFunction(
    () => document.querySelectorAll("tbody tr").length === 3,
  );
  assert.ok(
    (await rows.locator(".txn-id").allTextContents()).includes(transaction),
  );
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  const download = await downloadEvent;
  const csv = await readFile(await download.path(), "utf8");
  assert.ok(csv.includes(transaction) && csv.includes("resolved_at"));
  assert.equal(csv.trim().split("\r\n").length, 4);

  // Theme switch persists across reloads.
  await page.getByRole("button", { name: "Switch to dark theme" }).click();
  assert.equal(
    await page.evaluate(() => document.documentElement.dataset.theme),
    "dark",
  );
  await page.reload();
  await rows.first().waitFor();
  assert.equal(
    await page.evaluate(() => document.documentElement.dataset.theme),
    "dark",
  );
  await page.keyboard.press("?");
  await page.getByRole("dialog", { name: "Keyboard shortcuts" }).waitFor();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Switch to light theme" }).click();

  await page
    .getByRole("button", { name: "Your CSV files", exact: true })
    .click();
  await page
    .getByText("File uploads require the FastAPI backend.", { exact: false })
    .waitFor();
  assert.equal(await page.locator('input[type="file"]').count(), 0);
  await page
    .getByRole("button", { name: "Sample dataset", exact: true })
    .click();
  await page.getByRole("button", { name: "Reset demo", exact: true }).click();
  await page.waitForFunction(
    (expected) =>
      document.querySelectorAll(".stat-value")[1]?.textContent === expected,
    String(total),
  );

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await rows.first().waitFor();
  await page.screenshot({
    path: resolve(screenshots, "mobile.png"),
    fullPage: true,
    animations: "disabled",
  });
  assert.ok(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
    "Mobile page overflows horizontally",
  );
  await rows
    .first()
    .getByRole("button", { name: /^View break/ })
    .click();
  await dialog
    .getByRole("button", { name: "Mark resolved", exact: true })
    .waitFor();
  await dialog.evaluate((element) =>
    Promise.all(element.getAnimations().map((animation) => animation.finished)),
  );
  const mobileBox = await dialog.boundingBox();
  assert.ok(mobileBox.x >= 0 && mobileBox.x + mobileBox.width <= 390);
  await page.keyboard.press("Escape");
  assert.deepEqual(errors, [], "Browser console or runtime errors");
  assert.deepEqual(
    apiRequests,
    [],
    "The static demo must not require a backend",
  );
  console.log(
    "Browser checks passed: desktop/mobile, triage order, filters, break mix, search, pagination, sorting, evidence, resolve with note and history, keyboard review, bulk resolve, replay, reload, theme, reset, CSV and no API dependency.",
  );
} finally {
  await browser?.close();
  server?.kill();
}
