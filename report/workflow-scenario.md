# OoC document conversion QC: concrete workflow

A researcher maintains a text extract of an organ-on-a-chip methods/results record. A conversion step drops one methods paragraph or emits an extra copy. BioSURE checks the converted sequence against a separately supplied reference and proposes one bounded structural change. This is a proposed use case with fictitious project-authored text, not a measured OoC lab incident. The app does not perform the conversion itself.

## Executable example

Choose **Load example** in the app. Four reference paragraphs describe a fictitious assay record, a channel-preparation methods paragraph, a pointer to a measurement record, and an explicit fictitious-data notice. The omission example excludes the second paragraph; the duplicate example includes it twice; the substitution example changes it.

Unique exact paragraph hashes align surviving text to reference IDs. One internal omission with two surviving reference neighbors or one extra identical paragraph produces a candidate. The unchanged v2 gate checks it. Applied output contains actual normalized text and a replayable receipt, not prose reconstructed from hashes. Changed meaning, reordering, multiple faults, repeated reference content and boundary omissions abstain; identical sequences report `NO_CHANGE` without applying a repair.

Whitespace is collapsed before hashing; whitespace-only differences are intentionally ignored. Inputs must have the same language and exact paragraph content, not translations/paraphrases. A PDF text-layer importer can supply unverified page chunks for manual cleanup, but it does not establish paragraph boundaries, figure content or faithful document conversion. DOCX parsing and biological correctness are out of scope.

## Input contract

Save a local JSON with exactly the three fields below, then run `python -m biosure.cli workflow --input paragraph-input.json`:

```json
{"record_id":"conversion-qc","reference_paragraphs":["Alpha","Beta","Gamma"],"observed_paragraphs":["Alpha","Gamma"]}
```

The app invokes the same adapter through POST `/api/workflow`; advanced strict candidate JSON invokes POST `/api/decide`. Neither opens evaluation gold. Limit: 128 paragraphs per input, 4096 characters each, 262144 normalized characters combined; HTTP body 1 MiB. The server processes requests in memory, rejects malformed/duplicate-key JSON and foreign Host/Origin, and emits generic errors without echoing prose. Browser downloads contain your supplied output. Clearing the UI is not secure memory erasure. Do not enter patient data or sensitive records. The local HTTP server is not production hosting.

## Trust and category boundary

The supplied reference is not authenticated or independently adjudicated. False evidence can cause false output. The stress suite demonstrates twelve such errors against unchanged gold. A receipt proves what declared input led to a decision, not biological truth, ownership or fidelity to an official source.

Whole-graph evidence reconstruction ties BioSURE on the original synthetic/article sets. On stress it produces twelve more exact outputs because it lacks the gate's global conflict veto; both methods apply all forged-reference candidates incorrectly. No superiority or novel AI capability follows from these counts. The local draft category is now Tool & Platform, not an account submission change.

## Batch triage and review

`python -m biosure.cli batch --input fixtures/workflow_examples.json --out workflow-results.json` triages six fictional records: two corrections, one unchanged record and three manual reviews. Output must be a new file; an existing file is never overwritten. Inputs remain unchanged. Invalid records or duplicate IDs reject the whole batch before writing. Maximum 100 records and 8 MiB input JSON; per-record limits are unchanged.

`review_changes` reports normalized differences with zero-based half-open spans. The UI displays paragraph positions. Previews do not infer meaning or override abstention. A correct complete reference can instead be copied; no measured advantage over copying or a normal diff viewer is established.

See the [submission report](public-submission.md), [practical validation boundary](practical-validation.md) and [rights inventory](../RIGHTS.md).
