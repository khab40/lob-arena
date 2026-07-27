import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { OrderBookSnapshot, PriceLevel } from "@/types/arena";
import {
  bucketHeatmapPrice,
  formatHeatmapPrice,
  inferPriceBucket,
  selectVisibleHeatmapPrices
} from "@/components/liquidityHeatmapScale";

export type HeatmapSnapshotFrame = {
  book: OrderBookSnapshot;
  tick: number;
};

export type HeatmapFrame = {
  tick: number;
  levels: {
    price: number;
    bidSize: number;
    askSize: number;
    abuserSize?: number;
  }[];
};

const DEFAULT_VISIBLE_LEVELS = 22;
const LEFT_AXIS_WIDTH = 72;
const BOTTOM_AXIS_HEIGHT = 18;

type HeatmapTheme = {
  axis: string;
  background: string;
  dangerRgb: string;
  grid: string;
  infoRgb: string;
  lowCell: string;
  successRgb: string;
  warningRgb: string;
};

export function LiquidityHeatmap({
  maxFrames = 72,
  snapshots,
  visibleLevels = DEFAULT_VISIBLE_LEVELS
}: {
  maxFrames?: number;
  snapshots: HeatmapSnapshotFrame[];
  visibleLevels?: number;
}) {
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const expandButtonRef = useRef<HTMLButtonElement | null>(null);
  const shouldRestoreFocusRef = useRef(false);
  const [canvasSize, setCanvasSize] = useState({ height: 320, width: 900 });
  const [expanded, setExpanded] = useState(false);
  const [themeVersion, setThemeVersion] = useState(0);
  const recentSnapshots = useMemo(() => snapshots.slice(-maxFrames), [maxFrames, snapshots]);
  const priceBucket = useMemo(() => inferPriceBucket(recentSnapshots), [recentSnapshots]);
  const frames = useMemo(() => toHeatmapFrames(recentSnapshots, priceBucket), [priceBucket, recentSnapshots]);
  const visiblePrices = useMemo(
    () => selectVisibleHeatmapPrices(snapshots.at(-1)?.book, visibleLevels, priceBucket),
    [priceBucket, snapshots, visibleLevels]
  );

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!wrapper) {
      return;
    }

    const observer = new ResizeObserver(([entry]) => {
      const width = Math.max(320, Math.floor(entry.contentRect.width));
      const height = Math.max(260, Math.floor(entry.contentRect.height));
      setCanvasSize((current) => (
        current.width === width && current.height === height ? current : { height, width }
      ));
    });
    observer.observe(wrapper);
    return () => observer.disconnect();
  }, [expanded]);

  useEffect(() => {
    if (!expanded) return undefined;
    const appRoot = document.getElementById("root");
    const previousBodyOverflow = document.body.style.overflow;
    appRoot?.setAttribute("inert", "");
    document.body.style.overflow = "hidden";
    dialogRef.current?.querySelector<HTMLButtonElement>(".heatmap-close-button")?.focus();

    const handleDialogKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        shouldRestoreFocusRef.current = true;
        setExpanded(false);
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        ) ?? []
      );
      if (!focusable.length) {
        event.preventDefault();
        dialogRef.current?.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", handleDialogKeyDown);
    return () => {
      window.removeEventListener("keydown", handleDialogKeyDown);
      appRoot?.removeAttribute("inert");
      document.body.style.overflow = previousBodyOverflow;
    };
  }, [expanded]);

  useEffect(() => {
    if (!expanded && shouldRestoreFocusRef.current) {
      shouldRestoreFocusRef.current = false;
      expandButtonRef.current?.focus();
    }
  }, [expanded]);

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeVersion((version) => version + 1));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) {
      return;
    }

    const pixelRatio = window.devicePixelRatio || 1;
    const nextWidth = Math.floor(canvasSize.width * pixelRatio);
    const nextHeight = Math.floor(canvasSize.height * pixelRatio);
    if (canvas.width !== nextWidth) {
      canvas.width = nextWidth;
    }
    if (canvas.height !== nextHeight) {
      canvas.height = nextHeight;
    }
    context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
    drawHeatmap(context, frames, visiblePrices, priceBucket, readHeatmapTheme());
  }, [canvasSize, frames, priceBucket, themeVersion, visiblePrices]);

  function closeExpandedHeatmap() {
    shouldRestoreFocusRef.current = true;
    setExpanded(false);
  }

  const heatmapBody = (
    <>
      <div className="section-heading-row">
        <h2 id={expanded ? "expanded-heatmap-title" : undefined}>Liquidity Heatmap</h2>
        <div className="heatmap-heading-actions">
          <span>{frames.length} frames</span>
          {expanded ? (
            <button
              aria-label="Close expanded liquidity heatmap"
              className="heatmap-close-button"
              onClick={closeExpandedHeatmap}
              type="button"
            >
              Close
            </button>
          ) : (
            <button
              aria-label="Expand liquidity heatmap"
              className="heatmap-expand-button"
              onClick={() => setExpanded(true)}
              ref={expandButtonRef}
              type="button"
            >
              Expand
            </button>
          )}
        </div>
      </div>
      <div className="heatmap-canvas-wrap" ref={wrapperRef}>
        <canvas
          ref={canvasRef}
          className="cockpit-heatmap"
          aria-label="Rolling liquidity heatmap by time frame and price level"
        />
      </div>
      <div className="heatmap-legend">
        <span><i className="legend-swatch low" /> dark = low liquidity</span>
        <span><i className="legend-swatch high" /> bright = high liquidity</span>
        <span><i className="legend-swatch abuser" /> outline = suspect liquidity</span>
      </div>
    </>
  );

  return (
    <>
      {expanded ? <div aria-hidden="true" className="liquidity-heatmap heatmap-placeholder" /> : (
        <section
          className="liquidity-heatmap"
          onDoubleClick={() => setExpanded(true)}
          title="Double-click to enlarge"
        >
          {heatmapBody}
        </section>
      )}
      {expanded ? createPortal(
        <div className="heatmap-dialog-backdrop">
          <section
            aria-labelledby="expanded-heatmap-title"
            aria-modal="true"
            className="liquidity-heatmap expanded"
            onDoubleClick={closeExpandedHeatmap}
            ref={dialogRef}
            role="dialog"
            tabIndex={-1}
          >
            {heatmapBody}
          </section>
        </div>,
        document.body
      ) : null}
    </>
  );
}

function drawHeatmap(
  context: CanvasRenderingContext2D,
  frames: HeatmapFrame[],
  visiblePrices: number[],
  priceBucket: number,
  theme: HeatmapTheme
) {
  const { canvas } = context;
  const pixelRatio = window.devicePixelRatio || 1;
  const width = canvas.width / pixelRatio;
  const height = canvas.height / pixelRatio;
  const plotWidth = width - LEFT_AXIS_WIDTH;
  const plotHeight = height - BOTTOM_AXIS_HEIGHT;

  context.clearRect(0, 0, width, height);
  context.fillStyle = theme.background;
  context.fillRect(0, 0, width, height);

  if (!frames.length || !visiblePrices.length) {
    drawEmptyState(context, theme);
    return;
  }

  const maxDepth = Math.max(
    1,
    ...frames.flatMap((frame) => frame.levels.map((level) => level.bidSize + level.askSize))
  );
  const cellWidth = plotWidth / frames.length;
  const cellHeight = plotHeight / visiblePrices.length;

  drawYAxis(context, visiblePrices, cellHeight, priceBucket, theme);

  frames.forEach((frame, frameIndex) => {
    const levelsByPrice = new Map(frame.levels.map((level) => [level.price, level]));
    visiblePrices.forEach((price, priceIndex) => {
      const level = levelsByPrice.get(price);
      const depth = (level?.bidSize ?? 0) + (level?.askSize ?? 0);
      const intensity = Math.min(depth / maxDepth, 1);
      const x = LEFT_AXIS_WIDTH + frameIndex * cellWidth;
      const y = priceIndex * cellHeight;

      context.fillStyle = getCellColor(level, intensity, theme);
      context.fillRect(x, y, Math.max(1, cellWidth), Math.max(1, cellHeight));

      if ((level?.abuserSize ?? 0) > 0) {
        context.strokeStyle = `rgba(${theme.warningRgb}, 0.95)`;
        context.lineWidth = Math.max(1, Math.min(cellWidth, cellHeight) * 0.14);
        context.strokeRect(x + 0.5, y + 0.5, Math.max(1, cellWidth - 1), Math.max(1, cellHeight - 1));
      }
    });
  });

  drawXAxis(context, frames, plotWidth, plotHeight, theme);
}

function drawYAxis(
  context: CanvasRenderingContext2D,
  visiblePrices: number[],
  cellHeight: number,
  priceBucket: number,
  theme: HeatmapTheme
) {
  context.fillStyle = theme.axis;
  context.font = "11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
  visiblePrices.forEach((price, index) => {
    if (index % 3 !== 0 && index !== visiblePrices.length - 1) {
      return;
    }
    context.fillText(formatHeatmapPrice(price, priceBucket), 4, index * cellHeight + cellHeight / 2 + 4);
  });
}

function drawXAxis(context: CanvasRenderingContext2D, frames: HeatmapFrame[], plotWidth: number, plotHeight: number, theme: HeatmapTheme) {
  context.strokeStyle = theme.grid;
  context.beginPath();
  context.moveTo(LEFT_AXIS_WIDTH, plotHeight + 0.5);
  context.lineTo(LEFT_AXIS_WIDTH + plotWidth, plotHeight + 0.5);
  context.stroke();

  context.fillStyle = theme.axis;
  context.font = "11px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
  context.fillText(formatTick(frames[0]?.tick), LEFT_AXIS_WIDTH, plotHeight + 14);
  context.fillText(formatTick(frames.at(-1)?.tick), LEFT_AXIS_WIDTH + plotWidth - 50, plotHeight + 14);
}

function drawEmptyState(context: CanvasRenderingContext2D, theme: HeatmapTheme) {
  context.fillStyle = theme.axis;
  context.font = "13px Inter, system-ui, sans-serif";
  context.fillText("Waiting for order-book frames", LEFT_AXIS_WIDTH, 34);
}

function getCellColor(level: HeatmapFrame["levels"][number] | undefined, intensity: number, theme: HeatmapTheme) {
  if (!level || intensity <= 0) {
    return theme.lowCell;
  }

  const alpha = 0.18 + intensity * 0.74;
  if (level.askSize > level.bidSize) {
    return `rgba(${theme.dangerRgb}, ${alpha})`;
  }
  if (level.bidSize > level.askSize) {
    return `rgba(${theme.successRgb}, ${alpha})`;
  }
  return `rgba(${theme.infoRgb}, ${alpha})`;
}

function readHeatmapTheme(): HeatmapTheme {
  const styles = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback;

  return {
    axis: read("--chart-axis", "#8fb7c9"),
    background: read("--chart-bg", "#050b12"),
    dangerRgb: read("--danger-rgb", "244, 63, 94"),
    grid: read("--chart-grid", "rgba(148, 163, 184, 0.16)"),
    infoRgb: read("--info-rgb", "34, 211, 238"),
    lowCell: read("--heatmap-low-cell", "rgba(15, 23, 42, 0.72)"),
    successRgb: read("--success-rgb", "16, 185, 129"),
    warningRgb: read("--warning-rgb", "251, 191, 36")
  };
}

function toHeatmapFrames(snapshots: HeatmapSnapshotFrame[], priceBucket: number): HeatmapFrame[] {
  return snapshots.map((snapshot) => {
    const levelsByPrice = new Map<number, HeatmapFrame["levels"][number]>();
    snapshot.book.bids.forEach((level) => mergeLevel(levelsByPrice, level, "bid", priceBucket));
    snapshot.book.asks.forEach((level) => mergeLevel(levelsByPrice, level, "ask", priceBucket));

    return {
      levels: Array.from(levelsByPrice.values()),
      tick: snapshot.tick
    };
  });
}

function mergeLevel(
  levelsByPrice: Map<number, HeatmapFrame["levels"][number]>,
  level: PriceLevel,
  side: "ask" | "bid",
  priceBucket: number
) {
  const price = bucketHeatmapPrice(level.price, priceBucket);
  const existing = levelsByPrice.get(price) ?? { askSize: 0, bidSize: 0, price };

  if (side === "bid") {
    existing.bidSize += level.quantity;
  } else {
    existing.askSize += level.quantity;
  }

  if (isAbuserOwned(level)) {
    existing.abuserSize = (existing.abuserSize ?? 0) + level.quantity;
  }

  levelsByPrice.set(price, existing);
}

function formatTick(tick: number | undefined) {
  return tick === undefined ? "" : `T${tick}`;
}

function isAbuserOwned(level: PriceLevel) {
  return level.owner === "abuser" || level.agent_id?.toLowerCase().includes("abuser");
}
