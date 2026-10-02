import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Any request to /api/... is forwarded to FastAPI, so the browser never hits CORS.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:8000" } },
});