import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// Pair 06: PORT_BASE = 9000 + 6 x 10 = 9060 (backend), so the React dev server uses 9061.
// strictPort makes Vite stop with an error instead of silently picking another port
// (the backend only allows requests from http://localhost:9061).
export default defineConfig({
  plugins: [react()],
  server: { port: 9061, strictPort: true },
  preview: { port: 9061, strictPort: true },
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost:9061" } },
    globals: true,
    setupFiles: "./src/test/setup.js",
    css: false,
  },
});
