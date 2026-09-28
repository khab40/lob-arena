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

## Verified drill

The [September 28 receipt](../evidence/mlflow-metadata-recovery-20260928.json)
records **60 tables / 19,521 rows** restored and matched, including three
application users. The 380,475-byte private dump was copied to root
`outputs/platform-maintenance-20260927/recovery-20260928/metadata.dump` and its
SHA-256 rechecked; directory/file permissions are 0700/0600. The VM-side copy is
retained at `/opt/aimada/mlflow/recovery-20260928/metadata.dump`.

The restore used the existing PostgreSQL image ID, not a downloaded replacement.
Its temporary container was stopped and removed automatically; independent
Docker readback found no restore container. Nebius MCP readback confirmed the VM
STOPPED at resource version 104. No permissions or final credentials changed.
The deployed MLflow runtime is **3.13.0**; repository image pin changes, including
PR #203, are not evidence of a live upgrade.

The database has one registered-model namespace, **zero versions and zero
aliases**. Registration therefore remains outstanding. This drill verifies table
data, not sequence advancement or successful application writes after recovery.

To repeat during an authorized maintenance window, run on the VM:

```sh
python3 scripts/mlflow_metadata_recovery.py \
  --source-container lob-arena-mlflow-nebius-mlflow-postgres-1 \
  --output /absolute/new-private-backup-directory
```

Use a new output directory; existing backups are never overwritten. Only publish
the sanitized verification JSON. Keep the private dump outside Git and retain it
until an explicit backup disposition. Restoration into the live database is a
separate operation; this command has no live-restore mode.
