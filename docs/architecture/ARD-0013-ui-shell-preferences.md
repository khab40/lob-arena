# ARD-0013: UI Shell Preferences And Demo Presentation

Status: Accepted

Date: 2026-06-24

## Implementation Status

Status as of 2026-06-24: `[done]`

Implemented:

- README/GitHub banner switched to `assets/img/ai-mada.jpg`.
- Stale UI subtitle text removed from the product shell.
- Compact vertical navigation collapse/expand control sized closer to browser vertical-tab controls.
- Day/night/system theme preference with `lob-arena.themePreference`, document `data-theme`, and system-mode `prefers-color-scheme` handling.
- Light-theme and dark-theme surface, border, text, chart, status, bid/ask, warning, danger, success, and accent tokens for shared widgets.
- Theme-aware Recharts timeline colors, tooltips, and axes.
- Theme-aware Liquidity Map canvas background, axis labels, grid line, low-liquidity cells, and bid/ask/abuser colors.
- Liquidity Map/timeline frame updates gated by arena tick progression so paused or not-started state remains visually stable.

Before final submission:

- Final screenshot set under `assets/screenshots/`.

Future work:

- Dedicated accessibility contrast audit for the final visual palette.

## Context

The arena is used for live demos, screenshots, and technical review. Oversized navigation controls, stale branding text, and visuals that keep moving while the simulation is stopped make the product feel less controlled than the backend runtime actually is.

The UI shell needs professional presentation behavior without moving simulation responsibility into the browser.

## Decision

Treat display and chrome state as local UI shell preferences.

The shell supports three theme modes and applies the same semantic tokens to panels, controls, status chips, charts, order-book levels, and canvas visualizations:

- `system`: follow the operating system color-scheme preference.
- `light`: force day mode.
- `dark`: force night mode.

The shell persists those choices in local storage and applies the resolved mode through `data-theme`. Navigation collapse controls are compact icon-style controls. Timeline-like widgets append frames only when backend tick values advance.

## Architecture

```mermaid
graph TD
    Browser["Browser Local State"]
    Theme["lob-arena.themePreference"]
    Shell["React Shell"]
    Backend["Java Spring live arena"]
    Arena["Arena State Stream"]
    Visuals["Stable Timeline Widgets"]

    Browser --> Theme
    Theme --> Shell
    Backend --> Arena
    Arena --> Visuals
    Shell --> Visuals
```

## Consequences

Positive:

- Demo operators can pick a theme without changing backend state.
- Screenshots and recordings can use a cleaner, more stable presentation.
- Paused arena state visually matches backend runtime state.

Tradeoffs:

- More CSS tokens must be maintained across dark and light modes.
- Chart-specific light-mode tuning may still be needed after real screenshot capture.
- Local browser preferences are intentionally per-browser, not synchronized user profile settings.

## Related Documentation

- `README.md`
- `docs/product/DESIGN-IDEAS.md`
- `docs/roadmap/PHASES.md`
- `docs/runtime/runtime-model.md`
- [ARD-0001: Overall Architecture](ARD-0001-overall-architecture.md)
