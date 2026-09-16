import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // 127.0.0.1 explícito: por padrão o Vite escuta só em ::1 no Windows, e a API
  // escuta só em IPv4 — a mistura custa ~2,3 s de espera por requisição.
  server: { host: "127.0.0.1", port: 5173 },
});
