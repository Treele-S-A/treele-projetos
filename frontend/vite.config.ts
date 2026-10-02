import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Mesmo commit que o servidor manda em X-Versao: se diferirem, esta tela é
  // de antes da última atualização (ver api.ts). Vazio fora da Vercel.
  define: {
    __VERSAO__: JSON.stringify((process.env.VERCEL_GIT_COMMIT_SHA ?? "").slice(0, 12)),
  },
  // 127.0.0.1 explícito: por padrão o Vite escuta só em ::1 no Windows, e a API
  // escuta só em IPv4 — a mistura custa ~2,3 s de espera por requisição.
  server: {
    host: "127.0.0.1",
    port: 5173,
    // Com VITE_API=/api, a tela em desenvolvimento fala com a API do Docker
    // (porta 8000, sem prefixo) pela mesma origem — sem depender do CORS.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        rewrite: (caminho) => caminho.replace(/^\/api/, ""),
      },
    },
  },
});
