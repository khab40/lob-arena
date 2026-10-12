import { validateDemoAuthConfig, validateDemoSession } from "./ceoAuthContract";

async function authRequest(path: string, signal: AbortSignal, body?: unknown) {
  return fetch(`/api/auth/${path}`, {
    method: body === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store",
    redirect: "error", signal,
    ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
  });
}

export async function getDemoSession(signal: AbortSignal) {
  const response = await authRequest("session", signal);
  if (response.status === 401) return null;
  if (!response.ok) throw new Error("Sign-in is unavailable. Please try again.");
  return validateDemoSession(await response.json());
}

export async function getDemoAuthConfig(signal: AbortSignal) {
  const response = await authRequest("config", signal);
  if (!response.ok) throw new Error("Sign-in is unavailable. Please try again.");
  return validateDemoAuthConfig(await response.json());
}

export async function signInToDemo(credential: string, signal: AbortSignal) {
  if (!credential || credential.length > 12000) throw new Error("Sign-in could not be completed. Please try again.");
  const response = await authRequest("google", signal, { credential });
  if (!response.ok) throw new Error("Sign-in could not be completed. Please try again.");
  return validateDemoSession(await response.json());
}

export async function signOutOfDemo(signal: AbortSignal) {
  const response = await authRequest("logout", signal, {});
  if (response.status !== 204) throw new Error("Sign-out could not be confirmed. Please try again.");
}
