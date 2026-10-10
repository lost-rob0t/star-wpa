# RAGE Research Agent Instructions

This file is authoritative for humans and automated agents working in this repository.

## Before changing anything

Observe, do not assume:

```bash
git status --short
git branch --show-current
git remote -v
find .. -name AGENTS.md -print
```

Read every applicable nested `AGENTS.md`. Do not overwrite unrelated work. Current source, tests, scripts, and tracked repository state override stale prose or remembered behavior.

## RAGE

RAGE means **Recursive Analysis with Gated Execution**.

Every loop must be grounded in observed state. Analysis identifies evidence, constraints, contradictions, and unknowns. Execution is admitted only by an explicit gate. Evaluation records what actually happened. The next loop starts from that evidence rather than from the previous plan.

Do not treat a plan, generated patch, existing file, merge, or green build as proof that a gate was approved.

## Repository model

- `roam/research/` owns research and findings.
- `roam/design/` owns canonical designs.
- `roam/implement/` owns active implementation working copies.
- `roam/indexes/` owns project indexes and roadmaps.
- `scripts/` owns capture, lifecycle, synchronization, and validation.
- `tests/` owns regression coverage for repository mechanics.

Use existing scripts before inventing parallel workflow machinery.

## Document contract

Every substantive Org document must contain:

```org
:PROPERTIES:
:ID: stable-id
:END:
#+title:
#+description:
#+status:
#+filetags:
```

It must also contain an approval table and changelog.

Use this approval header:

```org
* Approval Table

| Approval area | Required authority | State | Evidence required | Evidence reference |
|---------------+--------------------+-------+-------------------+--------------------|
```

Allowed approval states are `PENDING`, `NOT STARTED`, `APPROVED`, `REJECTED`, `SUPERSEDED`, and `NOT APPLICABLE`.

Never fabricate approval or evidence. `NOT APPLICABLE` needs a reason. Preserve stable IDs. Duplicate IDs and unresolved `id:` links are validation failures.

Use this changelog header:

```org
* Changelog

| Date | Change | Author or actor | Evidence |
|------+--------+-----------------+----------|
```

Research must separate verified facts, inference, contradictions, and unresolved questions. For externally changing facts, prefer current primary sources and record retrieval dates.

## Implementation gates

Each immediate project subtree under `roam/implement/` may contain at most one active Org design.

Promote through `scripts/implement.py`; do not manually create competing active copies. Record terminal outcomes through `scripts/mark-design.py`. Implemented and rejected ledgers are append-only evidence.

Retries and repeated runs must be idempotent where practical. A stale or failed run must not silently become success.

## Generated and sensitive material

Do not commit `.cache/`, `_site/`, generated databases, credentials, authorization headers, private evidence, session material, or secrets.

Never hand-edit generated output. Change source or generators instead.

## Validation

Before completion run and observe:

```bash
git diff --check
git diff --stat
python3 -m py_compile scripts/*.py
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 scripts/sync.py
python3 scripts/sync.py --check
python3 scripts/validate-docs.py
```

Never claim a command passed unless it was executed and its result was observed. Never bypass a failing wrapper with a lower-level command just to obtain a green exit code.

<!-- BEGIN STARINTEL FLEET CONTRACT -->
## StarIntel 15-worker fleet contract

This repository participates in the StarIntel hourly worker fleet.

- **GitHub connector is the repository control surface for fleet automation.** Use the connected GitHub connector to read current `AGENTS.md`, repository files, issues, pull requests, branches, diffs, comments, reviews, and CI/check state, and for permitted writes. Attempt the connector before claiming GitHub repository access or mutation is unavailable.
- **Canonical StarIntel document authority is 0.10.1 generated from Star Language.** The source of truth is `lost-rob0t/star-lang/specs/starintel/0.10.1/core.star` and its generated artifacts. Consumer repositories must consume/pin generated output; they must not maintain a competing handwritten schema or revive 0.9.x as canonical authority.
- **Respect worker ownership.** SL01-SL05 own Star Language/compiler/schema domains; PA06-PA09 own Pro Actors/collection runtimes; SS10-SS13 own server/runtime/router/persistence/security; IR14-IR15 own cross-repo integration and release admission. Do not duplicate an in-flight branch or silently take over another worker's owned slice.
- **One writer per branch.** Re-fetch exact head/base immediately before mutation. Reuse an existing retained branch/PR when it owns the task. Never force-push or overwrite concurrent work.
- **Evidence is exact-head.** Required CI/checks must be observed on the exact candidate SHA; pending, skipped, stale, foreign, mock-only, or unrun evidence is not green.
- **Scheduled fleet tasks stay enabled.** Repository work must not disable a scheduled worker unless the operator explicitly asks for that task to be disabled.

Repository-specific rules still apply; stricter local rules win unless they conflict with canonical StarIntel 0.10.1 authority or an explicit current operator instruction.
<!-- END STARINTEL FLEET CONTRACT -->
