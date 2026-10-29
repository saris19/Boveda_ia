import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on http://127.0.0.1:8000 (python run.py in backend/).
// The proxy lets the frontend call "/api/..." without CORS during local work.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
