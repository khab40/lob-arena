import { expect, test, type Page, type Route } from "@playwright/test";

// Small, invented API responses. Never copy private retained row evidence here.
const sessionId = "0123456789abcdef";
const secondSessionId = "fedcba9876543210";
const provenance = {
  verification_sha256: "a".repeat(64), settings_sha256: "b".repeat(64), job_id: "TEST-JOB",
  request_sha256: "c".repeat(64), model_checkpoint_sha256: "d".repeat(64),
  predictions: { sha256: "e".repeat(64), size_bytes: 123, version_id: "1" }
};
function catalog(total = 3, mixed = false) {
  return {
    kind: "saved_research_predictions", campaign_id: "december-holdout-20261007",
    label_context: "synthetic_research_labels", limitations: ["Invented test evidence; no production qualification."],
    provenance, detectors: [{ id: "transformer", threshold: 0.7, mode: "balanced" }, { id: "lightgbm", threshold: 0.6, mode: "balanced" }],
    sessions: [sessionId, secondSessionId].map((id) => ({
      id, rows: total, symbol: "TEST", family: mixed ? "mixed" : "test_family",
      families: mixed ? ["control", "test_attack"] : ["test_family"]
    }))
  };
}
function rows(url: URL, total = 3, mixed = false) {
  const offset = Number(url.searchParams.get("offset"));
  const detector = url.searchParams.get("detector");
  const session = url.searchParams.get("session_id");
  const threshold = detector === "transformer" ? 0.7 : 0.6;
  const count = Math.min(100, total - offset);
  return {
    campaign_id: "december-holdout-20261007", session_id: session, detector, threshold, mode: "balanced",
    total, offset, next_offset: offset + count < total ? offset + count : null, provenance,
    rows: Array.from({ length: count }, (_, index) => {
      const ordinal = offset + index;
      const probability = mixed ? ordinal >= 100 ? 0.9 : 0.2 : ordinal % 2 ? 0.9 : detector === "lightgbm" ? 0.3 : 0.2;
      return { ordinal, source_ordinal: ordinal + 50, target_id: `test-${session}-${ordinal}`,
        timestamp_ns: "9007199254740993123", symbol: "TEST", family: mixed ? ordinal < 100 ? "control" : "test_attack" : "test_family",
        synthetic_label: mixed ? ordinal >= 100 ? 1 : 0 : ordinal % 2, probability, alert: probability >= threshold };
    })
  };
}
async function mockSaved(page: Page, options: {
  total?: number; missing?: boolean; corrupt?: boolean; unavailableDetector?: boolean; mixed?: boolean;
  pageResponse?: (route: Route, url: URL) => Promise<void>;
} = {}) {
  const requests: URL[] = [];
  const sockets: string[] = [];
  page.on("websocket", (socket) => sockets.push(socket.url()));
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const url = new URL(route.request().url()); requests.push(url);
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname === "/api/research/saved-scores/campaigns") {
      if (options.missing) return json({ detail: "Disabled" }, 404);
      const value = catalog(options.total, options.mixed);
      if (options.unavailableDetector) value.detectors = value.detectors.filter((item) => item.id !== "lightgbm");
      return json(value);
    }
    if (url.pathname === "/api/research/saved-scores/campaigns/december-holdout-20261007/rows") {
      if (options.pageResponse) return options.pageResponse(route, url);
      const value = rows(url, options.total, options.mixed);
      if (options.corrupt) value.provenance = { ...provenance, verification_sha256: "f".repeat(64) };
      return json(value);
    }
    return json({ detail: "Unexpected test request" }, 500);
  });
  return { requests, sockets };
}

