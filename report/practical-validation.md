# Practical validation: evidence and remaining work

## What is actually demonstrated

Six project-authored fictional inputs in `fixtures/workflow_examples.json` exercise actual paragraph text, not only graph hashes. Offline replay gives two bounded automatic corrections, one unchanged record and three manual-review records (substitution, boundary omission and repeated-reference ambiguity). Browser checks show applied text, review positions, receipt export and stale-result clearing. Batch triage avoids writing a replacement for every record and preserves the submitted input file. These checks establish implementation behavior only.

No researcher study, naturally occurring extraction incident, time-saving measurement or independent reference adjudication has been conducted. The examples must not be described as a lab validation set, and record count must not be presented as independent article count.

## The simple alternative must remain visible

When a complete correct reference is already available, copying that reference reconstructs the desired text directly. BioSURE cannot claim a restoration-accuracy advantage over that alternative in its paragraph workflow. Its potential tool value is the explicit difference review, a restricted apply/abstain policy, batch triage and reproducible decision records. Whether this saves time compared with a normal diff viewer or improves downstream research work is unmeasured.

The graph interface can inspect externally proposed edits without reconstructing source prose. Its strong comparator builds complete candidate graphs from the same evidence and ties the gate on two exploratory sets. This further prevents an algorithmic superiority claim. Using evidence created by the same system is not independent verification.

## Protocol for a real workflow evaluation

This is a protocol for future data collection, not a report of completed participants.

1. Obtain non-confidential, redistributable OoC research-document extracts and record the licensed canonical source. Preserve the extraction output before looking at defects. Record natural and injected faults separately.
2. Have a reviewer not responsible for generation adjudicate expected paragraph order and content. Lock references and record their provenance before testing repair candidates. Keep disagreement cases rather than filtering them out.
3. Compare manual side-by-side review, a normal paragraph diff, direct reference copying and BioSURE on the same records. Randomize task order. If full copying is not appropriate, record the reason before evaluation, not after seeing scores.
4. Measure verified final-output agreement, incorrectly applied edits, unresolved defects, elapsed active review time, and the number of records requiring intervention. Report every denominator, source count and withdrawal.
5. Collect task-specific feedback from actual users. Do not infer scientific or clinical utility from interface satisfaction. Report negative results and ties.

Use independent sources for a confirmatory run. Human participation, access to lab records, ethics/consent obligations and rights must be resolved by the owner before collection. Do not manufacture elapsed-time or preference data to satisfy the deadline.

## Minimum defensible submission claim

"An offline, inspectable structural-integrity workbench for a bounded paragraph conversion task, with candidate-specific evidence checks, batch triage, receipts and an explicitly measured forged-reference failure boundary."

Not defensible: "clinically safe", "authenticates source truth", "new state-of-the-art AI", "validated in OoC laboratories", "saves researchers a measured percentage of time", or "the tests establish general real-world error control".
