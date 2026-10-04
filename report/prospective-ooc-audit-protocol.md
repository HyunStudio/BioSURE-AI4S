# Prospective OoC PDF text-layer audit: locked source selection

Selection lock: **2026-10-04 14:41 Asia/Seoul**, before opening or extracting any of the selected PDF/XML bytes. This is an internal prospective lock by the development agent, not external preregistration or independent expert adjudication. It is a document-QC audit, not an OoC laboratory-outcome experiment.

## Metadata-only search and screening

The official [PMC license filter](https://pmc.ncbi.nlm.nih.gov/about/userguide/) and [PMC Cloud access method](https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/) were used. NCBI ESearch request (`db=pmc`, `retmax=40`, `retmode=json`, `sort=pub date`) used this exact term:

```text
("organ-on-a-chip"[Title/Abstract] OR "microphysiological system"[Title/Abstract]) AND "cc by license"[Filter] AND 2025/01/01:2025/12/31[PubDate]
```

ESearch reported 130 results on 2026-10-04. The date expression defines this API search snapshot; some ESummary display dates are in 2026, so it must not be described as eight articles definitively published in calendar 2025. In returned order, screen *metadata only*: exclude any PMCID in BioSURE's 24-article ML corpus or prior native/structural audit; require a nonempty DOI, a title containing `organ-on-a-chip` or `microphysiological` (case-insensitive), and PMC Cloud version-1 metadata with `license_code=CC BY`, `is_manuscript=false`, `is_retracted=false`, and a nonempty PDF/XML URL. No PDF/text-layer success, discrepancy count, or model output is an eligibility criterion.

The ordered results through the eighth selection, including all exclusions, are:

| ESearch position | PMCID | Pre-PDF metadata disposition |
|---:|---|---|
| 1 | PMC13557687 | Excluded: already in BioSURE ML corpus; title also misses rule. |
| 2 | PMC7619114 | Excluded: `is_manuscript=true`. |
| 3 | PMC13214250 | Excluded: title misses rule. |
| 4 | PMC13093561 | Excluded: title misses rule. |
| 5 | PMC12624441 | Selected, development 1. |
| 6 | PMC12914553 | Excluded: `is_manuscript=true`. |
| 7 | PMC12864593 | Selected, development 2. |
| 8 | PMC12866807 | Excluded: title misses rule. |
| 9 | PMC12850162 | Selected, development 3. |
| 10 | PMC12848640 | Excluded: title misses rule. |
| 11 | PMC12838518 | Selected, development 4. |
| 12 | PMC12838714 | Excluded: title misses rule. |
| 13 | PMC12838946 | Selected, held-out 1. |
| 14 | PMC12822522 | Excluded: title misses rule. |
| 15 | PMC12801197 | Excluded: title misses rule. |
| 16 | PMC12789962 | Selected, held-out 2. |
| 17 | PMC12784959 | Excluded: title misses rule. |
| 18 | PMC12755145 | Selected, held-out 3. |
| 19 | PMC12729921 | Excluded: title misses rule. |
| 20 | PMC12729539 | Excluded: title misses rule. |
| 21 | PMC12727648 | Excluded: title misses rule. |
| 22 | PMC12730911 | Excluded: title misses rule. |
| 23 | PMC12732092 | Selected, held-out 4. |

## Frozen source order and attempted units

All eight deposits were metadata-verified as CC BY, non-manuscript, non-retracted with PDF/XML links. DOI and cloud metadata identity are frozen below; use the exact version-1 objects `https://pmc-oa-opendata.s3.amazonaws.com/<PMCID>.1/<PMCID>.1.json`. PDFs and XML come from the URLs in those objects and are not redistributed. Record actual byte SHA-256 after acquisition; the metadata's MD5 parameter is not a substitute for the observed SHA-256.

| Split | PMCID | DOI |
|---|---|---|
| Development | PMC12624441 | 10.1021/acsptsci.5c00554 |
| Development | PMC12864593 | 10.1002/adhm.202502711 |
| Development | PMC12850162 | 10.1002/smsc.202500154 |
| Development | PMC12838518 | 10.3390/bioengineering13010009 |
| Held-out | PMC12838946 | 10.3390/biomimetics11010018 |
| Held-out | PMC12789962 | 10.1002/adbi.202500225 |
| Held-out | PMC12755145 | 10.1186/s40486-025-00246-0 |
| Held-out | PMC12732092 | 10.3390/cells14241986 |

For every source attempt exactly two units: the full title and full abstract on **article page 1** of the deposited PDF. A repository cover, if any, is not article page 1; determine page mapping from the rendered title page and disclose it. If the complete abstract continues beyond article page 1, if its reading order cannot be isolated without discretionary manual rewriting, or if exact source bytes cannot be acquired, mark that unit unscorable with the cause. Do not replace the source or truncate the unit. Preserve all 16 attempts in the manifest and summary.

Use `pypdf==6.19.0` plain text extraction and BioSURE's frozen `_normalise_lines` (NFKC, preserved line-end hyphens, whitespace collapse). The observed unit must be the actual text layer, not an edited correction. The separate canonical JATS title/abstract and rendered deposited page are the gold-adjudication aids; document any disagreement and version mismatch. A mismatch with canonical continuous text is a **discrepancy**, which may include visible line-wrap hyphen reflow, not necessarily a pypdf-invented glyph. One development agent checks gold, so this is not independent expert truth.

Run the fixed model and gate with all selected records before looking at held-out scoring. Decisions see declared reference and observed text, never gold. Compare BioSURE with direct copying of that same declared reference and ordinary diff/manual review; do not handicap copy. Report attempted/scorable units, controls/discrepancies, exact/incorrect automatic outputs, abstentions and review alerts by source and split. Counts are not deployment rates or measured human time. If development findings motivate a code change, freeze the change before inspecting held-out results and replay all old sets, including forged-reference stress. Retain negative outcomes and the original observations.
