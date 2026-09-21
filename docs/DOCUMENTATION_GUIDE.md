# Documentation ownership

Start at the [documentation index](README.md). Each fact has one maintained
owner; other documents summarize its purpose and link to it.

| Information | Owner |
| --- | --- |
| Installation and first run | [Quickstart](deployment/QUICKSTART.md) |
| Current system boundaries | [Architecture](architecture.md) |
| Decision, alternatives and tradeoffs | Relevant [ARD](architecture/README.md) |
| Capability and acceptance scope | [Functional overview](product/FUNCTIONAL_OVERVIEW.md) |
| User workflow | [Use-case catalogue](use-cases/README.md) or focused ML guide |
| Current gates, issue state and dated evidence | [Current status](roadmap/CURRENT_STATUS.md) |
| Target dates and dependencies | [Main roadmap](roadmap/ROADMAP-MAIN.md) |
| Forward feature requirements | [Phase scope](roadmap/PHASES.md) |
| Exact contract, formula or command | Relevant data, ML, runtime or operations reference |
| Historical attempts and review outcomes | [Archive](archive/README.md), linked receipts |

## Editing rules

1. Update the owning document. Update consumers only when their scope or link
   changes; do not copy status, contracts or procedures into every overview.
2. Preserve unique requirements, formulas, failure semantics and authorization
   boundaries. Keep exact receipts and frozen `evidence/` snapshots unchanged.
3. Distinguish design acceptance, implemented software, synthetic rehearsal and
   production qualification. Baseline dates are not a revised forecast.
4. Keep dated execution history outside current instructions. A historical
   command or approval is not authority to run it again.
5. Retain ARD identifiers. Mark superseded decisions and name their successors;
   keep context, decision, alternatives and consequences. Add diagrams or
   implementation detail only when needed to explain that decision.
6. Use relative local links and HTTPS externally. When moving a page, update
   its relative links and retain navigation for referenced old paths/anchors.
7. Give each diagram one owner. Link to it elsewhere. Prefer diagrams for
   ownership, state, branching, concurrency or trust boundaries; use prose or a
   table for short linear lists. Label proposed/historical views explicitly.
8. Do not require a diagram, status table, documentation map or generic
   "business value" section in every document. Avoid another full-file review
   ledger for routine edits; put validation evidence in the PR.

## Validation

- Run `python3 scripts/check_markdown_links.py` against active Markdown files
  and any changed archives, excluding immutable evidence snapshots.
- Render new/changed Mermaid blocks and visually inspect them. Unchanged
  blocks can be checked by content hash against a previously rendered baseline.
- Check moved-file consumers in scripts and packaging; run affected static
  packaging checks where applicable.
- Run `git diff --check`; compare protected file/section hashes before and after
  compaction. Report net text reduction separately from archiving.
- Apply [model execution policy](ml/model-validation-execution-policy.md);
  documentation checks do not require training, scoring or cloud workloads.
