# BioSURE Evidence-First Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a frozen, source-level OoC PDF audit that compares BioSURE with same-input simple baselines without hiding failures.

**Architecture:** Reuse `biosure.native_pilot` as the one-source gold-blind decision and scoring primitive. A small aggregate module validates a locked manifest, executes every attempted source and unit, and emits decisions and a score summary only to a fresh output directory. A separate acquisition protocol fixes metadata-only source selection before inspecting text layers.

**Tech Stack:** Python 3.12, pytest, existing pypdf/ReportLab test dependencies, Node 20+ for existing browser tests.

**Spec:** `docs/superpowers/specs/2026-10-04-biosure-evidence-first-design.md`

## Global Constraints

- Eight target OoC sources: four development and four held-out; never tune on held-out data.
- Keep unavailable or unscorable attempts visible; never substitute favorable sources post-inspection.
- Decision phase cannot read gold; direct copy and diff receive the same input.
- No independent-expert, human-time, biological-impact or first-place claim without evidence.
- Registration and Kaggle Writeup submission remain owner-only.
- Do not overwrite output or existing release tags; source PDFs/XML remain out of package unless rights are separately cleared.

## Review Focus

- Missing source path must fail before writing any output; Task 1 tests preflight atomicity.
- Duplicate source/unit/case ID must fail; Task 1 tests all identity levels.
- Unscorable unit without reason must fail; Task 1 tests explanatory metadata.
- Gold/decision digest mismatch must fail rather than be skipped; Task 2 tests propagation.
- A zero-discrepancy audit must retain attempted counts and zero metrics; Task 2 tests the negative outcome.

---

### Task 1: Manifest contract and preflight

**Files:**
- Create: `biosure/prospective_audit.py`
- Test: `tests/test_prospective_audit.py`

**Interfaces:**
- Produces: `preflight_manifest(manifest: dict, root: Path) -> list[dict]`, returning validated source entries in locked order. Manifest schema is `biosure.prospective-audit/1.0` with `protocol_path`, `protocol_sha256`, `sources`; each source has unique `source_id`, `split` (`development` or `held_out`), `license_uri`, `doi`, `pmcid`, and `units`. Every unit has unique `unit_id`, `status` (`scorable` or `unscorable`), `case_id` for scorable units, and nonempty `reason` for unscorable units. Sources with a scorable unit have `inputs_path`, `gold_path`, `inputs_sha256`, `gold_sha256`; all-unscorable sources have none. Relative paths must stay inside root. Preflight validates protocol and input digests, existence of gold paths, and exact unit/case correspondence, but does not open gold bytes.

- [ ] **Step 1: Write failing tests** for a valid mixed manifest, missing file, traversal path, duplicate source/unit/case ID, invalid split/status, unscorable without reason, stale protocol/input digest, and unit/case mismatch.
- [ ] **Step 2: Run red:** `python -m pytest tests/test_prospective_audit.py -q -p no:cacheprovider`; failures must be missing behavior, not setup errors.
- [ ] **Step 3: Implement** `preflight_manifest(manifest: dict, root: Path) -> list[dict]` using `loads_json` and SHA-256; resolve and verify protocol/input paths and check gold path existence without reading gold bytes.
- [ ] **Step 4: Run green** with the same command, then run the complete Python suite.
- [ ] **Step 5: Commit** test and module.

### Task 2: Gold-blind aggregate runner and scorer

**Files:**
- Modify: `biosure/prospective_audit.py`
- Create: `scripts/evaluate_prospective_audit.py`
- Test: `tests/test_prospective_audit.py`

**Interfaces:**
- Consumes: `preflight_manifest(manifest, root)` from Task 1 and existing `decide_inputs(inputs, model)` / `score_decisions(decisions, gold)`.
- Produces: `evaluate_manifest(manifest: dict, root: Path, model: dict) -> dict` that returns a JSON-serializable decisions-and-summary object. The function first computes decisions for every scorable source using inputs only; only after all decisions exist does it verify and load any gold and score. Summary includes `attempted_sources`, `scorable_sources`, `attempted_units`, `scorable_units`, `unscorable`, `native_error_cases`, `biosure`, `direct_copy`, `diff_review`, `learned_review`, and `source_results`, with development/held-out breakdowns.

- [ ] **Step 1: Write failing tests** that prove gold is not read during any decision, zero-error totals remain zero, unscorable attempts are counted, failed scoring propagates, and split totals sum to the overall total.
- [ ] **Step 2: Run red:** focused pytest command above.
- [ ] **Step 3: Implement** `evaluate_manifest` and a CLI that accepts manifest, model and one new output directory, performs complete in-memory evaluation before creating it, and writes canonical JSON decisions and summary. Refuse existing output.
- [ ] **Step 4: Run green**, full Python suite, and `python scripts/verify_reproduction.py .`.
- [ ] **Step 5: Commit** runner, CLI and tests.

### Task 3: Lock source-selection protocol and conduct audit

**Files:**
- Create: `report/prospective-ooc-audit-protocol.md`
- Create: `fixtures/prospective_ooc_manifest.json`
- Create: `fixtures/prospective_ooc_*_inputs.json`, `fixtures/prospective_ooc_*_gold.json` for scorable sources
- Create: `results/prospective_ooc_audit.json`
- Modify: `report/public-scorecard.md`, `report/public-submission.md`, `README.md`, `RIGHTS.md`, release inclusion checks as required.
- Test: `tests/test_prospective_audit.py`, `tests/test_release.py`

**Interfaces:** Consumes Task 2 CLI; produces frozen public fixture/result evidence, no unlicensed binaries.

- [ ] **Step 1: Lock exact public metadata query, timestamp, order, eight selected PMCID/DOI identities, exclusions and first-page title/abstract attempt rule in a commit before inspecting selected PDF text layers.**
- [ ] **Step 2: Acquire all locked PDF/XML bytes and record URLs, licenses, hashes, document versions and failed acquisitions.**
- [ ] **Step 3: Write independent fixture-validation tests for every locked case and every manifest entry; run red.**
- [ ] **Step 4: Extract observed text; create separate gold against rendered page/JATS; retain disagreement and unscorable reasons; run CLI.**
- [ ] **Step 5: Run green; update report with all outcomes, same-input baselines, and limitations; commit.**

### Task 4: Conditional product improvement and submission consistency

**Files:** Determined by the measured defect; do not preselect a favorable target. Likely `biosure/pdf_extract.py`, `tests/test_pdf_extract.py`, `report/pdf-spacing-crosscheck.md`, watch-page copy and video assets.

**Interfaces:** Only start a product behavior change if development data exposes a concrete reproducible fault. Keep held-out sources untouched until after the change is frozen.

- [ ] **Step 1: Reproduce one development defect in a failing test; run red.**
- [ ] **Step 2: Implement the smallest safe change; run green and all old/new audits, including forged-reference stress.**
- [ ] **Step 3: Compare held-out performance and report ties/regressions without suppressing them. If no defensible change exists, explicitly record that outcome and skip code changes.**
- [ ] **Step 4: Refresh current-version demo and claims only after results are frozen; verify full video decode, duration under five minutes, rights, public links and archive/version alignment.**
- [ ] **Step 5: Run clean Windows clone tests, Node tests, reproduction and release audits, then inspect public CI and Pages before claiming readiness.**
