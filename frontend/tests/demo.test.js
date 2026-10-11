import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createDemoClient } from "../src/demo/client.js";
import { formatAmount } from "../src/format.js";

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
  assert.equal(all.total, 130);
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
