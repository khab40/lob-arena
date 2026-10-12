export type DemoSession = {
  user: { id: string; email: string; name: string };
  workspace_id: "ceo-demo";
  expires_at: string;
};

export type DemoAuthConfig = { configured: boolean; client_id: string | null; nonce: string | null };

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid sign-in response.");
  return value as Record<string, unknown>;
}

function text(value: unknown, limit: number): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= limit
    && ![...value].some((character) => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127);
}

export function validateDemoSession(value: unknown): DemoSession {
  const session = record(value);
  const user = record(session.user);
  if (!text(user.id, 128) || !text(user.email, 254) || !text(user.name, 200)
      || session.workspace_id !== "ceo-demo" || !text(session.expires_at, 40)
      || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|\+00:00)$/.test(session.expires_at)
      || !Number.isFinite(Date.parse(session.expires_at))) throw new Error("Invalid sign-in response.");
  return value as DemoSession;
}

export function validateDemoAuthConfig(value: unknown): DemoAuthConfig {
  const config = record(value);
  if (config.configured === false && config.client_id === null && config.nonce === null) return value as DemoAuthConfig;
  if (config.configured !== true || !text(config.client_id, 256)
      || !/^[A-Za-z0-9_-]+\.apps\.googleusercontent\.com$/.test(config.client_id)
      || !text(config.nonce, 128) || !/^[A-Za-z0-9_-]{32,128}$/.test(config.nonce)) {
    throw new Error("Invalid sign-in response.");
  }
  return value as DemoAuthConfig;
}
