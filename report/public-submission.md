Category: Tool & Platform

# BioSURE: Reference-Conditioned Structural Integrity for Life-Science Research Documents

Project: BioSURE. Public maintainer/account: HyunStudio (Hyun_Studio). Category: Tool & Platform. The owner authorized preparation and release decisions except registration; this report does not claim that competition registration or account submission has occurred.

## Demo video and code

Code: [BioSURE-AI4S](https://github.com/HyunStudio/BioSURE-AI4S), a standalone no-prior repository, not the private monorepo. [Release v0.2.0](https://github.com/HyunStudio/BioSURE-AI4S/releases/tag/v0.2.0). [Watch the demonstration](https://hyunstudio.github.io/BioSURE-AI4S/) or [download the MP4](https://github.com/HyunStudio/BioSURE-AI4S/releases/download/v0.2.0/biosure-demo.mp4). The captioned montage is under five minutes and shows actual local application states: paragraph input, bounded omission and duplicate correction, unsupported substitution, article attribution, the forged-reference failure boundary, batch manual inspection and accepted/rejected upstream proposals. It is labeled as captured states, not continuous recording or speed evidence. It contains original UI, original captions and fictional text; no music, private records or third-party visual media.

## Project summary

Life-science research-support pipelines often depend on text extracted from research documents. A structurally valid repair can still replace the wrong paragraph or change an unsupported payload. BioSURE provides an offline workbench for inspecting a proposed structural edit against separately declared reference evidence. It supports one internal missing paragraph or one extra exact duplicate, otherwise deferring to manual review. A receipt binds the supplied request, candidate, evidence, rule version and selected graph.

The tool processes actual paragraph input, shows difference locations, returns normalized text when applied and exports JSON. Batch triage distinguishes corrected, unchanged and review-required records without overwriting source files. A new provider-independent path checks actual pasted upstream proposals against locked reference and observation inputs, accepting a bounded supported edit or rejecting invented wording and unrelated changes. The standard-library runtime does not require a model, GPU, paid service or external inference. This demonstrates an integration interface for AI-assisted document pipelines, not a live AI-model evaluation or benefit to research outcomes.

Eight synthetic cases from two graphs yield two exact corrections and six abstentions. Nine article-derived cases from three CC BY 4.0 OoC articles yield three exact corrections and six abstentions. An independent whole-graph comparator using the same evidence ties both sets. A 168-case authored stress suite exposes twelve incorrectly applied outputs when reference evidence is forged. No deployment error rate or algorithmic superiority is inferred.

BioSURE's contribution is an inspectable, reproducible workflow tool with explicit limits, not a learned biological predictor or source-authentication system. Clinical use, semantic verification, natural-defect effectiveness and researcher time savings remain outside the demonstrated scope.

## Technical report

### 1. Problem and application scenario

A researcher or pipeline maintainer has a canonical paragraph sequence and a converted sequence of an OoC methods/results record. A conversion fault removes a methods paragraph or inserts an extra copy. A repair component may suggest an edit that is plausible in shape but not supported in content. The task is to inspect the proposed changed payload and decide whether exactly one bounded edit is consistent with the declared reference.

The included text examples are explicitly fictional, not actual lab incidents. The article probe uses real research-document structure reduced to hashes; it does not process experimental measurements. The current workbench is intended for local research-document QA upstream of analysis or AI-assisted research support. No AI inference is implemented; this submission's technical component is a deterministic computational tool. Tool & Platform describes the current contribution more accurately than a novel-model claim.

### 2. System and decision boundary

The graph request has exactly four fields: `case_id`, `damaged`, `candidates`, and `evidence`. Ordered blocks contain an ID, type, SHA-256 text digest, heading level and optional target. Citation anchors, if present, must resolve. Strict parsing rejects extra nested fields, invalid identities/hashes and outcome labels. Clean gold and corruption specifications are not decision inputs.

For insertion, a candidate differs by exactly one canonical paragraph. Its ID and hash must match an evidence entry; both surviving neighbor IDs must match the insertion position. For duplicate removal, the retained and removed identities and equal paragraph digest must match the declared identity evidence. Unrelated changes, contradictory evidence, absent support or multiple supported candidates cause abstention. The frozen rule is `biosure-blind-v2`. It is not a trained confidence score or calibrated statistical guarantee.

The paragraph adapter collapses whitespace and assigns stable reference IDs from unique paragraph digests. It proposes only one supported structural edit and invokes the same parser and gate. A successful response includes actual normalized text. Repeated reference content, boundary omission, substitution, reordering and multiple faults are unsupported. Difference hunks help manual inspection but never authorize an edit. Hunk spans are zero-based and half-open in JSON; the UI shows human-readable paragraph positions.

The upstream proposal adapter accepts the same locked reference and observed sequences plus `proposed_paragraphs`. It derives the supported operation/evidence from the original inputs, maps the actual proposed paragraph hashes into a candidate graph, then invokes the unchanged v2 gate. It does not substitute an internally generated repair for a rejected upstream proposal. If the original difference is unsupported, even a proposal copying the entire reference is not automatically applied. A proposal receipt binds reference, observation, actual proposal and gate receipt digests under `biosure-proposal-v1`; origin remains unauthenticated. This is a deterministic validation boundary for externally supplied output, not a learned detector or a demonstration that a named AI produced that output.

Batch input is an array of 1–100 workflow records with unique IDs. Validation completes before output creation; an invalid later item yields no partial output. The browser imports a local JSON file or accepts pasted JSON, displays per-record decisions and downloads the result. Editing/clearing invalidates stale results. CLI batch writes one explicitly selected new JSON file and never replaces an existing path. The summary separates unchanged records from automatic corrections and manual-review records. The HTTP limit is 1 MiB; the CLI limit is 8 MiB.

### 3. Receipts, privacy and trust

Canonical UTF-8 JSON is hashed to record input, evidence, candidates, configuration and selected graph. The same input yields the same decision receipt. Receipts provide content binding and replayability, not a signature, timestamp authority, authenticity proof or biological truth guarantee. A third party able to change a reference and recompute hashes can still create a consistent false result.

The browser server binds only to loopback, checks local Host and same Origin, rejects malformed/duplicate-key/non-finite JSON and applies a one-MiB body limit. Paragraph limits are 128 per sequence, 4096 characters each and 262144 normalized characters combined. Advanced graph requests have at most 32 candidates, 128 blocks per graph and 256 evidence entries. Inputs are processed in memory without server-side input storage or prose access logging. Explicit downloads contain user text. Clearing a browser view is not secure erasure. The server is not a production-hosting or clinical deployment system.

### 4. Data and evaluation design

The authored synthetic challenge has two graphs and eight deliberately selected conditions, including valid insertion/removal, wrong content/position/identity, missing evidence and two separately supported insertion alternatives. It is exploratory, not a confirmatory statistical sample.

The separate article-derived probe uses official PMC OAI-PMH JATS for [PMC5562747](https://pmc.ncbi.nlm.nih.gov/articles/PMC5562747/), [PMC7170869](https://pmc.ncbi.nlm.nih.gov/articles/PMC7170869/) and [PMC6745596](https://pmc.ncbi.nlm.nih.gov/articles/PMC6745596/). Each source explicitly declares CC BY 4.0. The generator selects the first three nonempty body paragraphs, collapses whitespace and keeps only digests and structural locators. It constructs three cases per source. Reference and gold come from the same JATS; this is not independent adjudication or native-defect discovery. No source prose, full XML, patient records or media are packaged. Full source metadata and change notice are included in provenance and RIGHTS.

The stress suite uses twelve authored graphs with 16/32/64 paragraphs and fourteen conditions per source: valid edits, no change, missing evidence, wrong hash/ID/location, extra metadata, unrelated edits, conflicting evidence, ambiguity, forged evidence, wrong retained identity and reordered context. There are 168 cases but twelve source graphs. The conditions are intentionally balanced negative controls, not estimates of deployment prevalence.

The evaluator records outcome-free decisions before opening clean gold, then checks the complete selected graph. Gold separation prevents decision-path leakage; it does not create independent source evidence. All sets remain separate. The source count is reported alongside case count.

### 5. Baselines and measured results

Identity proposes no correction. A weak schema/locality comparator accepts executable bounded graph edits without evidence validation. Hash-only matching receives the same evidence but checks only changed hashes. Independent whole-graph reconstruction receives the same evidence and builds canonical allowed one-edit graphs without calling BioSURE's validators or imposing its global conflict veto.

| Set and method | Automatic | Exact automatic | Incorrect automatic | Abstained |
|---|---:|---:|---:|---:|
| Synthetic / BioSURE | 2 | 2 | 0 | 6 |
| Synthetic / schema-locality | 7 | 3 | 4 | 1 |
| Synthetic / hash evidence | 5 | 2 | 3 | 3 |
| Synthetic / reconstruction | 2 | 2 | 0 | 6 |
| Article / BioSURE | 3 | 3 | 0 | 6 |
| Article / schema-locality | 9 | 6 | 3 | 0 |
| Article / hash evidence | 3 | 3 | 0 | 6 |
| Article / reconstruction | 3 | 3 | 0 | 6 |
| Stress / BioSURE | 36 | 24 | 12 | 132 |
| Stress / schema-locality | 120 | 48 | 72 | 48 |
| Stress / hash evidence | 96 | 36 | 60 | 72 |
| Stress / reconstruction | 48 | 36 | 12 | 120 |

BioSURE rejects four weak-baseline errors in the tiny synthetic probe and three in the article probe, but those wins do not prove novelty. Equal-evidence reconstruction ties both and corrects twelve additional stress cases with conflicting evidence. The conservative veto reduces coverage in that condition. Every BioSURE stress error occurs when both candidate and declared evidence are forged while gold stays unchanged; both strong methods fail all twelve forged-reference controls. This directly exposes the assumption boundary. It must not be advertised as a measured real-world 33% error rate or concealed in a headline of zero errors.

Six fictional actual-text workflow examples give two automatic corrections, one unchanged record and three manual reviews. They demonstrate the interface and triage behavior only, not an OoC user study. The automated package tests exercise implementation contracts, malformed inputs, privacy boundaries and reproduction. Test counts do not establish scientific validity.

### 6. Practical value and honest limits

Version 0.2 closes two usability defects found in release review: acknowledging a reference during asynchronous sample/file loading no longer discards the load, and every batch record exposes numbered reference/converted text plus change spans. The proposal path is exercised by offline function, HTTP, CLI and browser-logic tests: correct internal insertion/removal is accepted, invented wording, unrelated changes, reordering and additional copies are withheld, and unsupported original differences cannot be authorized by full replacement. These are authored implementation controls, not independently sampled model outputs.

| Alternative | Complete correct reference available | Unsupported original difference | Audit boundary |
|---|---|---|---|
| Direct reference copy | Restores the reference immediately | Replaces the whole document regardless of scope | No bounded decision is required |
| Apply upstream proposal unchecked | Depends on the proposal, including invented text | Applies all supplied changes | No content-evidence gate |
| BioSURE upstream proposal check | Applies only the supported one-edit match | Withholds automatic replacement | Actual candidate and declared evidence are content-bound |

This comparison describes policy, not measured superiority. Direct copying remains simpler for complete replacement; BioSURE's restricted policy intentionally withholds some proposals that would equal the reference. A normal diff also displays changes. Neither user time savings nor downstream AI/research accuracy has been measured.

The potential benefit is inspectable change review, bounded decision policy, local batch triage and reproducible records of candidate approval. A complete correct reference can simply be copied, so the paragraph adapter has no demonstrated restoration-accuracy advantage over copying. We have not measured researcher time savings or compared usability against a normal diff viewer. The [practical validation protocol](practical-validation.md) explicitly specifies the missing evaluation and includes direct copying as a baseline.

The tool cannot validate units, doses, treatment labels, figures, biological outcomes, clinical facts or translation quality. It does not authenticate evidence or detect arbitrary unknown defects. All existing data sets are exploratory and have few distinct sources. Domain benefit and integration into actual AI-assisted research workflows remain unvalidated. These limitations constrain the present contribution rather than being solved by the Tool & Platform label.

### 7. Reproduction and release

Python 3.12 and the standard library suffice for replay and the local demo. Pytest is a development dependency. From the standalone root:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python scripts/verify_reproduction.py .
python -m biosure.cli batch --input fixtures/workflow_examples.json --out ../example-results.json
python -m biosure.web_demo
python -m pytest tests -q -p no:cacheprovider
```

The verifier checks all three frozen counts and the full stress summary, and fails on drift. The CLI provides separate full graph-evaluation commands documented in README. Optional article regeneration accesses the official PMC API, but frozen replay is offline. The no-prior export excludes manuscript-related copied code and private aggregate results. A content manifest binds the exported files. MIT applies to the project-authored assets; article derivatives retain CC BY 4.0 notices. Release authorization is recorded in provenance and RIGHTS rather than silently assumed.

Separate competition registration and actual account submission remain owner actions. Confirm the exact closing time/timezone in the official competition interface. Reproducible code, attributed assets, a demonstration and an honest report support evaluation; they do not guarantee eligibility, scientific validity or competitive scoring.

## Sources and attribution

[Official challenge overview](https://www.kaggle.com/competitions/ai-4-s-open-innovation-artificial-intelligence-for-life-scien/overview/url); [PMC OAI-PMH API](https://pmc.ncbi.nlm.nih.gov/tools/oai/); the three linked article records and their CC BY 4.0 notices. This project uses no external learned model or paid inference. Implementation, tests, interface and documentation were developed with OpenAI Codex assistance under the project owner's direction. Generated code was subject to local tests and author self-review, not an independent scientific review. Codex is not a human team member or scientific author.
