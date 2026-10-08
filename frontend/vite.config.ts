import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dashboard calls /api/...; Vite forwards those requests to the FastAPI backend.
// Override the backend address with:  set API_TARGET=http://localhost:8001  (cmd)
// 127.0.0.1, not "localhost": uvicorn listens on IPv4 only, while Node resolves localhost to ::1 first.
const apiTarget = process.env.API_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: Number(process.env.PORT ?? 5173),
    proxy: { "/api": { target: apiTarget, changeOrigin: true } },
  },
});
