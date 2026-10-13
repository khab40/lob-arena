import { isIP } from "node:net";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

function isLoopback(peer: string | undefined) {
  if (!peer) return false;
  const address = peer.toLowerCase();
  if (address === "::1") return true;
  const ipv4 = address.startsWith("::ffff:") ? address.slice(7) : address;
  return isIP(ipv4) === 4 && ipv4.startsWith("127.");
}

export function demoProxyAllowed(request: IncomingMessage) {
  const forwarded = Object.keys(request.headers).some((name) => {
    const key = name.toLowerCase();
    return key === "forwarded" || key === "x-real-ip" || key.startsWith("x-forwarded-");
  });
  return isLoopback(request.socket.remoteAddress) && !forwarded;
}

// Vite applies bypass before opening its HTTP or WebSocket upstream connection.
export function bypassRemoteDemoProxy(request: IncomingMessage) {
  return demoProxyAllowed(request) ? undefined : false;
}

export function guardDemoProxy(request: IncomingMessage, response: ServerResponse, next: () => void, fullApplication = false) {
  const path = request.url ?? "";
  if (!path.startsWith("/api/auth") && !path.startsWith("/api/ceo-demo")
    && !(fullApplication && (path.startsWith("/api") || path.startsWith("/ws/")
      || path === "/health" || path.startsWith("/health?")))) return next();
  if (demoProxyAllowed(request)) return next();
  response.statusCode = 403;
  response.setHeader("Cache-Control", "no-store");
  response.setHeader("Content-Type", "application/json");
  response.end('{"detail":"Local access required"}');
}

export function ceoLoopbackProxy(fullApplication = false): Plugin {
  const guard = fullApplication
    ? (request: IncomingMessage, response: ServerResponse, next: () => void) => guardDemoProxy(request, response, next, true)
    : guardDemoProxy;
  return {
    name: "ceo-loopback-proxy",
    configureServer(server) {
      // Register before Vite's proxy replaces the original socket identity.
      server.middlewares.use(guard);
    },
    configurePreviewServer(server) {
      server.middlewares.use(guard);
    }
  };
}
