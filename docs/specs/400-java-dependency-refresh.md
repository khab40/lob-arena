# Compatible Java dependency refresh

Ticket: [Bug #400](https://github.com/khab40/lob-arena/issues/400), child of
[Story #38](https://github.com/khab40/lob-arena/issues/38), Project #3.
Existing dependency PR: [#371](https://github.com/khab40/lob-arena/pull/371).

As a platform operator, I want dependency maintenance to retain strict Java
diagnostics, so that kernel verification remains reproducible.

The original seven-update PR raises six gRPC artifacts from 1.84.0 to 1.84.1
and Gradle from 9.7.1 to 9.8.1. Actions run 38117440101 fails both Java jobs:
the current Protobuf plugin calls deprecated `Configuration.setVisible`.

Delivered increment: retain all six gRPC updates; restore the verified Gradle
9.7.1 wrapper properties and original JAR; retain `org.gradle.warning.mode=fail`.
No application behavior change intended beyond those six patch releases.
Reuse the existing wrapper, Protobuf plugin, Java check and permanent golden
corpus workflow. Kernel behavior remains owned by
[`docs/runtime/java-simulation-kernel.md`](../runtime/java-simulation-kernel.md).
No dependency or parallel workflow is added; no warning bypass is introduced.

The Gradle 9.8.1 upgrade is deferred to OPEN Bug #400. This PR delivers only the
compatible gRPC increment and must not close that Bug or claim the original
Gradle update accepted. Its wrapper upgrade remains incomplete until AC-03.
Out of scope: plugin replacement, model/cloud work, merge and cleanup.

```gherkin
Feature: Java dependency refresh with strict diagnostics
  Scenario: AC-01 Verify the compatible gRPC patch increment
    Given six gRPC artifacts at 1.84.1 and Gradle 9.7.1
    When existing Java kernel and golden corpus checks run
    Then both checks pass

  Scenario: AC-02 Preserve wrapper integrity and strict warnings
    Given the verified Gradle 9.7.1 wrapper and failure-on-warning policy
    When the compatible dependency increment is prepared
    Then the original wrapper JAR and checksum remain unchanged
    And warning mode remains fail

  Scenario: AC-03 Qualify the deferred Gradle upgrade
    Given a Protobuf plugin compatible with Gradle 9.8.1
    When the same strict Java and golden checks run with Gradle 9.8.1
    Then both checks pass without deprecation or warning bypass
```

| Scenario | Implementation/contract | Test/check | Evidence | Status |
| --- | --- | --- | --- | --- |
| AC-01 | Existing exchange-proto/kernel-grpc build files | `./gradlew clean check --no-daemon`; CI Java 25 and permanent golden corpus | `outputs/chore-deps-20261013/pr371-tests.log`, `pr371-ci.json` | Pass (local and golden CI; receipt pins verified head) |
| AC-02 | Existing wrapper and `java/gradle.properties` | Compare wrapper properties/JAR/policy with baseline; six-artifact version check | `outputs/chore-deps-20261013/pr371-verification.json` | Pass (static) |
| AC-03 | Deferred Gradle 9.8.1/Protobuf compatibility | Same strict Java/golden checks after compatibility correction | Bug #400 and retained failed log `pr371-java-failed.log` | Gated; not delivered |

CI pass above is pinned to dependency head `33aa9437b97ad3e6eba1e1cbdbf653b06b8210e0`
in `outputs/chore-deps-20261013/pr371-ci-pre-traceability.json`. This status-only
update changes no dependency or product bytes. Each subsequent publication head
requires fresh CI before merge; its result is retained in `pr371-ci.json`.

Exact diff/spec pins and independent review remain in root
`outputs/chore-deps-20261013/`. Current green verification cannot complete AC-03.
