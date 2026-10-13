# Local CEO release of the existing application

Work: [#90](https://github.com/khab40/lob-arena/issues/90),
[#91](https://github.com/khab40/lob-arena/issues/91),
[Project #3](https://github.com/users/khab40/projects/3).
The [canonical specification](../specs/91-secure-ceo-playback-demo.md) owns acceptance;
[verified saved-score playback](../ml/verified-saved-score-mock.md) owns original
custody, score ordering and frozen detector decisions.

This release preserves the existing UI and backend. The first local topology uses
host Vite and FastAPI with the existing Java kernel and agent runner from the
main Compose stack. Google/session access remains direct loopback. Saved
Transformer/LightGBM predictions appear as a prepared source in Saved Research;
its captured evidence is investigated through the existing Control Panel.
The window has at most 64 original rows and synthetic research labels. Playback
speed is presentation pacing, not model throughput or exchange time. The labelled
`deterministic_fallback` explains captured scores without a market-abuse claim.

Status recorded 12 October 2026: the earlier prepared-page rehearsal passed
Google integration, original-custody playback/capture/save/reopen/export, but did
not preserve the full application's controllers and backend. It is historical
proof, not acceptance of this full-product release. Recovery retained the three
original publications and removed the temporary exact-key permission with
independent policy readback. Full-stack rehearsal, the immutable tag, independent
review and fresh-head CI must identify the corrected release before acceptance.
Shared/container deployment, full #90/#91 acceptance and #24 MLflow closure remain
open. This runbook grants no new data access, model workload, remote LLM call,
cloud deployment, spend, merge or deletion authorization.

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

Use the existing `feat/ceo-playback-demo-20261012` task branch and PR #380.
After the final reviewed commit passes its checks, bind an immutable release tag
to that exact commit. The public configuration example's tag is a proposed name;
a tag or image name alone does not establish verified source or build identity.
Record the commit/tag, configuration hash and actual image IDs in private evidence.

Copy [ceo-local.env.example](../../deployments/modes/ceo-local.env.example) to a
new owned release env file outside Git, replacing its runtime path and tag with
verified values. Resolve the current host user's numeric identity with
`rtk proxy id -u` and `rtk proxy id -g`; set `CEO_RELEASE_UID` and
`CEO_RELEASE_GID` to those decimal values. Java uses this explicit identity rather
than the image's default user. It contains no Google credentials or custody settings. Create
its dedicated runtime directory with mode `0700`, disjoint from retained custody
and private authentication state. Both Java and host FastAPI use this directory;
backend retention applies only there. Resolve existing host listeners on ports
8000/5173 before switching to the reviewed release; preserve retained state.

Before rendering or starting the release, replace these placeholders with the
same directory and numeric values recorded in the release env file. This read-only
preflight refuses a relative/symlinked directory, a different owner or mode other
than `0700`. Stop on failure; do not loosen permissions or change private custody
or authentication-state ownership to make the sidecar work.

```sh
rtk proxy python3 - /absolute/project/outputs/ceo-release-runtime REPLACE_WITH_ID_U REPLACE_WITH_ID_G <<'PY'
import os, pathlib, stat, sys
path = pathlib.Path(sys.argv[1])
uid, gid = sys.argv[2:4]
assert uid.isascii() and uid.isdecimal() and gid.isascii() and gid.isdecimal(), "Numeric UID/GID required"
assert (int(uid), int(gid)) == (os.getuid(), os.getgid()), "Host identity mismatch"
assert path.is_absolute() and path.resolve(strict=True) == path, "Absolute nonsymlinked directory required"
info = path.lstat()
assert stat.S_ISDIR(info.st_mode), "Runtime directory required"
assert (info.st_uid, info.st_gid) == (int(uid), int(gid)), "Runtime owner mismatch"
assert stat.S_IMODE(info.st_mode) == 0o700, "Runtime mode must be 0700"
print("Runtime owner and mode preflight PASS")
PY
```

From the checkout root, merge the maintained
[local release override](../../deployments/docker-compose.ceo-local.yml) with the
existing full-stack Compose file. After independent review and applicable build/run
approval, use:

```sh
rtk proxy docker compose --env-file /absolute/project/outputs/ceo-release/release.env \
  -p lob-arena-ceo-local -f docker-compose.yml -f deployments/docker-compose.ceo-local.yml \
  config --quiet
rtk proxy docker compose --env-file /absolute/project/outputs/ceo-release/release.env \
  -p lob-arena-ceo-local -f docker-compose.yml -f deployments/docker-compose.ceo-local.yml \
  build java-kernel agent-runner
rtk proxy docker compose --env-file /absolute/project/outputs/ceo-release/release.env \
  -p lob-arena-ceo-local -f docker-compose.yml -f deployments/docker-compose.ceo-local.yml \
  up -d --no-build java-kernel agent-runner
```

This starts Java REST on `127.0.0.1:8082` and agent health on `127.0.0.1:9101`.
Java reaches its agent through the internal Compose network. gRPC is unpublished;
heavy and LangGraph agents are disabled. The existing backend/frontend container
image definitions remain in `container-app-gated`; do not enable that profile.
Docker peers do not satisfy direct-loopback authentication. All-container/shared
HTTPS operation requires a separately reviewed origin, ingress and transport package.

From the same checkout's `backend/`, reuse the private Google env file. Set
`ARENA_OUTPUT_DIR` to the exact runtime directory in the release env file; the
explicit child settings below take effect after the private env file is loaded:

```sh
rtk proxy uv run --locked --env-file /absolute/project/outputs/ceo-demo-private/local.env \
  env JAVA_ARENA_BASE_URL=http://127.0.0.1:8082 \
  ARENA_REMOTE_AGENT_URLS=http://127.0.0.1:9101 \
  ARENA_OUTPUT_DIR=/absolute/project/outputs/ceo-release-runtime \
  NEBIUS_SERVERLESS_ENABLED=false NEBIUS_ENDPOINT_MODE=mock \
  uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

From its `frontend/` in another terminal, reuse the existing Vite application:

```sh
rtk proxy env VITE_CEO_DEMO=true pnpm exec vite --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://localhost:5173/arena`. Google protects the existing route table and
controllers; saved evidence is an additional source, not a replacement cockpit.
Java REST and `/ws/arena` pass through FastAPI's session boundary. Cloud controls
keep their configured unavailable state and execution gates. The frontend uses
same-origin proxy transport; retain the reviewed proxy guard and port 5173.
Do not substitute the historical partial VM deploy helper: it omits Java kernel.

For inert browser verification, `pnpm run test:e2e` from `frontend/` starts separate
strict-port fixture servers: ordinary Arena on 4173 with demo mode disabled and
the prepared demo on 4174 with it enabled. It refuses existing server reuse.
These tests use mocked evidence and identities; they neither score a model nor
replace the original-custody Google rehearsal.

For an authorized rehearsal:

1. Record the reviewed source/build identity, configured local origin and private
   receipt directory. Complete Google sign-in with an approved identity; confirm
   the workspace remains authorized through session polling and a page reload.
2. Check the existing Arena, Data Ingestion, Scenario Generator and Control Panel
   remain usable under their configuration contracts. Open the prepared source in
   Saved Research; check saved-prediction and synthetic-label notices, playback
   controls and each supported detector.
   Confirm the fixed paired window remains available without a model run.
3. Select an original threshold alert and capture it. Record the opaque snapshot
   ID and `snapshot_sha256`; playback or detector changes must not change it.
4. Open the existing Control Panel Investigation Team section with the captured
   saved-anomaly input. Request explanation. Confirm `deterministic_fallback` and
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
