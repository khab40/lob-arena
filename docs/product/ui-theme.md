# UI Theme

## Concept

The LOB Arena UI uses a Nebius Cloud-inspired AI console theme without copying Nebius CSS, logo files, or proprietary assets. The design goal is a compact enterprise console: dark left navigation, clean command-center workspace, status cards, health pills, and a violet primary accent for AI/serverless actions.

## Theme Modes

- Light mode uses a near-white workspace, white cards, light blue-gray borders, dark navy text, and a dark graphite/navy sidebar.
- Dark mode uses a deep navy workspace, dark navy cards, muted blue borders, light text, and the same very dark sidebar.
- System mode keeps the existing behavior and follows `prefers-color-scheme`; the resolved mode is applied through `document.documentElement.dataset.theme`.

## Core Tokens

The main tokens live in `frontend/src/App.css`:

- `--color-bg`
- `--color-bg-muted`
- `--color-surface`
- `--color-surface-elevated`
- `--color-border`
- `--color-border-strong`
- `--color-text`
- `--color-text-muted`
- `--color-text-soft`
- `--color-primary`
- `--color-primary-hover`
- `--color-primary-soft`
- `--color-success`
- `--color-warning`
- `--color-danger`
- `--color-sidebar-bg`
- `--color-sidebar-text`
- `--color-sidebar-muted`
- `--color-sidebar-active-bg`
- `--color-sidebar-active-text`
- `--shadow-card`
- `--radius-sm`
- `--radius-md`
- `--radius-lg`
- `--layout-sidebar-width`
- `--layout-topbar-height`

Existing legacy variables such as `--panel-bg`, `--accent`, and `--widget-bg` map onto these tokens so older components inherit the console theme without a rewrite.

## Not Copied From Nebius

This theme does not import external Nebius stylesheets, does not copy Nebius logo assets, and does not reuse proprietary Nebius class names or CSS. The sidebar wordmark, status cards, topbar, and violet accent palette are LOB Arena-owned styling built with local CSS variables.

## Quick Demo Adjustments

Before a demo, the fastest color changes are:

1. Adjust `--color-primary`, `--color-primary-hover`, and `--color-primary-soft` for accent color.
2. Adjust `--color-sidebar-bg` for the navigation tone.
3. Adjust `--color-bg`, `--color-surface`, and `--color-surface-elevated` for workspace contrast.
4. Keep `--color-border` and `--shadow-card` subtle to preserve the cloud-console feel.
