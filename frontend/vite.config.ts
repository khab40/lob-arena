import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { bypassRemoteDemoProxy, ceoLoopbackProxy } from "./dev/ceoLoopbackProxy.ts";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const authenticatedDemo = (process.env.VITE_CEO_DEMO ?? env.VITE_CEO_DEMO) === "true";
  const protectedProxy = {
    target: "http://127.0.0.1:8000", changeOrigin: false, xfwd: false,
    bypass: bypassRemoteDemoProxy
  };
  return {
  plugins: [ceoLoopbackProxy(authenticatedDemo), react()],
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
      "/api/auth": protectedProxy,
      "/api/ceo-demo": protectedProxy,
      ...(authenticatedDemo ? {
        "/api": protectedProxy,
        "/health": protectedProxy,
        "/ws/arena": { ...protectedProxy, ws: true }
      } : {})
    },
    allowedHosts: [
      '.trycloudflare.com'
    ]
  }
  };
});


