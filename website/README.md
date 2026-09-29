# LOB Arena public website

Six static pages: Home, Arena Demo, Research, Architecture, Detectors/ML and
About/Docs. Approved scope: [Story #253](https://github.com/khab40/lob-arena/issues/253)
under [Feature #252](https://github.com/khab40/lob-arena/issues/252), Epic #15,
[Project #3](https://github.com/users/khab40/projects/3).

This public introduction is separate from the secure, backend-driven CEO UI in
#91. It does not bypass that story's evidence or authentication gates.

## Run and verify

Use Node 24+ and pnpm 10.30.3. From the repository root:

```sh
cd website
pnpm install --frozen-lockfile
pnpm dev
# Open http://127.0.0.1:5173/lob-arena/
pnpm test
pnpm lint
pnpm build
pnpm exec playwright install chromium
pnpm test:e2e
pnpm preview
```

The browser suite serves the built output at port 4187 and checks desktop and
mobile routes, refresh, history, missing routes, replay controls, keyboard
operation, offline replay and absence of external/API/WebSocket requests.
Screenshots and failure traces are written to ignored `test-results/`.

## Static deployment

Vite's base is `/lob-arena/`. React Router's `HashRouter` keeps page navigation in
the URL fragment, so refreshed links such as `/lob-arena/#/research` need no
server rewrite or custom 404 fallback. Assets and favicon use the same base.
See the [router contract](https://reactrouter.com/api/declarative-routers/HashRouter).

`.github/workflows/website.yml` validates PRs without deployment privileges.
Only validated `main` pushes or manual runs on `main` can deploy the built
`website/dist` artifact. No source tree, private output or backend is published.

One-time operator setup after review:

1. In repository Settings → Pages, select **GitHub Actions** as the source.
2. Restrict the `github-pages` environment to `main`; add a required reviewer if
   deployments need a separate approval after merge.
3. Merge the reviewed PR only after approval. The workflow then publishes to
   `https://khab40.github.io/lob-arena/`. If Pages was enabled later, run the
   Public website workflow manually on `main`.
4. Check the deployment URL and refresh `/lob-arena/#/demo` and `#/research`.

No Pages settings were changed by this implementation. A 404 from the Pages
API at implementation time meant no configured site was visible to the caller.
See [GitHub's Pages workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
Revert a website change through a reviewed PR and deploy the resulting `main`
to roll back; never upload operational frontend or experiment artifacts.

## Dependency and design reuse

React 19, TypeScript, Vite 8, React Router 8, TailwindCSS 3.4, Recharts and pnpm
match the existing frontend. The website has its own build and installed modules.
It imports no frontend runtime, API clients, cloud SDKs or environment config.

`pnpm-lock.yaml` is a relative symlink to the existing frontend lock. Both app
manifests intentionally declare identical dependency versions and overrides;
the contract test rejects drift. This shares the reviewed dependency graph
without modifying `/frontend` or duplicating its large generated lockfile.
Run frozen installs here; do not run `pnpm add/update` in this directory because
the lock is shared. For a future website-only dependency, first split the lock
in a dedicated, reviewed dependency change. Full-repository checkout on a
symlink-capable filesystem is required (GitHub Actions Linux supports this).
Changes to either shared dependency file trigger website CI.

`src/tokens.css` snapshots the existing frontend's navy/purple dark theme.
`TeamMark.tsx` is a local copy of its pure icon component. Provenance is revision
`b3724b8`; all other components are website-local to avoid coupling the operator
application to public presentation work. `/frontend` is unchanged.

## Content and data boundaries

- `src/data/replay.ts`: hand-authored synthetic price/depth/event sequences and
  scripted flags. No licensed payloads, model training, inference or scores.
- `src/data/research.ts`: dated, immutable source links and verified research
  metrics. LightGBM is `research_baseline_qualified`, Transformer is in readiness
  and input verification before GPU training, near-real-time detection is a
  target direction. The website is not a live status feed.
- Metrics describe 15,160 retained observations, one date, three symbols and
  research labels. They are unrelated to the illustrative website replay.
- No analytics, remote fonts, backend/API/Nebius calls, WebSocket or credentials.
  External navigation is limited to explicit repository/documentation links.

To refresh content, inspect the latest evidence and disposition, update the
snapshot commit/date and claims together, then rerun all checks. Do not convert
roadmap targets into completed capability claims.
