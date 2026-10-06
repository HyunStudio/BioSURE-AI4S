# Owner actions before an AI4S submission

This is a preparation checklist, not evidence of first-place readiness. BioSURE
is a one-person HyunStudio team led by HyunGi Hwang. The study runner is a
future external-usability tool, **not a submission prerequisite**. No volunteer,
independent adjudicator, registration or Kaggle Writeup has been completed by
this file. Codex/GPT are development tools, not teammates or validators.

The [official AI4S page](https://www.kaggle.com/competitions/ai-4-s-open-innovation-artificial-intelligence-for-life-scien/overview)
lists the preliminary round through **October 10, 2026** and says a separate
registration form is required *before* the official Kaggle Writeup; an
unregistered team is ineligible for judging and awards. Confirm the exact
closing clock and timezone in the signed-in Kaggle interface and submit early.
Only the owner can decide to register and submit; this checklist does not do so.

## Owner-only submission actions

| Block | Owner action and evidence to retain privately |
|---|---|
| 0–10 min | **OWNER ACTION:** Verify the official closing clock, complete the separate registration form if proceeding, and confirm HyunStudio / HyunGi Hwang as the one-person team. Do not assume a GitHub release is a Kaggle submission. |
| 10–20 min | Open the [public code release](https://github.com/HyunStudio/BioSURE-AI4S/releases/latest), [live browser trial](https://hyunstudio.github.io/BioSURE-AI4S/try/) with non-confidential text and a PDF text layer, [v0.3.23 MP4 download](https://github.com/HyunStudio/BioSURE-AI4S/releases/download/v0.3.23/biosure-demo-v0322.mp4), [streaming watch page](https://hyunstudio.github.io/BioSURE-AI4S/), [Judge Mode](https://hyunstudio.github.io/BioSURE-AI4S/judge/) and [study instrument](https://hyunstudio.github.io/BioSURE-AI4S/study/) without login. The unchanged v0.3.22 recording shows actual browser text/PDF inputs ending in abstention and distinguishes one static Judge case; v0.3.23 fixes in-page playback. The older v0.3.19 and v0.3.14 recordings are historical. |
| 20–30 min | Check the public report and scorecard against the exact released code, video and result files. Preserve the negative learned comparison and natural-case abstentions. Do not claim a participant study or independent domain review. |
| 30–40 min | **OWNER ACTION:** Finalize the official Kaggle Writeup with category `Tool & Platform`, public video/code/report links, one-person team information and accurate AI-tool disclosure, then submit it in Kaggle. Confirm receipt in the account interface. |

External participants, domain adjudication and a cross-disciplinary team bonus
are optional future opportunities, not eligibility gates or completed evidence.
Do not add students, Codex/GPT or outside advisers as team members. A solo
automated rehearsal is a software test, not a participant result.

## Optional exploratory usability pilot

If there is time and an appropriate consent/ethics route, an anonymous student
pilot may be run **after** the submission package is ready. It is not a
submission prerequisite and is not biological or clinical validation. The
minimum balanced schedule uses three volunteers with **slots 0, 1 and 2**
once each; each case then appears once in each view. Six volunteers with slots
0–5 repeat each case/view twice. Neither sample supports significance,
superiority or population claims. Report denominators, counts, medians, ranges
and individual cases only, including null or unfavorable findings.

Copyable invitation, sent individually with one distinct slot number (do not
put a name, email, major or other identifier in the JSON):

> Optional anonymous UI pilot: open https://hyunstudio.github.io/BioSURE-AI4S/study/ and select assignment slot **N** from the dropdown. Review the nine fixed tasks, download the JSON at the end, and return only that file privately. Participation is voluntary; you may stop at any time. Do not enter personal, patient or confidential information. This tests an interface, not biological expertise.

Replace **N** with 0, 1 or 2 for the minimum schedule; add 3, 4 and 5 only
if available. Decide consent/ethics requirements before inviting anyone.
Keep any exports and withdrawal count outside the public repository. An absent
file does not itself prove withdrawal. Exact duplicate exports can be detected;
repeat participation with changed answers/times cannot be detected without
identifiers. Public article-title accuracy remains **unscored** without a
genuinely independent domain key; the declared JATS/reference is not that key.

## Local analysis command

From the standalone source root, with Python 3.12 and three optional files held
privately:

```powershell
python scripts/analyze_study.py --manifest docs/study/manifest.json --sessions private-session-0.json private-session-1.json private-session-2.json --out private-summary.json
```

Add files for slots 3, 4 and 5 if present. Add `--key` only for a separately
held and documented answer key. Add `--withdrawals N` only for an
owner-observed count. The analyzer refuses malformed, partial and duplicate
sessions and will not overwrite an existing output. It reports counts,
median/min/max active-tab and wall time, and keyed accuracy only where the
separate key permits it; neither time measure alone proves working time.

The key has schema `biosure.practical-study-key/1.0`, the manifest SHA-256 and
an `answers` object keyed by task ID. Each answer declares `difference`
(`yes`/`no`), optional zero-based `first_changed_reference_position`, and
`basis` (`fictional-author-key`, `independent-adjudication`, or
`source-derived`). For a public article, only an explicitly declared
`independent-adjudication` basis is scored. This declaration is not proof of
who performed adjudication. Do not publish the key or raw exports.

Practical superiority would require appropriate external evidence, but such
evidence is **not required to submit this honest solo prototype**. Until it
exists, the accurate statement is that the optional instrument has **zero
participants** and no independent natural-source answers.
