import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createDemoClient } from "../src/demo/client.js";
import { formatAmount, formatCompact } from "../src/format.js";

const snapshot = JSON.parse(
  readFileSync(new URL("../src/demo/snapshot.json", import.meta.url)),
);
const memory = () => {
  const values = new Map();
  return {
    getItem: (key) => values.get(key),
    setItem: (key, value) => values.set(key, value),
  };
};

test("demo resolves locally, preserves reruns and reloads, and resets only its own state", async () => {
  const storage = memory(),
    client = createDemoClient(snapshot, storage);
  const first = (await client.request("/breaks?page_size=1")).items[0];
  const result = await client.request(`/breaks/${first.break_id}/resolve`);
  assert.equal(
    (await client.request(`/breaks/${first.break_id}/resolve`)).resolved_at,
    result.resolved_at,
  );
  await client.request("/reconcile/run?source=synthetic");
  const reloaded = createDemoClient(snapshot, storage);
  assert.equal(
    (await reloaded.request(`/breaks/${first.break_id}`)).resolved,
    true,
  );
  assert.equal((await reloaded.request("/stats")).total_breaks_resolved, 1);
  reloaded.reset();
  assert.equal((await reloaded.request("/stats")).total_breaks_resolved, 0);
});

test("filters and pagination operate across the complete sample", async () => {
  const client = createDemoClient(snapshot);
  const all = await client.request("/breaks?page_size=200");
  assert.equal(all.total, 167);
  const duplicates = await client.request(
    "/breaks?break_type=DUPLICATE&page_size=3&page=2",
  );
  assert.equal(duplicates.total, 20);
  assert.equal(duplicates.items.length, 3);
  assert.ok(duplicates.items.every((item) => item.break_type === "DUPLICATE"));
  assert.equal((await client.request("/breaks?source=uploaded")).total, 0);
});

test("numeric sorting retains precision beyond JavaScript's safe integer boundary", async () => {
  const items = ["90071992547409.1234", "2.0000", "90071992547409.1233"].map(
    (amount, index) => ({
      break_id: String(index),
      internal_amount: amount,
      source: "synthetic",
      break_type: "AMOUNT_MISMATCH",
    }),
  );
  const client = createDemoClient({ ...snapshot, items });
  const result = await client.request(
    "/breaks?sort_by=internal_amount&sort_dir=asc",
  );
  assert.deepEqual(
    result.items.map((item) => item.internal_amount),
    ["2.0000", "90071992547409.1233", "90071992547409.1234"],
  );
  assert.equal(
    formatAmount("90071992547409.1234", "USD"),
    "USD 90,071,992,547,409.1234",
  );
  assert.equal(formatAmount("5091.8100", "USD"), "USD 5,091.81");
  assert.equal(formatAmount("-0.0300"), "-0.03");
  assert.equal(formatAmount("12.0050"), "12.005");
});

test("export follows filters and still emits headers for an empty view", async () => {
  const client = createDemoClient(snapshot);
  const exported = await (
    await client.request("/breaks/export?break_type=DUPLICATE")
  ).text();
  assert.equal(exported.trim().split("\r\n").length, 21);
  assert.ok(
    (
      await (await client.request("/breaks/export?resolved=true")).text()
    ).startsWith("break_id,transaction_id"),
  );
  const withNegativeAmount = createDemoClient({
    ...snapshot,
    items: [
      {
        ...snapshot.items[0],
        transaction_id: "=SUM(1)",
        delta_amount: "-0.0400",
      },
    ],
  });
  const negativeCsv = await (
    await withNegativeAmount.request("/breaks/export")
  ).text();
  assert.ok(negativeCsv.includes('"-0.0400"'));
  assert.ok(negativeCsv.includes('"\'=SUM(1)"'));
  assert.ok(negativeCsv.includes("evidence_side,occurrence"));
});

test("the public demo cannot upload data or generate AI explanations", async () => {
  const client = createDemoClient(snapshot);
  await assert.rejects(
    client.request("/reconcile/upload"),
    /connected backend/,
  );
  await assert.rejects(
    client.request(`/breaks/${snapshot.items[0].break_id}/ai-explain`),
    /disabled/,
  );
  assert.equal((await client.request("/stats")).ai_enabled, false);
});

test("demo keeps a review history with notes and supports reopening", async () => {
  const storage = memory(),
    client = createDemoClient(snapshot, storage);
  const first = (await client.request("/breaks?page_size=1")).items[0];
  const url = `/breaks/${first.break_id}`;
  const body = (note) => ({ method: "POST", body: JSON.stringify({ note }) });
  await client.request(`${url}/resolve`, body("Fee confirmed"));
  const repeat = await client.request(`${url}/resolve`, body("again"));
  assert.equal(repeat.message, "Break was already resolved");
  const reopened = await client.request(`${url}/reopen`, body(" "));
  assert.equal(reopened.resolved, false);
  const reloaded = createDemoClient(snapshot, storage);
  const events = await reloaded.request(`${url}/events`);
  assert.deepEqual(
    events.map((event) => [event.action, event.note]),
    [
      ["resolved", "Fee confirmed"],
      ["reopened", null],
    ],
  );
  assert.equal((await reloaded.request(url)).resolved, false);
  assert.equal((await reloaded.request("/session")).reviewer, "demo visitor");
});

test("demo search, confidence filter and triage order match the API", async () => {
  const client = createDemoClient(snapshot);
  const split = snapshot.items.find(
    (item) => item.break_type === "SPLIT_SETTLEMENT",
  );
  const member = split.related_rows[0].transaction_id.toLowerCase();
  const found = await client.request(`/breaks?q=${member}`);
  assert.deepEqual(
    found.items.map((item) => item.break_id),
    [split.break_id],
  );
  const medium = await client.request(
    "/breaks?confidence=medium&page_size=200",
  );
  assert.ok(medium.total > 0);
  assert.ok(medium.items.every((item) => item.confidence === "medium"));
  const ordered = await client.request(
    "/breaks?sort_by=confidence&sort_dir=asc&page_size=200",
  );
  const rank = { low: 0, medium: 1, high: 2 };
  const ranks = ordered.items.map((item) => rank[item.confidence]);
  assert.deepEqual(
    ranks,
    [...ranks].sort((a, b) => a - b),
  );
});

test("demo bulk review is conditional and logs every change", async () => {
  const storage = memory(),
    client = createDemoClient(snapshot, storage);
  const ids = snapshot.items.slice(0, 3).map((item) => item.break_id);
  await client.request(`/breaks/${ids[0]}/resolve`, { method: "POST" });
  const result = await client.request("/breaks/bulk-review", {
    method: "POST",
    body: JSON.stringify({ action: "resolve", break_ids: ids, note: "Batch" }),
  });
  assert.deepEqual([result.changed, result.unchanged], [2, 1]);
  assert.equal(result.message, "2 breaks resolved");
  const reloaded = createDemoClient(snapshot, storage);
  assert.equal((await reloaded.request("/stats")).total_breaks_resolved, 3);
  const events = await reloaded.request(`/breaks/${ids[1]}/events`);
  assert.deepEqual(
    events.map((event) => event.note),
    ["Batch"],
  );
  await assert.rejects(
    client.request("/breaks/bulk-review", {
      method: "POST",
      body: JSON.stringify({ action: "resolve", break_ids: [] }),
    }),
    /at least one/,
  );
});

test("demo statistics report exposure, confidence and auto-tied rows exactly", async () => {
  const client = createDemoClient(snapshot);
  const stats = await client.request("/stats");
  const types = Object.fromEntries(
    stats.breaks_by_type.map((row) => [row.break_type, row.open_value]),
  );
  // Amount breaks expose the difference; FX cents sum to well under a dollar.
  assert.match(types.FX_ROUNDING, /^0\.\d{4}$/);
  assert.equal(
    stats.open_by_confidence.reduce((sum, row) => sum + row.open_count, 0),
    snapshot.items.length,
  );
  const batchMembers = snapshot.items
    .filter((item) => item.evidence_side === "many_internal")
    .reduce((sum, item) => sum + item.related_rows.length, 0);
  const bankOnly = snapshot.items.filter(
    (item) => item.evidence_side === "external",
  ).length;
  assert.equal(
    stats.ledger_rows_in_breaks,
    snapshot.items.length -
      bankOnly -
      snapshot.items.filter((item) => item.evidence_side === "many_internal")
        .length +
      batchMembers,
  );
  assert.equal(formatCompact("2264512.3456"), "2.26M");
  assert.equal(formatCompact("999.995"), "999.995");
  assert.equal(formatCompact("-1500"), "-1.50K");
});
