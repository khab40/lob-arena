import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { resolveImportWindow } from "../src/pages/importWindow.ts";

const candidate = {
  candidate_id: "candidate-1",
  symbol: "SPY",
  trade_date: "2012-06-21",
  start_time_ms: 34_200_000,
  end_time_ms: 37_800_000,
  start_time: "09:30:00.000",
  end_time: "10:30:00.000",
  depth: 10,
  message_file: "message.csv",
  orderbook_file: "orderbook.csv",
  message_file_size: 100,
  orderbook_file_size: 100,
  status: "ready",
  errors: [],
  dataset_id: null
};

describe("custom ingestion windows", () => {
  it("builds the requested window for a positive whole number of minutes", () => {
    const result = resolveImportWindow(candidate, {
      customMinutes: "17",
      duration: "custom",
      startTime: "09:35:00"
    });

    assert.equal(result.valid, true);
    assert.deepEqual(result.request, {
      start_time_ms: 34_500_000,
      end_time_ms: 35_520_000
    });
    assert.equal(result.label, "09:35:00–09:52:00");
  });

  it("rejects fractional, non-positive, and out-of-range durations", () => {
    for (const customMinutes of ["0", "-2", "1.5", ""]) {
      const result = resolveImportWindow(candidate, {
        customMinutes,
        duration: "custom",
        startTime: "09:35:00"
      });
      assert.equal(result.valid, false);
      assert.match(result.error, /positive whole number/);
    }

    const outside = resolveImportWindow(candidate, {
      customMinutes: "56",
      duration: "custom",
      startTime: "09:35:00"
    });
    assert.equal(outside.valid, false);
    assert.match(outside.error, /fit inside/);
  });
});
