import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  // Относительные пути в сборке: статику публикуем не в корне домена, а рядом с
  // index.html. С абсолютным «/assets/...» опубликованная демонстрация не находит скрипты.
  base: "./",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true,
  },
});
