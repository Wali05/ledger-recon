import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const target = process.env.API_PROXY_TARGET || "http://localhost:8000";
export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: Object.fromEntries(
      ["/reconcile", "/breaks", "/stats", "/health"].map((path) => [
        path,
        target,
      ]),
    ),
  },
});
