# LOB Arena Publication Image Plan

## Decision

Do **not** create the GitHub social preview from fabricated UI content. The
repository has a branded README hero and four committed sanitized application
screenshots. The current captures prove the product workflow, but dedicated
Nebius console log/metric captures and canonical publication-sized exports are
still needed before building the requested product composite.

## Verified publication assets

| Asset | Current use | Status | Action |
|---|---|---|---|
| `assets/img/ai-mada.jpg` | README hero | Usable as the README banner only | Keep separate from the GitHub social preview. Re-export with metadata stripped and visually compare before replacing the current file. |
| `assets/screenshots/Screenshot 2026-07-14 at 17.41.43.png` and three companion captures | README runtime, Investigation Team, detector tournament and execution-trace evidence | Four sanitized application screenshots committed | Preserve as evidence; create canonical named/cropped exports below and add dedicated Nebius console log/metric captures. |
| README Mermaid architecture diagram | In-page architecture explanation | Technically useful but not a cover image | Export a clean 16:9 raster copy for the LinkedIn article. |
| `assets/demo-video/` narration/caption files | Video planning | Not image material | Do not use as article or social artwork. |

The current README hero is a wide JPEG and is not the required 2:1 GitHub social-preview composition. It also does not provide the strongest proof of the working product. Keep it as the README hero unless a visually superior optimized export is prepared.

## GitHub social preview

### Required output

`assets/social/aimada-github-social-preview.png`

- Canvas: **1280 × 640 px**
- Format: PNG
- Maximum size: **1 MB**
- Background: dark graphite/navy matching LOB Arena dark mode
- Safe area: keep important text and panels at least 48 px from every edge

### Composition

- Left 58–62%: real live Arena capture showing the order-book or liquidity visualization.
- Right 38–42%: real detector incident, Investigation Team, or tournament result panel.
- Top-left title: **LOB Arena**.
- Subtitle: **LOB Arena**.
- Bottom supporting line: **Built with Nebius Serverless AI Jobs + Endpoints**.
- Use only one or two real product captures. Do not create a dense multi-screen collage.

### Required manual captures before composition

1. `assets/screenshots/aimada-live-arena.png`
2. One of:
   - `assets/screenshots/aimada-investigation-team.png`
   - `assets/screenshots/aimada-detector-tournament.png`

Until these exist, keep only the capture specification in `assets/social/README.md`; do not create a placeholder PNG that looks like a real product screenshot.

## LinkedIn technical article image plan

| Image | Planned file path | Required dimensions | Exact UI state to capture | Must be visible | Hide or redact | Article placement | Caption | Alt text |
|---|---|---:|---|---|---|---|---|---|
| Cover image | `assets/social/aimada-linkedin-cover.png` | 1200 × 675 | Dark-mode LOB Arena Command Center with a live synthetic market and one active incident/investigation panel | LOB Arena title, order-book/liquidity view, detector or investigation result, restrained Nebius Serverless line | Browser address bar, local/private URLs, tokens, account controls, tenant/project IDs | Article cover | LOB Arena combines a synthetic order-book arena with Nebius Serverless AI investigation and batch evaluation. | LOB Arena dashboard showing a synthetic order book and an AI-assisted incident investigation. |
| Architecture diagram | `assets/screenshots/aimada-architecture.png` | 1600 × 900 | Render the current architecture with Front, Back, Agents Workspace, Endpoint, Jobs, artifacts, and S3 evidence flow | React/Vite, FastAPI, authoritative runtime, deterministic detectors, agent-runner, Endpoint, Jobs, Object Storage/evidence | Environment-variable values, internal hostnames, credentials | After “The architecture has two main paths” | LOB Arena separates interactive Endpoint workflows from repeatable Serverless Job evaluation and durable evidence storage. | Architecture diagram linking the LOB Arena frontend, backend, agents, Nebius Endpoint, Serverless Jobs, and evidence storage. |
| Live Arena | `assets/screenshots/aimada-live-arena.png` | 1600 × 900 | Workload Generator or Command Center in dark mode after normal liquidity has formed and a bounded spoofing-like or layering-like scenario is active | Order-book ladder, price/spread or liquidity visualization, scenario status, detector confidence or incident indicator | Browser chrome, unrelated tabs, user identity, private URLs | After the synthetic-market explanation | A bounded synthetic scenario running inside LOB Arena’s live limit-order-book arena. | Live LOB Arena market simulation with order-book depth, liquidity visualization, and a synthetic scenario. |
| AI Investigation Team | `assets/screenshots/aimada-investigation-team.png` | 1600 × 900 | Completed real Nebius-backed investigation for a selected incident | `Nebius`/real mode indicator, specialist findings, consensus, evidence timeline, recommended action, latency if displayed | Endpoint hostname, bearer token, tenant/project IDs, personal information | After the detect-versus-explain section | Deterministic detectors create the evidence first; the Nebius-hosted AI Endpoint turns it into a reviewer-oriented investigation. | LOB Arena Investigation Team view showing structured findings, evidence timeline, consensus, and review actions. |
| Detector Tournament / benchmark | `assets/screenshots/aimada-detector-tournament.png` | 1600 × 900 | Completed real or representative tournament with leaderboard and artifact links visible | Serverless Jobs label, completed status, detector names, scenario count, precision/recall/F1, latency, report/artifact links | Full Job IDs if sensitive, private S3 URLs, credentials | In “Results and reproducibility” | Nebius Serverless AI Jobs run repeatable detector tournaments and persist metrics, reports, and artifacts. | Completed LOB Arena detector tournament showing a leaderboard, evaluation metrics, and downloadable artifacts. |
| Production evidence and S3 sync | `assets/screenshots/aimada-production-evidence-sync.png` | 1600 × 900 | Execution Trace or Evidence UI after a successful S3 synchronization | Completed Endpoint and Job evidence records, S3 upload/sync status, safe artifact download links | Bucket name if private, access keys, signed URLs, endpoint hostname, tenant/project IDs, local usernames | After the production-evidence paragraph or near the results section | Production Job and Endpoint evidence is archived to Object Storage, synchronized to the backend, and exposed for review in the UI. | LOB Arena evidence interface showing completed Nebius records, S3 synchronization status, and downloadable artifacts. |

## Capture procedure

1. Use a 1920 × 1080 browser window at 100% zoom.
2. Select dark mode and collapse nonessential navigation where possible.
3. Preload the deterministic scenario, representative completed Job, Endpoint investigation, and evidence records.
4. Capture PNG screenshots without browser chrome when possible.
5. Crop rather than scale text-heavy screens below readable size.
6. Strip EXIF, XMP, ICC comments, and editor metadata from publication copies.
7. Recheck every image at 50% zoom; all labels central to the argument must remain legible.
8. Run secret scanning and a manual visual review before publication.

## README policy

- Keep `assets/img/ai-mada.jpg` as the README hero until a better optimized hero is available.
- Keep the social preview in `assets/social/`; do not reuse it automatically as the README banner.
- Do not add a README screenshot gallery until at least the Live Arena, Investigation Team, and Detector Tournament screenshots are real, redacted, and committed.
- Once those three images exist, add a compact three-image gallery rather than a long wall of screenshots.

## Validation checklist

- [ ] Social preview is exactly 1280 × 640 px.
- [ ] Social preview is under 1 MB.
- [ ] LinkedIn cover is 1200 × 675 px.
- [ ] Article screenshots are 1600 × 900 px or a consistent equivalent.
- [ ] Images contain no access keys, tokens, signed URLs, private hosts, tenant IDs, project IDs, email addresses, or local usernames.
- [ ] Metadata is stripped from publication exports.
- [ ] Text remains readable at typical GitHub and LinkedIn display sizes.
- [ ] Every screenshot represents a real application state.
- [ ] README gallery is added only after real captures exist.
