# Local CEO saved-prediction demo

Work: [#90](https://github.com/khab40/lob-arena/issues/90),
[#91](https://github.com/khab40/lob-arena/issues/91),
[Project #3](https://github.com/users/khab40/projects/3).
The [canonical specification](../specs/91-secure-ceo-playback-demo.md) owns acceptance;
[verified saved-score playback](../ml/verified-saved-score-mock.md) owns original
custody, score ordering and frozen detector decisions.

This procedure starts only the local backend and frontend. It presents saved
Transformer/LightGBM research predictions and synthetic labels from one verified
campaign. The prepared window has at most 64 original rows and up to 16 preceding
context rows. Playback speed is presentation pacing, not inference throughput or
exchange time. Explanation uses the labelled `deterministic_fallback`, grounded
in the captured scores and labels; it makes no adjudicated market-abuse claim.

Status recorded 12 October 2026: actual Google integration and the original-custody
end-to-end rehearsal are
pending. Inert tests, mocked browser tests, lint and build pass; they do not prove
those integration checks. CI/publication, deployment, full #90/#91 acceptance and
#24 MLflow closure remain incomplete. The first original-data S3 HEAD failure has
no established cause. This runbook grants no new data access, remote LLM call,
model workload, cloud deployment, spend, merge or deletion authorization.

Use the reviewed source and installed locked backend/frontend dependencies.
Keep the existing Google web client and approved identities; this procedure does
not create an OAuth client or change access policy. Google's
[setup guide](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
specifies both `http://localhost` and the port-specific origin for local testing.
This package uses `http://localhost:5173`; the existing client's authorized
JavaScript origins, configured application origin and opened URL must agree.
Do not mix `localhost` and `127.0.0.1` origins. Local mode still requires Google
sign-in and backend application sessions. Use direct loopback access without a tunnel,
forwarding headers or a shared proxy. Shared deployment requires a separate
reviewed HTTPS execution package.

Choose absolute, nonsymlinked paths outside the worktree. Original custody must
already be approved and retain its frozen `verification.json`, `result.json`,
`predictions.json`, `target-ledger.json` and `receipts/`; do not copy it into a
frontend fixture or alter historical receipts. The loader checks maintained pins
before returning rows and rechecks custody before reads and capture.

Keep custody, the generic runtime output directory, private state and
`assets/screenshots` disjoint: none may contain another. The default generic
`../outputs` can overlap root custody, so override it explicitly. Create a new
owned private directory and state directory with mode `0700`; their parent paths
must already exist. The backend writes its owned `0600` session database and
journey artifacts there. Retain that state across backend restarts and outside
disposable worktrees. Historical custody permissions must remain unchanged.

Create a new private `0600` env file outside Git, for example at
`/absolute/project/outputs/ceo-demo-private/local.env`. Replace every placeholder
below before use. The client ID is the existing web client's public identifier;
no OAuth client secret is needed for ID-token verification. Do not put identity
values, tokens, cookies, the state database or custody contents in public logs.

```dotenv
CEO_DEMO_ENABLED=true
CEO_DEMO_LOCAL=true
CEO_DEMO_ORIGIN=http://localhost:5173
GOOGLE_CLIENT_ID=REPLACE_WITH_EXISTING_WEB_CLIENT_ID
CEO_DEMO_ALLOWED_EMAILS=REPLACE_WITH_APPROVED_EMAIL_LIST
CEO_DEMO_STATE_DIR=/absolute/project/outputs/ceo-demo-private/state
CEO_DEMO_SESSION_SECONDS=1800
RESEARCH_SAVED_SCORES_DIR=/absolute/project/outputs/approved-saved-scores
ARENA_OUTPUT_DIR=/absolute/project/outputs/ceo-demo-runtime
NEBIUS_ENDPOINT_MODE=mock
```

The allowlist is comma-separated. Application session lifetime defaults to 1800
seconds and accepts 60–3600 seconds; it cannot outlive the verified Google token.
`RESEARCH_SAVED_SCORES_ENABLED` is not needed for the protected CEO journey.
Missing Google configuration or unsafe private state keeps sign-in unavailable;
missing or invalid custody keeps the campaign unavailable. Neither condition
grants a fallback session or exposes fixture predictions.

From the reviewed checkout's `backend/` directory:

```sh
rtk proxy uv run --locked --env-file /absolute/project/outputs/ceo-demo-private/local.env \
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

From its `frontend/` directory in a second terminal:

```sh
rtk proxy env VITE_CEO_DEMO=true pnpm exec vite --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://localhost:5173/ceo-demo`. The new auth and journey requests use the
same-origin Vite proxy to the loopback backend; `VITE_API_BASE_URL` does not select
their destination. Keep port 5173 fixed: another port will not satisfy the
configured origin. The separate legacy `/research-predictions` guide and mocked
browser test server on port 4173 are not the Google demo startup procedure.

For an authorized rehearsal:

1. Record the reviewed source/build identity, configured local origin and private
   receipt directory. Complete Google sign-in with an approved identity; confirm
   the workspace remains authorized through session polling and a page reload.
2. Open the prepared campaign. Check saved research prediction and synthetic
   label notices; play/pause, change speed and select each supported detector.
   Confirm the fixed paired window remains available without a model run.
3. Select an original threshold alert and capture it. Record the opaque snapshot
   ID and `snapshot_sha256`; playback or detector changes must not change it.
4. Request explanation. Confirm the visible mode is `deterministic_fallback` and
   its retained input is the captured snapshot. Record `explanation_sha256`.
5. Save the complete result. Reopen it from the saved list, export JSON and check
   its `record_sha256`, snapshot and explanation match the saved response. The
   UI must report save success only after verified durable readback.
6. Log out. Confirm the workspace disappears and subsequent session/protected
   requests are denied. A session that reaches its configured expiry must also
   lose access; account replacement must discard the previous account's journey.
7. Retain a private receipt linking source/build, actual mode, opaque IDs, hashes
   and outcomes, together with the verified saved bundle. Keep credential and
   private payload bytes out of public evidence. Mark failed or skipped steps
   explicitly; do not report full acceptance from mocked checks.

An unavailable campaign needs inspection of the approved custody and exact
verification receipts; it is not permission to download replacement data or run
a model. Fixed safe errors may also indicate a refused write or storage budget:
journey files are bounded to 256 KiB each, at most 1000 retained files including
partials, and 256 MiB total. Preserve failed partials and durable state for
review; cleanup or replacement requires its applicable authorization.
