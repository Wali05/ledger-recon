import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

// Only target a disposable local stack: this replaces its uploaded dataset.
const url = process.env.LIVE_URL;
assert.ok(
  url,
  "Set LIVE_URL to a disposable connected dashboard, e.g. http://localhost:5173",
);
assert.ok(
  ["localhost", "127.0.0.1"].includes(new URL(url).hostname),
  "This check is restricted to a local test stack",
);
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || undefined,
});
try {
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1000 },
  });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(url);
  // With API_KEYS configured on the server, pass one key via API_KEY.
  if (process.env.API_KEY) {
    const field = page.getByLabel("API key");
    await field.fill("wrong-key-0000000000");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.getByText("That key was not accepted.").waitFor();
    await field.fill(process.env.API_KEY);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await page.getByRole("button", { name: "Sign out" }).waitFor();
  }
  await page.getByText("Connected workspace", { exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Your CSV files", exact: true })
    .click();
  const ledger = await readFile(
    new URL("../../samples/ledger.csv", import.meta.url),
    "utf8",
  );
  await page.getByLabel("Internal ledger CSV").setInputFiles({
    name: "ledger.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      ledger.replace("Test Transaction 1", `Browser check ${Date.now()}`),
    ),
  });
  await page
    .getByLabel("Bank statement CSV")
    .setInputFiles(
      fileURLToPath(new URL("../../samples/statement.csv", import.meta.url)),
    );
  const uploaded = page.waitForResponse(
    (response) =>
      response.url().endsWith("/reconcile/upload") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Upload both files", exact: true })
    .click();
  assert.equal((await uploaded).status(), 200);
  await page.waitForFunction(
    () => document.querySelectorAll(".stat-value")[0]?.textContent === "3",
  );
  async function run() {
    const accepted = page.waitForResponse(
      (response) =>
        response.url().includes("/reconcile/run?") &&
        response.request().method() === "POST",
    );
    const completed = page.waitForResponse(
      async (response) =>
        response.url().includes("/reconcile/status/") &&
        response.ok() &&
        (await response.json()).status === "complete",
      { timeout: 60000 },
    );
    await page
      .getByRole("button", { name: "Run reconciliation", exact: true })
      .click();
    const response = await accepted;
    assert.equal(response.status(), 202);
    const jobId = (await response.json()).job_id;
    assert.equal((await (await completed).json()).job_id, jobId);
    await page.waitForFunction(() =>
      document.querySelector(".job-status")?.textContent.includes("complete"),
    );
    return jobId;
  }
  const firstJob = await run();
  const rows = page.locator("tbody tr");
  await page.waitForFunction(
    () => document.querySelectorAll("tbody tr").length === 3,
  );
  assert.equal(await page.locator(".stat-value").nth(1).innerText(), "3");
  await rows
    .filter({ hasText: "TXN_TEST_2" })
    .getByRole("button", { name: /^View break/ })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("button", { name: "Mark resolved", exact: true })
    .waitFor();
  assert.match(await dialog.innerText(), /10\.00/);
  await dialog
    .getByLabel("Note for the record (optional)")
    .fill("Confirmed with bank");
  await dialog
    .getByRole("button", { name: "Mark resolved", exact: true })
    .click();
  await dialog.getByRole("button", { name: "Reopen", exact: true }).waitFor();
  assert.match(
    await dialog.locator(".history-list").innerText(),
    new RegExp(`resolved by ${process.env.API_REVIEWER || "local"}`, "i"),
  );
  await page.waitForFunction(
    () => document.querySelectorAll(".stat-value")[2]?.textContent === "1",
  );
  await page.keyboard.press("Escape");
  const secondJob = await run();
  assert.notEqual(firstJob, secondJob);
  await page.reload();
  await page
    .getByRole("button", { name: "Your CSV files", exact: true })
    .click();
  await page.waitForFunction(
    () => document.querySelectorAll(".stat-value")[2]?.textContent === "1",
  );
  await page.getByLabel("Resolution status").selectOption("true");
  await page.waitForFunction(
    () => document.querySelectorAll("tbody tr").length === 1,
  );
  assert.match(await rows.first().innerText(), /TXN_TEST_2/);
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV", exact: true }).click();
  const csv = await readFile(await (await downloaded).path(), "utf8");
  assert.ok(
    csv.includes("TXN_TEST_2") &&
      csv.includes("resolved_at") &&
      !csv.includes("TXN_TEST_3"),
  );
  assert.deepEqual(errors, []);
  console.log(
    "Connected browser flow passed: CSV pair → queued job → 3 breaks → evidence → resolve → rerun → reload → filtered CSV.",
  );
} finally {
  await browser.close();
}
