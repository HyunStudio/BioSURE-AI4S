# BioSURE evidence-first competition improvement

Date: 2026-10-04 (Asia/Seoul)

## Intent and boundary

Improve BioSURE's AI4S Tool & Platform submission by adding stronger, honest evidence before the 2026-10-10 preliminary deadline. The owner wants work to continue in this task without repeated approval pauses. Registration and final Kaggle submission remain owner-only and out of scope. A win, superior algorithm, reduced researcher time, independent expert validation, or safe unattended repair must not be claimed without matching evidence.

Current evidence is limited: the learned matcher ties lexical baselines on constructed held-out pairs; BioSURE automatically restores 0/2 selected JHU native PDF errors, 0/2 in the older two-source OoC audit, and 0/3 discrepant units in the newer three-source audit. A correct-reference copy is exact on those small audits. The authored forged-reference stress set includes 12 incorrect automatic applications. The public video predates v0.3.10 spacing suggestions. These facts are baselines, not targets to conceal.

## Approaches considered

1. Presentation only: refresh video and copy. Fast, but does not address the 30% technical and 20% validation criteria.
2. New ML/DL model: potential novelty, but too much training, rights, and held-out evaluation risk before the deadline; DL is reserved for later CHI-Bench work.
3. **Selected: evidence-first evaluation plus contingent targeted product improvement.** Lock a fresh source-selection protocol; execute the existing gold-separated pipeline on every attempted unit; compare same-input copy, diff, deterministic gate, and review-only signals. Only change algorithmic behavior if a development defect is reproducible and a separate held-out set shows a gain without hidden regressions. Refresh public claims and video after the measured result is known.

## Scope and architecture

This is one narrow validation subsystem, not an end-to-end OoC analysis platform. Existing `biosure.native_pilot.decide_inputs` and `score_decisions` remain the single-source decision/scoring primitives. A new aggregate runner consumes a locked manifest of source IDs, preselected unit attempts, input paths, gold paths and status per unit. It validates source identity and input bytes, then runs all decisions without opening any gold bytes; only afterward does it verify gold digests and score. It writes immutable decisions and summary to a fresh output directory only after successful scoring. It produces machine-readable attempted/scorable/source counts and method-level outcomes, including zero and unscorable cases. It refuses duplicate IDs, missing rights/provenance, stale digests, overwritten output, omitted locked sources, or a condition label inconsistent with gold.

Source acquisition and visual transcription stay explicit human/agent tasks. The manifest records DOI/PMCID, license, document version, PDF/XML URL and byte hashes, page-selection rule, extractor version, unit locators, and whether gold was checked against rendered pages. A hash confirms the bytes used, not reference truth. Source PDFs/XML are not redistributed unless rights and provenance are separately cleared. No source may be replaced because its extraction or results are unfavorable. If a unit is unavailable or unscorable, the attempt and reason remain in the denominator and output.

Selection: target eight previously unused, openly licensed OoC papers not in the 24-article ML corpus or earlier audits: four development sources and four held-out sources, assigned by frozen source order. Freeze the exact public metadata query, search timestamp, ordering, metadata-only eligibility exclusions, and first-page title/abstract unit rule in a committed protocol **before inspecting selected PDF text layers**. Do not exclude a chosen paper after inspecting its PDF; an unavailable PDF or non-extractable unit stays attempted/unscorable. If fewer than eight metadata-eligible sources exist, report the shortfall rather than substitute opportunistically. The default unit task is title/abstract text-layer discrepancy triage; a structurally different task must not be pooled into its metrics.

Data flow: fixed protocol -> metadata/license screening -> manifest lock -> exact source acquisition -> observed extraction and separately recorded visual/JATS gold -> gold-blind decisions -> sealed scoring -> aggregate report -> source-level test and public presentation. The runner must not access network or hidden gold during decisions. New model or gate changes, if any, require a new version and full replay of old and new sets, including the forged-reference stress set.

## Outcomes and acceptance criteria

Report each attempted source and unit, scorable status, control versus native discrepancy, exact and incorrect automatic outputs, abstentions, diff review flags, and learned lexical alerts. Copy must receive the same declared reference; it must not be handicapped. Report baseline-relative differences and source-level uncertainty where defensible, with no significance claim from tiny samples. Do not pool the new audit with earlier post-hoc/development audits as independent observations.

The first deliverable is a locked protocol and runnable aggregate evaluation with adversarial tests for omission, duplicate IDs, digest mismatch, bad gold, unscorable attempts and output overwrite. The second is a complete audit on all eligible selected sources, even if BioSURE loses or every case abstains. Only measured improvements may be promoted to the report and refreshed video. Documentation must prominently separate functional tests, constructed benchmarks, native PDF observations, and actual human-use or biological evidence.

Windows and Ubuntu Python/Node suites, reproduction verifier, release manifest, and public-link checks must pass before publishing. Video must show actual current-version operation and disclose review-only suggestions, automation, and version. Publication of any new release must use a new tag and matching archive/manifest; existing tags are immutable.

## Explicit limitations and stop rules

One developer adjudicating rendered pages is not independent expert validation. No timed review benefit can be inferred from automation. If no independent reviewer becomes available, keep winner-readiness No-Go unless new evidence genuinely changes that conclusion. Never claim a positive result by dropping failures, changing a source after extraction inspection, or conflating correct-reference copying with a weaker comparator. The owner controls registration, contact data, and final Writeup submission.
