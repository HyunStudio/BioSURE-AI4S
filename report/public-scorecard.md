# BioSURE AI4S evidence scorecard — 2026-10-01

This maps evidence to the [official AI4S evaluation dimensions](https://www.kaggle.com/competitions/ai-4-s-open-innovation-artificial-intelligence-for-life-scien/overview/url). Percentages are judging weights, **not** self-awarded scores. Category recommendation remains **Tool & Platform**: the tested contribution is an offline review workbench and bounded decision interface, not a demonstrated superior model or laboratory outcome.

| Official dimension | Weight | Evidence available | Material gap |
|---|---:|---|---|
| Problem Importance & Potential Impact | 30% | Inspectable reference-conditioned document QC for research-support inputs; [workflow](workflow-scenario.md). | No measured OoC laboratory impact, downstream scientific error reduction or researcher time saving. |
| Technical Approach & Innovation | 30% | Candidate-specific structural gate, explicit abstention, receipts, trained review-only logistic matcher; [technical report](public-submission.md). | Equal-evidence reconstruction ties the first two probes. Learned matching ties strong lexical baselines on constructed queries; novelty/superiority is unproved. |
| Results & Validation | 20% | Frozen [structural results](../results/stress_summary.json), [ML results](../results/ml_evaluation.json), and [one-source native PDF pilot](../results/native_pilot.json). | Pilot is post-hoc selected and agent-adjudicated; no independent expert, multiple native-error sources, blinded user study or deployment error rate. |
| Reproducibility & Implementation Quality | 10% | Public offline code, frozen fixtures/model/results, two-step gold-separated pilot, a [source-PDF text-layer verifier](../scripts/verify_native_source.py), and tests; [README](../README.md). | The PDF is not packaged; source acquisition and visual-gold adjudication remain external. Content hashes cannot authenticate scientific truth. |
| Presentation Quality | 10% | [4:48 captioned demo](https://hyunstudio.github.io/BioSURE-AI4S/) shows actual UI states and the PDF failure warning. | Silent montage, not a continuous use/time study; it predates this pilot, and small on-screen detail limits communication. |

## Real extraction-error pilot — deliberately small

The PDF/text source is Tward et al., [DOI 10.1038/s41467-025-65317-7](https://doi.org/10.1038/s41467-025-65317-7), [PMCID PMC12645051](https://pmc.ncbi.nlm.nih.gov/articles/PMC12645051/), CC BY 4.0. The public [eScholarship full-PDF download](https://escholarship.org/content/qt8cc3z8ph/qt8cc3z8ph.pdf) has a repository cover: article page 1 is file page 2. The two-page excerpt begins at article page 1. Both locked PDF hashes, the pypdf 6.16.2 procedure, post-hoc selection and modified short text are recorded in [inputs](../fixtures/native_pilot_inputs.json). A separately stored [gold transcription](../fixtures/native_pilot_gold.json) was checked by one agent against rendered PDF and official JATS. This is not independent domain-expert adjudication. One title control and two actual article-page-1 text-layer errors come from **one article**, not three independent documents. The PDF, XML and figures are not distributed.

The decision command accepts inputs and a frozen model, **no gold argument**. It writes its decision file before the score command opens gold. The scorer checks the input and decision digests and case IDs. These hashes catch accidental switching or modification, but cannot prove authorship or prevent a person from recomputing a false fixture.

| Same three records | Exact automatic | Incorrect automatic | Abstentions | Native-error records needing review |
|---|---:|---:|---:|---:|
| BioSURE bounded workflow | 0 | 0 | 3 | 2/2 |
| Direct declared-reference copy | 3 | 0 | 0 | 0/2 |
| Normal diff / manual review | 0 | 0 | 3 | 2/2 |

The title control accounts for one of copy's three exact outputs. On the **two actual extraction-error records**, direct copy restores both when its reference is correct; BioSURE restores neither automatically. The diff exposes both discrepancies but writes no output. “Needs review” is a record count, **not measured time**. No policy demonstrated a comparative restoration or labor advantage here. The PDF-import figure-label loss remains outside this text-only scoring task.

The learned correspondence model is **not an independent error detector** in this pilot. Its previous `REVIEW` count inherited the diff's changed/not-changed flag, so that count has been removed. Both erroneous one-paragraph records have above-threshold match scores (0.981 and 0.938), and only the body record has lexical number/unit flags, potentially from citation and spacing artifacts. The title also matches above threshold. One reference per record makes ranking trivial. The model authorizes zero repairs, and these signals cannot be called 1/2 detection sensitivity or a model advantage.

To reproduce from the standalone root with Python 3.12, choose fresh output names:

```powershell
python scripts/evaluate_native_pilot.py decide fixtures/native_pilot_inputs.json fixtures/ml_model.json pilot-decisions.json
python scripts/evaluate_native_pilot.py score pilot-decisions.json fixtures/native_pilot_gold.json pilot-results.json
python scripts/verify_reproduction.py .
```

For source-to-fixture provenance, independently obtain the public full PDF from the article source, then run `python scripts/verify_native_source.py path/to/full-paper.pdf`. The command requires the frozen full-PDF SHA-256, extracts its article page 1 (file page 2), and confirms all three observed strings occur there. It also accepts the locked two-page excerpt (article page 1 is file page 1). It does **not** check visual truth, gold, random selection, or article licensing. The PDF itself is deliberately not in the ZIP; an arbitrary same-title PDF with different bytes will fail the hash check.

## Reference-trust failure boundary

The authored stress test applies 36 candidates, of which **12 are wrong**: all twelve are forged-reference controls across twelve project-authored graphs. The strong whole-graph reconstruction comparator also fails those twelve. The denominator is a deliberately balanced test, **not** a real-world 12/36 error probability. The new native pilot does not resolve this vulnerability; direct copying would also be unsafe with a false reference.

**Precondition for any automatic use:** a responsible operator must independently establish the reference's provenance, version and exact document scope against the original authorized source before allowing its evidence into the workflow. If that cannot be established, leave the record in manual review; do not treat a digest, user acknowledgement, retrieval URL or this app's receipt as source authentication. The current API does not enforce that external check, so the present package is not safe as an unattended production repair service.

## Go / No-Go

**Go:** transparent Tool & Platform prototype submission, with the frozen results and all limits visible. **No-Go:** claim of first-place competitiveness, learned superiority, validated natural-error performance, clinical or OoC impact, expert endorsement, or safe unattended automatic correction. A stronger claim needs several independently selected native-error sources, adjudicators independent of development, same-input timed user comparison, and a verified reference-provenance workflow. No such study is claimed here.
