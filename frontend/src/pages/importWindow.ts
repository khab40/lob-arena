import type { IngestionCandidate } from "@/api/client";

export type ImportDuration = "1" | "5" | "30" | "60" | "custom" | "full";

export type ImportWindowSelection = {
  customMinutes: string;
  duration: ImportDuration;
  startTime: string;
};

export function defaultImportWindow(candidate: IngestionCandidate): ImportWindowSelection {
  const itchDefaultStart = 34_200_000;
  const startTimeMs = candidate.source_type === "nasdaq_itch"
    && itchDefaultStart >= candidate.start_time_ms
    && itchDefaultStart < candidate.end_time_ms
    ? itchDefaultStart
    : candidate.start_time_ms;
  return {
    customMinutes: "10",
    duration: candidate.source_type === "nasdaq_itch" ? "30" : "1",
    startTime: formatTimeInput(startTimeMs)
  };
}

export function resolveImportWindow(
  candidate: IngestionCandidate,
  selection = defaultImportWindow(candidate)
): {
  error: string;
  label: string;
  request: { start_time_ms?: number; end_time_ms?: number };
  valid: boolean;
} {
  if (selection.duration === "full") {
    return {
      error: "",
      label: `${candidate.start_time}–${candidate.end_time}`,
      request: {},
      valid: true
    };
  }
  const startTimeMs = parseTimeInput(selection.startTime);
  const durationMinutes = selection.duration === "custom"
    ? Number(selection.customMinutes)
    : Number(selection.duration);
  if (!Number.isInteger(durationMinutes) || durationMinutes <= 0) {
    return {
      error: "Duration must be a positive whole number of minutes.",
      label: "",
      request: {},
      valid: false
    };
  }
  const durationMs = durationMinutes * 60_000;
  const endTimeMs = startTimeMs + durationMs;
  if (
    !Number.isFinite(startTimeMs) ||
    startTimeMs < candidate.start_time_ms ||
    endTimeMs > candidate.end_time_ms
  ) {
    return {
      error: "Window must fit inside the source range.",
      label: "",
      request: {},
      valid: false
    };
  }
  return {
    error: "",
    label: `${formatTimeInput(startTimeMs)}–${formatTimeInput(endTimeMs)}`,
    request: { start_time_ms: startTimeMs, end_time_ms: endTimeMs },
    valid: true
  };
}

export function formatTimeInput(value: number) {
  const hours = Math.floor(value / 3_600_000);
  const minutes = Math.floor((value % 3_600_000) / 60_000);
  const seconds = Math.floor((value % 60_000) / 1_000);
  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

function parseTimeInput(value: string) {
  const parts = value.split(":").map(Number);
  if (parts.length < 2 || parts.some((part) => !Number.isFinite(part))) return Number.NaN;
  const [hours, minutes, seconds = 0] = parts;
  return ((hours * 60 + minutes) * 60 + seconds) * 1_000;
}
