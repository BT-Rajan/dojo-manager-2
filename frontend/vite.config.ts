import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// In development the FastAPI backend runs on :8000; /api is proxied so the session cookie
// stays same-origin.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "src"),
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:8000", changeOrigin: false },
    },
    fs: { strict: true, deny: ["**/.*"] },
  },
});
