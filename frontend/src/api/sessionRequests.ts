type Scope = { controller: AbortController; onAccessEnded: () => void };
let required = false;
let scope: Scope | null = null;

// The confirmed account owns pending requests. No token is stored in the browser.
export function startSessionRequests(onAccessEnded: () => void) {
  required = true;
  scope?.controller.abort();
  const owned = { controller: new AbortController(), onAccessEnded };
  scope = owned;
  return () => {
    owned.controller.abort();
    if (scope === owned) scope = null;
  };
}

export async function sessionFetch(input: RequestInfo | URL, init?: RequestInit) {
  if (!required) return globalThis.fetch(input, init);
  const owned = scope;
  if (!owned || owned.controller.signal.aborted) throw new Error("Application session required.");
  const url = new URL(input instanceof Request ? input.url : String(input), window.location.origin);
  if (url.origin !== window.location.origin || url.username || url.password) {
    throw new Error("Authenticated application requests require the same origin.");
  }
  const signal = AbortSignal.any([owned.controller.signal, ...(init?.signal ? [init.signal] : [])]);
  const response = await globalThis.fetch(input, { ...init, signal, credentials: "same-origin", cache: "no-store", redirect: "error" });
  signal.throwIfAborted();
  if (response.status === 401) {
    owned.controller.abort();
    if (scope === owned) { scope = null; owned.onAccessEnded(); }
    throw new Error("Your session ended. Sign in to continue.");
  }
  return response;
}
