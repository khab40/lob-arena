# MLflow metadata recovery — 2026-09-28

Existing story: [#19](https://github.com/khab40/lob-arena/issues/19), under
platform feature #14 in Project #3. G8 and the signed G9 research-baseline exit
remain closed.

As a platform operator,
I want to restore a retained MLflow metadata backup into an isolated database,
So that I can verify recovery without replacing the live tracking database.

Actor: platform operator. Goal: reproducible metadata recovery evidence.
Value: preserve run lineage, registry records and application permissions.
Out of scope: live database replacement, version upgrade, model execution,
production promotion, final-test access, and S3 artifact duplication.
Verification: inert tests plus a bounded restore on the existing Nebius CPU VM.

```gherkin
Feature: Recover shared MLflow metadata
  Scenario: Restore a consistent retained backup
    Given the existing PostgreSQL metadata database
    When an exported read-only snapshot is backed up and restored in isolation
    Then every public table has the same row count and content digest
    And the retained backup has a recorded checksum
    And the production database is not a restore target
  Scenario: Reject incomplete restoration
    Given a damaged backup or a different restored table
    When recovery is verified
    Then no successful verification receipt is produced
```

Implementation sequence:

1. Export one read-only PostgreSQL snapshot and retain a custom-format dump.
2. Restore into a fresh network-isolated PostgreSQL container using the exact
   source image. Fail on the first restore error, in a single transaction.
3. Compare the table inventory and SHA-256 of canonical row streams, including
   MLflow authentication tables. Retain only counts/digests in public evidence.
4. Copy the private dump to durable root `outputs/`, verify its checksum, and
   stop the VM. Never commit dumps or database credentials.

Execution bounds: one existing `cpu-e2/2vcpu-8gb` VM, at most 600 seconds before
the independent stop watchdog acts; zero Jobs and zero GPUs. Restore container:
one CPU, 1 GiB RAM, 512 MiB temporary database, no network or published ports.
Backup cap: 1 GiB on existing disk; no storage expansion. Incremental compute
exposure is at most the planned 1/6 VM-hour plus stop latency; costs remain under
the existing operator-managed policy, with no invented dollar estimate. SSH uses
the existing operator /32 rule. No new permission or credential activation.

PostgreSQL's [backup documentation](https://www.postgresql.org/docs/16/backup-dump.html)
describes consistent dumps; [pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html)
documents transactional restoration. This is a database-level recovery drill:
SQL roles/ACLs are recreated through deployment configuration, while application
users/permissions are retained as table data. Object Storage remains independently
verified by the accepted G9 package; this drill does not prove S3 disaster recovery.

Remaining #19 acceptance after this chunk: register the frozen candidate with
verified lineage and an auditable research-only alias; prove application-level
readback against restored metadata; carry the tracking contract through later
Transformer/hybrid runs. No champion or production alias is authorized here.
