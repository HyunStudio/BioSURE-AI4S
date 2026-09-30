# BioSURE — reference-conditioned document integrity workbench

BioSURE is a local Tool & Platform prototype for paragraph-conversion quality control upstream of life-science research-support pipelines. It compares actual reference and converted text, proposes one internal missing paragraph or one extra exact duplicate, validates the proposed graph edit, and returns normalized text and a replayable decision receipt. Other changes require manual review.

No learned model, external inference, paid API or GPU is required. This is not a translator, PDF/DOCX parser, biological predictor, source-authentication service or clinical safety tool. Reference truth is an assumption, not a result.

Project: [HyunStudio/BioSURE-AI4S](https://github.com/HyunStudio/BioSURE-AI4S). Maintainer: HyunStudio. Project-authored assets are MIT; article derivatives retain CC BY 4.0 notices. See RIGHTS for the exact boundary.

[Watch the captioned demonstration](https://hyunstudio.github.io/BioSURE-AI4S/) · [Download version 0.2.0](https://github.com/HyunStudio/BioSURE-AI4S/releases/tag/v0.2.0). The watch page hosts the video, not a public paragraph-upload server. The workbench runs locally.

## Quick start — Python 3.12

From this standalone package's root:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python scripts/verify_reproduction.py .
python -m biosure.web_demo
```

Open `http://127.0.0.1:8765`. Load a fictitious example, acknowledge the reference assumption, and check. Use **Batch review** to load six fictional records, import a local JSON file or paste records; inspect individual decisions and download the full result. Editing inputs or clearing the view invalidates prior downloads. The workbench shows difference locations, the decision, normalized output when applied, and JSON receipts. Text is processed in memory; it is not sent to an external service. Downloads and explicit batch exports contain supplied text. Do not use patient or confidential data. The server must stay local, not public-hosted.

If port 8765 is occupied, stop that instance or run `python -m biosure.web_demo --port 8771`. The printed URL uses the actual bound port. Missing fixtures and occupied ports fail with an actionable message, not a running broken service. Default fixtures resolve relative to the source module, not your current working directory. No installer or package installation is needed.

The batch example has six fictional records: two automatically corrected, one unchanged, three requiring review. It is a functional check, not an independent usability experiment. Browser imports/pasted JSON are at most 1 MiB. CLI batches use `python -m biosure.cli batch --input fixtures/workflow_examples.json --out ../sample-batch-results.json` and allow at most 8 MiB. The output must be a new file; existing files are never replaced. To rerun, choose another output filename. Batch: 1–100 unique record IDs. Individual workflow limits: 128 paragraphs per sequence, 4096 characters each, 262144 normalized characters combined. Paragraphs must match exactly after whitespace normalization, in the same language.

## Reproduce all evaluations

```powershell
python -m biosure.cli blind-evaluate --cases fixtures/challenge --gold fixtures/gold --out synthetic-results
python -m biosure.cli blind-evaluate --cases fixtures/article_challenge --gold fixtures/article_gold --out article-results
python -m biosure.cli blind-evaluate --cases fixtures/stress_challenge --gold fixtures/stress_gold --out stress-results
```

The verifier checks the frozen expected counts for all three sets and the complete stress summary; it fails on drift rather than silently changing expectations. All supplied evaluations are offline. Optional article regeneration requires the official PMC API; runtime and replay do not.

| Evaluation | Constructed cases / sources | Exact automatic | Incorrect automatic | Abstained |
|---|---:|---:|---:|---:|
| Authored synthetic | 8 / 2 | 2 | 0 | 6 |
| Article-derived | 9 / 3 | 3 | 0 | 6 |
| Authored stress | 168 / 12 | 24 | 12 | 132 |

Whole-graph reconstruction receiving the same evidence ties the first two sets, and applies 36 exact / 12 incorrect in stress. BioSURE does not demonstrate algorithmic superiority. Every gate error is a deliberately forged-reference control: the candidate and declared reference agree, but the gold is unchanged. These are constructed conditions, not independent natural defects or deployment error rates. Reference and gold share an origin.

## Development tests and interfaces

Version 0.2 adds **AI / upstream proposal** validation. Paste a proposed repaired paragraph sequence from your upstream tool into the expanded panel, leaving the reference and converted inputs unchanged. The actual proposed text is checked; invented wording or unrelated edits are not silently replaced with the reference. The app itself makes no model call and does not authenticate a pasted proposal's origin. POST `/api/proposal` and `python -m biosure.cli proposal --input proposal-input.json` accept exactly the workflow fields plus `proposed_paragraphs`. A proposal receipt additionally binds all three normalized input digests to the gate receipt, including rejected unsupported proposals. It is a content hash, not a signature or biological validation.

Batch records now show numbered reference and converted paragraphs with difference spans, including manual-review cases. Sample/file loads cannot be canceled by acknowledging the reference; editing or clearing still prevents stale responses from replacing newer input.

Install pytest if not already available, then run `python -m pytest tests -q -p no:cacheprovider`. Core runtime uses Python's standard library; pytest is development-only. Prior-work diagnostics are intentionally excluded from this profile; the associated private-prior arithmetic test is skipped, not passed as a reproduced result.

Browser logic regressions run separately with `node --test tests/test_browser_logic.js` (Node.js 20+ for development tests only). CI runs both suites on Windows and Ubuntu. Browser/HTTP tests are software checks, not researcher studies or model benchmarks.

`python -m biosure.cli workflow --input paragraph-input.json` accepts exactly `record_id`, `reference_paragraphs`, `observed_paragraphs`. The same adapter is available through POST `/api/workflow`; arrays use POST `/api/batch`, and strict graph requests use POST `/api/decide`. The latter never receives evaluation gold. See the [workflow](workflow-scenario.md), [technical submission](public-submission.md), and [practical-validation boundary](practical-validation.md) in the report folder.

## Rights and release status

See [RIGHTS.md](../RIGHTS.md). The owner authorized release-preparation decisions except registration on 2026-09-30; the audited no-prior source profile is licensed and attributed accordingly. Private-prior code, DKE aggregates/manifests and internal reports are excluded. Publishing a full private source checkout/history is not authorized by this export.

`results/release_manifest.json` binds distributed source files (ignoring only root Git metadata), not authorship or truth. Verify an unchanged checkout before generating output files, with bytecode/cache creation disabled as above. To re-audit a clean staging directory, create a new destination outside the checkout: `python scripts/prepare_release.py . ../audited-release`, then `python scripts/audit_release.py ../audited-release`. The destination must not exist. The GitHub verification workflow tests the standalone profile on Windows and Ubuntu; its live status is the evidence, not this sentence. Competition registration and actual submission are separate owner actions.
