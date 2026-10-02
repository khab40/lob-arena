# MLflow service-health and diagnostic repair — 2026-10-02

As a platform operator,
I want verified service health and safe preflight diagnostics,
So that readiness cannot start from process state alone and failures are actionable.

Actor: platform operator. Goal: establish healthy-service prerequisites before
application verification. Value: bounded, diagnosable maintenance without exposing
credentials. Ticket: [Bug #282](https://github.com/khab40/lob-arena/issues/282),
under [Story #19](https://github.com/khab40/lob-arena/issues/19) in
[Project #3](https://github.com/users/khab40/projects/3).

## Observed failure

[PR #279](https://github.com/khab40/lob-arena/pull/279) merged; both merge workflows
passed. The authorized r2 attempt reached SSH, sudo, Docker and both Running
container states after 78.234 seconds of guest polling. It staged the package,
then failed after 0.823 seconds in the initial read-only checks. Only the window
intent was retained. The exact users/defaults/runtime subcheck is unknown;
container health was not recorded, so a health-related cause is not proven.

The [r2 receipt](../evidence/mlflow-readiness-r2-attempt-20261002.json) records
zero restore/live execution, grants, registry writes, probe runs, artifact
transfers and temporary containers. Watchdog shutdown and independent Nebius MCP
confirmed STOPPED at version 112, 215.514 seconds after the start request.

## Acceptance

```gherkin
Feature: Healthy and diagnosable MLflow maintenance

  Scenario: Wait for actual service readiness
    Given the existing database and application containers are running
    And either existing healthcheck is starting or unhealthy
    When guest readiness polls
    Then application verification remains blocked
    And normalized health observations are retained

  Scenario: Reject missing health configuration
    Given either existing service has no healthcheck
    When guest readiness inspects it
    Then it stops before application verification

  Scenario: Retain a safe failed-check receipt
    Given an initial SQL, defaults or runtime preflight check fails
    When the wrapper stops
    Then it records the phase and safe failure classification
    And it does not retain raw subprocess output or exception messages

  Scenario: Preserve the shutdown reserve
    Given healthy services do not appear within the guest deadline
    When readiness reaches its time or remaining-window limit
    Then application verification does not start
    And the already-armed watchdog stops the VM
```

## Timing choices and authorization

These numbers are engineering choices, not Nebius platform requirements:

- The agent originally proposed the 600-second shutdown target; the operator
  approved it in PR #279. It is neither a measured completion requirement nor
  a provider billing cap.
- The 435-second reserve is 370 seconds of execution transport, 40 independent
  readback, 20 evidence collection and 5 stop signaling, as recorded in PR #279.
- The agent selected a 120-second guest-polling maximum for this repair. The
  absolute deadline still requires 435 seconds remaining, so slow starts can
  shorten that allowance. This has not yet been measured on the VM.
- The operator explicitly approved retries without giving a count. The agent
  selected at most one additional start after r2; that count is not an
  operator-imposed requirement. Existing mutation/resource limits remain.

The previous failure was not the 600-second deadline. This repair adds the
missing health gate and diagnostics; increasing a timeout alone is not a diagnosis.
Initial read-only failures may be retried within authorization; ambiguous live
mutations must first be reconciled without creating duplicates.

Verification: 234 focused inert tests pass, including 11 new health/diagnostic
cases, with no local model execution. Actual healthy-service evidence and MLflow
readiness remain pending the bounded retry. Out of scope: new permissions beyond
the original four grants, deployment upgrade, model Jobs, final access and merge.
