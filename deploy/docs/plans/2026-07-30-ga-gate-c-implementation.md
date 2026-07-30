# OpenRath v2.0.0 Gate C Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a fail-closed target-evidence toolchain and dedicated workflow
that produces the exact same-SHA Gate C artifact required by the GA preparation
workflow.

**Architecture:** Target-side tools record immutable evidence files and six
strict gate reports. A protected self-hosted collector validates and uploads
the bundle; the GA preparation workflow accepts only that workflow identity
and exact candidate SHA.

**Tech Stack:** Python 3.12, httpx, pytest, GitHub Actions, pinned GitHub
actions, actionlint, zizmor.

---

### Task 1: Harden the Gate C report contract

**Files:**
- Modify: `scripts/release/verify_gate_reports.py`
- Create: `scripts/release/record_gate.py`
- Modify: `release/evidence/schema/ga-gate-report.schema.json`
- Modify: `tests/deployment/test_ga_gate_reports.py`

**Steps:**
1. Add failing tests for target-like environment requirements, evidence file
   hashes, traversal, symlinks, and missing evidence.
2. Run `uv run pytest tests/deployment/test_ga_gate_reports.py -q`.
3. Implement strict evidence validation and the reusable report recorder.
4. Run the targeted test again and confirm it passes.

### Task 2: Add bounded target load and performance reporting

**Files:**
- Create: `scripts/release/load_v2.py`
- Create: `scripts/release/build_performance_report.py`
- Create: `tests/deployment/test_release_load.py`

**Steps:**
1. Add tests for authentication redaction, lifecycle completion, sample
   validation, profile coverage, and scaling efficiency.
2. Implement an httpx lifecycle load client that writes raw JSON samples.
3. Implement a combiner requiring single-host plus split one/two/four-worker
   samples and zero errors.
4. Run `uv run pytest tests/deployment/test_release_load.py -q`.

### Task 3: Add target soak and drill recording

**Files:**
- Create: `scripts/release/build_soak_report.py`
- Create: `scripts/release/build_drill_report.py`
- Create: `deploy/docs/drills-v2.md`
- Create: `tests/deployment/test_release_operations_evidence.py`

**Steps:**
1. Add failing tests for the 28,800-second minimum, zero-error requirement,
   resource-growth decision, complete fault matrix, backup/restore, and
   rollout/rollback.
2. Implement report builders that bind raw logs and resource snapshots without
   executing destructive operations.
3. Document exact operator evidence and stop conditions.
4. Run the targeted operations-evidence tests.

### Task 4: Add the protected collector workflow

**Files:**
- Create: `.github/workflows/collect-v2-ga-evidence.yml`
- Modify: `.github/workflows/release-v2-ga.yml`
- Modify: `tests/deployment/test_release_version.py`
- Modify: `release/checklists/v2.0.0-ga.md`

**Steps:**
1. Add workflow contract tests requiring `main`, the exact SHA, the protected
   environment, fixed self-hosted labels, safe bundle identifiers, and the
   exact artifact name.
2. Implement the collector with pinned actions and minimal permissions.
3. Restrict GA preparation to a successful workflow-dispatch run named
   `Collect v2.0.0 Gate C evidence` on `main`.
4. Run workflow contract tests, actionlint, and zizmor.

### Task 5: Verify and publish the PR update

**Files:**
- Modify: PR #51 description

**Steps:**
1. Run Ruff, MyPy, targeted tests, and the complete non-external suite.
2. Run actionlint, zizmor, YAML parsing, and `git diff --check`.
3. Commit the exact Gate C files and push the existing PR branch.
4. Update PR #51 with the new trust boundary and validation results.
5. Monitor all PR checks to completion.

### External handoff

1. Configure approved Provider/OpenViking secrets without sharing values.
2. Register a Linux self-hosted runner labelled `openrath-ga`.
3. Configure the protected `ga-evidence` environment and its evidence-root
   variable.
4. Provision the target cluster and run the documented 1/2/4-worker, eight-hour
   soak, and recovery drills on the final SHA.
5. Dispatch the collector and provide its run ID to GA preparation.
