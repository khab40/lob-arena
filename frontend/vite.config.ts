import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { ceoLoopbackProxy } from "./dev/ceoLoopbackProxy.ts";

export default defineConfig({
  plugins: [ceoLoopbackProxy(), react()],
  build: {
    chunkSizeWarningLimit: 650,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/recharts") || id.includes("node_modules/d3-")) {
            return "charts";
          }
          if (id.includes("node_modules/react") || id.includes("node_modules/react-dom") || id.includes("node_modules/react-router")) {
            return "react-vendor";
          }
          if (id.includes("node_modules")) {
            return "vendor";
          }
        }
      }
    }
  },
  resolve: {
    alias: {
      "@": "/src"
    }
  },
  server: {
    port: 5173,
    proxy: {
      "/api/auth": { target: "http://127.0.0.1:8000", changeOrigin: false, xfwd: false },
      "/api/ceo-demo": { target: "http://127.0.0.1:8000", changeOrigin: false, xfwd: false }
    },
    allowedHosts: [
      '.trycloudflare.com'
    ]
  }
});


