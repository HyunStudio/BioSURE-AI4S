# BioSURE — reference-conditioned document integrity workbench

BioSURE is a local Tool & Platform prototype for document-conversion quality control upstream of life-science research-support pipelines. It compares actual reference and converted text, proposes one internal missing paragraph or one extra exact duplicate, validates the proposed graph edit, and returns normalized text and a replayable decision receipt. A small trained correspondence model ranks candidate paragraph matches for human review and flags lexical number, unit and negation differences; it never authorizes an edit. Other changes require manual review.

No external inference, paid API or GPU is required. The bundled offline model is trained on attributed CC BY 4.0 article excerpts; its benchmark ties strong lexical baselines on constructed alterations. This is not a translator, faithful PDF/DOCX converter, biological predictor, source-authentication service or clinical safety tool. Reference truth is an assumption, not a result.

Project: [HyunStudio/BioSURE-AI4S](https://github.com/HyunStudio/BioSURE-AI4S). Maintainer: HyunStudio. Project-authored assets are MIT; article derivatives retain CC BY 4.0 notices. See RIGHTS for the exact boundary.

[Watch the 4-minute-48-second captioned demonstration](https://hyunstudio.github.io/BioSURE-AI4S/). The v0.3 montage shows the earlier core workflow plus actual learned review and PDF warning screens. It is not a continuous recording or speed test. The watch page hosts video, not a public paragraph-upload server.

## Quick start — Python 3.12

From this standalone package's root:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pip install -e .
python scripts/verify_reproduction.py .
python -m biosure.web_demo
```

Open `http://127.0.0.1:8765`. Load a fictitious example, acknowledge the reference assumption, and check. Use **Batch review** to load six fictional records, import a local JSON file or paste records; inspect individual decisions and download the full result. Editing inputs or clearing the view invalidates prior downloads. The workbench shows difference locations, the decision, normalized output when applied, and JSON receipts. Text is processed in memory; it is not sent to an external service. Downloads and explicit batch exports contain supplied text. Do not use patient or confidential data. The server must stay local, not public-hosted.

If port 8765 is occupied, stop that instance or run `python -m biosure.web_demo --port 8771`. The printed URL uses the actual bound port. Missing fixtures and occupied ports fail with an actionable message. Default fixtures resolve relative to the source module. Python package installation supplies the BSD-licensed `pypdf` dependency for optional local PDF text-layer import.

PDF import accepts at most 16 MiB and 32 pages. It yields **unverified page-text chunks, not paragraphs**; copied figure labels, table structure, reading order, equations and layout are not guaranteed. The interface warns about embedded images and requires a separate acknowledgement after the user compares every chunk with the original pages and splits/corrects it manually. It never stores the uploaded PDF. The same review-only extraction is available with `python -m biosure.cli pdf-extract --input paper.pdf`; output includes page numbers and SHA-256 hashes but no invented bounding boxes. If a page has no text layer, OCR or manual transcription is required. Do not interpret a text-layer hash as proof of source authenticity.

The batch example has six fictional records: two automatically corrected, one unchanged, three requiring review. It is a functional check, not an independent usability experiment. Browser imports/pasted JSON are at most 1 MiB. CLI batches use `python -m biosure.cli batch --input fixtures/workflow_examples.json --out ../sample-batch-results.json` and allow at most 8 MiB. The output must be a new file; existing files are never replaced. To rerun, choose another output filename. Batch: 1–100 unique record IDs. Individual workflow limits: 128 paragraphs per sequence, 4096 characters each, 262144 normalized characters combined. Paragraphs must match exactly after whitespace normalization, in the same language.

## Reproduce all evaluations

```powershell
python -m biosure.cli blind-evaluate --cases fixtures/challenge --gold fixtures/gold --out synthetic-results
python -m biosure.cli blind-evaluate --cases fixtures/article_challenge --gold fixtures/article_gold --out article-results
python -m biosure.cli blind-evaluate --cases fixtures/stress_challenge --gold fixtures/stress_gold --out stress-results
python scripts/verify_reproduction.py .
```

The verifier checks the frozen expected counts for all three sets and the complete stress summary; it fails on drift rather than silently changing expectations. All supplied evaluations are offline. Optional article regeneration requires the official PMC API; runtime and replay do not.

| Evaluation | Constructed cases / sources | Exact automatic | Incorrect automatic | Abstained |
|---|---:|---:|---:|---:|
| Authored synthetic | 8 / 2 | 2 | 0 | 6 |
| Article-derived | 9 / 3 | 3 | 0 | 6 |
| Authored stress | 168 / 12 | 24 | 12 | 132 |

Whole-graph reconstruction receiving the same evidence ties the first two sets, and applies 36 exact / 12 incorrect in stress. BioSURE does not demonstrate algorithmic superiority. Every gate error is a deliberately forged-reference control: the candidate and declared reference agree, but the gold is unchanged. These are constructed conditions, not independent natural defects or deployment error rates. Reference and gold share an origin.

The learned correspondence component uses regularized logistic regression fitted on 4,584 constructed paragraph pairs from 12 of 24 CC BY 4.0 PMC articles. Six development articles select a frozen threshold; six unseen articles form the held-out test. On 284 constructed held-out queries, learned logistic, `difflib`, token Dice and a lexical blend each select all 284 intended references; exact matching accepts 96 and abstains on 188. The learned-minus-best-lexical top-1 accuracy difference is **0.000** (article-bootstrap 95% interval **[0.000, 0.000]**). Eight held-out unit-change controls exercise the lexical unit alert. This shows no learned advantage over simple string methods and says nothing about real conversion-error prevalence. The model still provides candidate rankings and lexical critical-token alerts for triage; the deterministic gate is unchanged. `fixtures/ml_corpus.json` contains attributed excerpts, `fixtures/ml_model.json` frozen weights, and `results/ml_evaluation.json` the split/metrics. The offline verifier refits and compares these artifacts.

On the separate public [JHU neuroanatomy article](https://pmc.ncbi.nlm.nih.gov/articles/PMC12645051/) (DOI 10.1038/s41467-025-65317-7), a two-page PDF excerpt exposed the practical boundary: the import recovers searchable `workflows` and `quantification` after ligature normalization, but three embedded images contain labels absent from the text layer. It emits two unverified page chunks and image/reading-order/letter-spacing warnings. Against eight JATS reference paragraphs, learned scores were low (0.363 and 0.325) and the gate abstained. This is an out-of-domain diagnostic, not a benchmark or assertion that the PDF is safely converted.

## Development tests and interfaces

The **AI / upstream proposal** panel validates pasted output. Paste a proposed repaired paragraph sequence from your upstream tool into the expanded panel, leaving the reference and converted inputs unchanged. The actual proposed text is checked; invented wording or unrelated edits are not silently replaced with the reference. The app itself makes no remote model call and does not authenticate a pasted proposal's origin. POST `/api/proposal` and `python -m biosure.cli proposal --input proposal-input.json` accept exactly the workflow fields plus `proposed_paragraphs`. A proposal receipt additionally binds all three normalized input digests to the gate receipt, including rejected unsupported proposals. It is a content hash, not a signature or biological validation.

Batch records now show numbered reference and converted paragraphs with difference spans, including manual-review cases. Sample/file loads cannot be canceled by acknowledging the reference; editing or clearing still prevents stale responses from replacing newer input.

Install development tools with `python -m pip install pytest reportlab`, then run `python -m pytest tests -q -p no:cacheprovider`. The runtime uses Python's standard library plus BSD-licensed `pypdf`; ReportLab generates test PDFs and is not needed to run the app. Prior-work diagnostics are intentionally excluded from this profile; the associated private-prior arithmetic test is skipped, not passed as a reproduced result.

Browser logic regressions run separately with `node --test tests/test_browser_logic.js` (Node.js 20+ for development tests only). CI runs both suites on Windows and Ubuntu. Browser/HTTP tests are software checks, not researcher studies or model benchmarks.

`python -m biosure.cli workflow --input paragraph-input.json` accepts exactly `record_id`, `reference_paragraphs`, `observed_paragraphs`. The same adapter is available through POST `/api/workflow`; POST `/api/ml-review` adds review-only rankings, POST `/api/pdf-extract` accepts raw local PDF bytes, arrays use POST `/api/batch`, and strict graph requests use POST `/api/decide`. The latter never receives evaluation gold. See the [workflow](workflow-scenario.md), [technical submission](public-submission.md), and [practical-validation boundary](practical-validation.md) in the report folder.

## Rights and release status

See [RIGHTS.md](../RIGHTS.md). The owner authorized release-preparation decisions except registration on 2026-09-30; the audited no-prior source profile is licensed and attributed accordingly. Private-prior code, DKE aggregates/manifests and internal reports are excluded. Publishing a full private source checkout/history is not authorized by this export.

`results/release_manifest.json` binds distributed source files (ignoring only root Git metadata), not authorship or truth. Verify an unchanged checkout before generating output files, with bytecode/cache creation disabled as above. To re-audit a clean staging directory, create a new destination outside the checkout: `python scripts/prepare_release.py . ../audited-release`, then `python scripts/audit_release.py ../audited-release`. The destination must not exist. The GitHub verification workflow tests the standalone profile on Windows and Ubuntu; its live status is the evidence, not this sentence. Competition registration and actual submission are separate owner actions.
