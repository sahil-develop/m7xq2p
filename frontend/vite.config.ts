/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // In development the FastAPI backend runs separately on :8000.
    proxy: { "/api": process.env.VITE_PROXY_TARGET ?? "http://localhost:8000" },
  },
  test: { environment: "node" },
});
