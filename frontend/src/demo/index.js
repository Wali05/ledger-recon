import snapshot from "./snapshot.json";
import { createDemoClient } from "./client.js";

let storage;
try {
  storage = window.localStorage;
} catch {
  /* Browser privacy mode. */
}
export const client = createDemoClient(snapshot, storage);
