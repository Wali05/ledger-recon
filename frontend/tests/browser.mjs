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
  await rows.first().waitFor();
  assert.equal(await rows.count(), 25);
  assert.equal(await page.locator(".reconcile-card").count(), 1);
  assert.equal(await page.locator(".stat-card").count(), 4);
  assert.equal(
    await page.locator(".stat-value").nth(0).innerText(),
    snapshot.ledger_rows.toLocaleString("en-GB"),
  );
  assert.equal(
    await page.locator(".stat-value").nth(1).innerText(),
    String(snapshot.items.length),
  );
  await page.locator(".breakdown-list").waitFor();
  await page.screenshot({
    path: resolve(screenshots, "dashboard.png"),
    fullPage: false,
    animations: "disabled",
  });

  const firstTransaction = await rows.first().locator(".txn-id").innerText();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.waitForFunction(() =>
    document.querySelector(".pagination-info")?.textContent.includes("Page 2"),
  );
  assert.notEqual(
    await rows.first().locator(".txn-id").innerText(),
    firstTransaction,
  );
  await page
    .getByLabel("Break type", { exact: true })
    .selectOption("DUPLICATE");
  await page.waitForFunction(() =>
    document.querySelector(".pagination-info")?.textContent.includes("Page 1"),
  );
  await rows.first().waitFor();
  assert.ok(
    (await rows.locator("td:nth-child(2)").allTextContents()).every((text) =>
      text.includes("Duplicate"),
    ),
  );
  await page.getByLabel("Break type", { exact: true }).selectOption("ALL");
  await page.getByRole("button", { name: /^Transaction/ }).click();
  await page.waitForFunction(
    () =>
      document.querySelector("th")?.getAttribute("aria-sort") === "ascending",
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
  assert.match(await dialog.innerText(), /Rule evidence/i);
  const box = await dialog.boundingBox();
  assert.ok(box.width <= 660 && box.width > 400);
  await page.screenshot({
    path: resolve(screenshots, "break-detail.png"),
    animations: "disabled",
  });
  await dialog
    .getByLabel("Note for the record (optional)")
    .fill("Matched to bank fee");
  await dialog
    .getByRole("button", { name: "Mark resolved", exact: true })
    .click();
  await page.waitForFunction(
    () => document.querySelectorAll(".stat-value")[2]?.textContent === "1",
  );
  await dialog.getByRole("button", { name: "Reopen", exact: true }).waitFor();
  const history = await dialog.locator(".history-list").innerText();
  assert.match(history, /resolved by demo visitor/i);
  assert.match(history, /Matched to bank fee/);
  await page.keyboard.press("Escape");
  assert.equal(await dialog.count(), 0);
  await page
    .getByRole("button", { name: "Replay sample results", exact: true })
    .click();
  await page.waitForFunction(() =>
    document.querySelector(".job-status")?.textContent.includes("complete"),
  );
  await page.reload();
  await rows.first().waitFor();
  assert.equal(await page.locator(".stat-value").nth(2).innerText(), "1");
  await page.getByLabel("Resolution status").selectOption("true");
  await page.waitForFunction(
    () => document.querySelectorAll("tbody tr").length === 1,
  );
  assert.equal(await rows.first().locator(".txn-id").innerText(), transaction);
  const downloadEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  const download = await downloadEvent;
  const csv = await readFile(await download.path(), "utf8");
  assert.ok(csv.includes(transaction) && csv.includes("resolved_at"));
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
    () => document.querySelectorAll(".stat-value")[2]?.textContent === "0",
  );
  assert.equal(await page.getByLabel("Resolution status").inputValue(), "");

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
    "Browser checks passed: desktop/mobile, filtering, pagination, sorting, evidence, resolve with note and history, replay, reload, reset, CSV, keyboard, and no API dependency.",
  );
} finally {
  await browser?.close();
  server?.kill();
}
