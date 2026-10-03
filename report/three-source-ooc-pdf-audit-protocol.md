# Three-source cross-publisher OoC PDF audit protocol

Fixed on 2026-10-03 (Asia/Seoul) before inspecting the selected PDF text
layers. This is an internal prospective selection, not external preregistration
or independent scientific adjudication. The papers are absent from the frozen
24-article learned-matcher corpus and the earlier three-source structural
probe. Do not replace a paper because its PDF is difficult to obtain or its
extraction is unfavorable.

## Locked sources and units

In this order, attempt the complete article title and complete abstract on
article page 1 of each version-of-record publisher PDF:

1. Wang et al., *An eighteen-organ microphysiological system coupling a
   vascular network and excretion system for drug discovery*, Microsystems &
   Nanoengineering (2025), DOI
   [10.1038/s41378-025-00933-3](https://www.nature.com/articles/s41378-025-00933-3).
   PMCID PMC12078732. Publisher states CC BY 4.0.
2. Kanioura et al., *An Organ-on-a-Chip Modular Platform with Integrated
   Immunobiosensors for Monitoring the Extracellular Environment*,
   Micromachines (2025), DOI
   [10.3390/mi16070740](https://www.mdpi.com/2072-666X/16/7/740).
   PMCID PMC12300027. Publisher PDF states CC BY 4.0.
3. Liu et al., *Leaf-vein-inspired multi-organ microfluidic chip for modeling
   breast cancer CTC organotropism*, Frontiers in Oncology (2025), DOI
   [10.3389/fonc.2025.1602225](https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2025.1602225/full).
   PMCID PMC12158725. Publisher states CC BY.

Six units are attempted. A unit that cannot be isolated in full from article
page 1 is marked unscorable, with the reason retained; it is not replaced by
an easier sentence or another paper. The PDFs are obtained separately and are
not redistributed. Record publisher URL, acquisition path, SHA-256, page
mapping, `pypdf` version and deterministic extraction anchors before scoring.
Acquire the deposited version-1 PDFs through the [official PMC Cloud
Service](https://pmc.ncbi.nlm.nih.gov/tools/pmcaws/), using each PMCID's
`PMC<id>.1/PMC<id>.1.json` metadata and `pdf_url`. At protocol lock, all
three metadata objects identify the listed DOI, `is_manuscript=false`,
`is_pmc_openaccess=true`, `is_retracted=false` and `license_code="CC BY"`.
If a deposited PDF differs from the publisher's version of record, retain
the attempted unit and disclose the version mismatch rather than substitute
a more favorable PDF.

Post-lock source check (2026-10-03): the [Frontiers publisher PDF](https://www.frontiersin.org/journals/oncology/articles/10.3389/fonc.2025.1602225/pdf)
has the same SHA-256 as the PMC Cloud deposit. The attempted Nature `.pdf`
URL returned HTML rather than PDF, and the MDPI `/pdf` URL returned HTTP 403
in this environment. Consequently byte identity with publisher-hosted files
is **unverified for Nature and MDPI**. The scored source is explicitly the
frozen PMC Cloud deposit, not an asserted byte-identical publisher download;
all three selections and attempted units remain unchanged.

## Frozen decision and comparison

Use pypdf plain extraction and the v0.3.4 importer normalization (NFKC,
preserved line-end hyphen glyphs, whitespace collapse) without manually fixing
observed text. Compare rendered publisher page and publisher HTML to transcribe
gold; record any discrepancy between those sources. One development agent
adjudicates the gold, so this is not an independent expert study. Keep input
and gold files separate and run the existing decision stage before scoring.

On the same units compare BioSURE's bounded automatic output, direct copy from
the correct declared reference, ordinary diff/manual review and the frozen
review-only learned signals. Verify that labels of `control` versus
`native_extraction_error` agree with observed text versus gold. Do not train,
retune, or choose another model/gate based on these results. If an importer or
evaluation defect is discovered, preserve the original observation and explain
the correction before replaying all locked sources.

Report all attempted and scorable units, controls, actual text-layer errors,
automatic exact/wrong results, abstentions and review alerts. Do not pool these
sources with earlier pilots as if observations were independent: source and
gold still refer to the same articles, and no researcher task time or
downstream biological outcome is measured. A negative or zero-error result is
valid and must remain visible.
