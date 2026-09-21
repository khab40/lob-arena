# Kernel Authority Rollout

The staged Python/shadow/Java rollout is complete. This document records the final authority policy.

## Final Policy

- Java is the only versioned deterministic-kernel authority.
- Spring Boot owns `POST /api/kernel/run` and `GET /api/kernel/status`.
- Successful run responses identify `X-Kernel-Authority: java` and `X-Kernel-Decision: java`.
- Invalid wire data or deterministic inputs return HTTP 400; requests above 8 MiB return HTTP 413.
- Python authority modes, percentage cohorts, replay, shadow queues, persisted authority decisions, and kernel fallback are retired.
- CI replays all immutable golden-corpus cases against the real Java gRPC service.

The historical rollout controls were intentionally removed after parity and stability gates passed. A rollback deploys a previously verified Java release rather than activating a duplicate Python kernel.
