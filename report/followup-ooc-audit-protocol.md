# Follow-up OoC source audit: selection lock

Selection lock: **2026-10-04 23:05 Asia/Seoul**, before opening or downloading either selected PDF/XML content. This is an internal development-agent lock, not external preregistration, independent gold adjudication, or a claim of OoC laboratory impact. It follows the earlier eight-source audit without tuning the v0.3.14 model or gate to those eight sources.

The official NCBI ESearch snapshot used `db=pmc`, `retmax=60`, `retmode=json`, `sort=pub date` and this exact query:

```text
("organ-on-a-chip"[Title/Abstract] OR "microphysiological system"[Title/Abstract]) AND "cc by license"[Filter] AND 2025/01/01:2025/12/31[PubDate]
```

ESearch returned 130 hits on 2026-10-04. Starting immediately after position 23, the last entry screened for the earlier audit, select the **next two** deposits whose ESummary title literally contains `organ-on-a-chip` or `microphysiological` (case-insensitive), whose ESummary DOI is nonempty, which were not in the prior ML/training/native audits, and whose version-1 PMC Cloud metadata reports `license_code=CC BY`, `is_manuscript=false`, `is_retracted=false`, and nonempty PDF and XML URLs. Metadata-only dispositions through the second selection:

| ESearch position | PMCID | Metadata disposition |
|---:|---|---|
| 24 | PMC12715219 | Selected 1; title contains `organ-on-a-chip`, DOI and eligible Cloud metadata present. |
| 25 | PMC12711516 | Excluded: title says `vascular-on-a-chip`, not either literal title keyword. |
| 26 | PMC12713709 | Excluded: title says `Vessel-on-a-Chip`, not either literal title keyword. |
| 27 | PMC12711315 | Excluded: title lacks either literal title keyword. |
| 28 | PMC12707140 | Selected 2; title contains `organ-on-a-chip`, DOI and eligible Cloud metadata present. |

Selected, frozen identities:

| Order | PMCID | DOI | Article title |
|---:|---|---|---|
| 1 | PMC12715219 | 10.1038/s41598-025-30612-2 | Effect of microbubble-assisted gemcitabine delivery with repeated ultrasound exposure in a pancreatic cancer organ-on-a-chip model. |
| 2 | PMC12707140 | 10.1128/iai.00346-25 | Comparison of cytokine responses to group B Streptococcus infection in a human maternal-fetal interface organ-on-a-chip system and ex vivo culture model of human gestational membranes. |

For each source use only the PDF/XML URLs in its `https://pmc-oa-opendata.s3.amazonaws.com/<PMCID>.1/<PMCID>.1.json` metadata. Record actual bytes and hashes; do not redistribute the full PDF/XML. Attempt the full title and full abstract from **article page one** of the deposited PDF, using pypdf 6.19.0 plain extraction and the frozen BioSURE NFKC/line normalizer. If the whole abstract is not on page one, text-layer order cannot be isolated without rewriting, or exact bytes cannot be acquired, retain an unscorable unit and reason; do not substitute another source or truncate it. Use continuous same-article JATS title/abstract as declared reference and scoring target, with one-agent rendered-page boundary check disclosed. A discrepancy can be typography or reflow, not necessarily an invented parser glyph.

The decisions phase receives only reference and observed text, never gold. Score afterward with the frozen v0.3.14 gate/model. Compare direct correct-reference copying, ordinary diff and `difflib`/token Dice rankings on identical units. Report all four attempts and every failure, including zero-error or unscorable outcomes. No tuning or source replacement is allowed after content inspection. This small follow-up cannot establish source truth, independent validation, restoration superiority or saved researcher time.
