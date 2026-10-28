import { defineConfig } from "vite";
export default defineConfig({
  server: {
    host: "127.0.0.1",
    port: 3400,
    proxy: { "/api": "http://127.0.0.1:8400" },
  },
  build: {
    target: "es2022",
    rollupOptions: {
      output: {
        manualChunks: (id: string) =>
          id.includes("/three/") ? "three" : undefined,
      },
    },
  },
});
