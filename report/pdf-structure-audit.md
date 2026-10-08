# Two-column PDF structure audit

**Question.** When a two-column, figure-heavy article PDF is imported, are body paragraphs kept intact and in order, and what interrupts them?

**Method.** `python scripts/audit_pdf_structure.py <dir>` imports each `pdf/<ID>.pdf` with the review-only importer. It then compares the text with that article's own JATS body paragraphs (`xml/<ID>.xml`): paragraphs of at least 200 letters, with figures and tables excluded. Case, spacing, punctuation and digits are ignored, so the comparison measures structure, not glyph fidelity. A paragraph is *intact* if it appears contiguously, *split* if every letter is traced in order with foreign text spliced between, *unverified* if start and end are found but some letters cannot be traced in order (a deletion, reordering or linearised formula is possible), and *lost* otherwise. Order inversions compare paragraph start positions only. An insert counts as *located* when a `PROBABLE_CAPTION_OR_PAGE_FURNITURE` hint names its text. The hint only points to lines; it never removes them. Frozen aggregate: [results/pdf_structure_audit.json](../results/pdf_structure_audit.json).

| Set | Sources | Pages | Paragraphs | Intact | Split | Unverified | Lost | Start-order inversions | Spliced inserts (caption / furniture or other) | Inserts located by hint |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| Development | 5 | 104 | 273 | 220 (80.6%) | 52 | 1 | 0 | 0 | 57 (29 / 28) | 56 |
| Held-out | 10 | 174 | 441 | 345 (78.2%) | 94 | 0 | 2 | 0 | 97 (37 / 60) | 86 before post-hoc fix, 96 after |

## Development set
Five CC BY organ-on-a-chip/MPS papers found by a PMC search on 2026-10-08: PMC12218145 (Commun Biol), PMC12508954 (ACS Omega), PMC12976268 (Nat Commun), PMC13285169 and PMC13334942 (Adv Sci). The hint patterns were written while looking at this set, so its recall is not a validation result.

## Held-out set
Ten CC BY PMC papers acquired earlier for other BioSURE audits: PMC12624441, PMC12707140, PMC12715219, PMC12732092, PMC12755145, PMC12789962, PMC12838518, PMC12838946, PMC12850162, PMC12864593. The first pattern version located **86/97** inserts here. All ten inserts in one ASM paper were missed, because that journal uses uppercase `FIG n` captions and bare-DOI running heads. Both forms were then added, giving 96/97. **The 96 is post hoc on held-out data**; the pre-fix 86/97 is the honest held-out number.

## Findings and limits
- No paragraph *start* appeared out of order, 2 of 714 paragraphs were not found and 1 could not be fully traced (a Codex review attributes this to formula linearisation; not independently confirmed). This does not prove letter-complete paragraphs or correct column order within a paragraph. An earlier version of the audit counted untraceable paragraphs as splits; a Codex review reproduced that defect with a synthetic deletion, which is now a regression test.
- About one paragraph in five is interrupted by a spliced caption, table content, running head, page counter, licence or submission note. This happens mostly at column and page breaks.
- No hint excerpt of 20 or more letters occurred inside any JATS body paragraph in either set. Hints are nonetheless dense (hundreds per set), and the shared 64-hint cap still applies, so reviewers must inspect every page.
- Letter-only matching hides glyph defects such as line-end hyphens and letter spacing; the existing warnings cover those separately. The JATS reference is the same article's markup, adjudicated by one agent. These are 15 convenience-selected sources, not an estimate across publishers.
