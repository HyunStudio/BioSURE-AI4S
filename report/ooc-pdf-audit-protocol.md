# Two-source OoC publisher-PDF audit protocol

The target articles and units were fixed in the private development history
before their publisher PDF text layers were inspected on 2026-10-01. This was
an internal prospective rule, not a public preregistration or independent
validation. The two sources were already known from the earlier constructed
structural probe; no source was replaced based on its PDF quality.

1. Use the first article page of the publisher PDFs for DOI
   [10.1038/s41598-017-08879-x](https://www.nature.com/articles/s41598-017-08879-x.pdf)
   and [10.1038/s41598-020-63710-4](https://www.nature.com/articles/s41598-020-63710-4.pdf),
   in that order. Both articles state CC BY 4.0.
2. Attempt the entire title and entire abstract on that page for each PDF:
   four units, with no cherry-picked error phrases. Keep clean units as controls;
   mark a unit unscorable if it cannot be isolated, without substitution.
3. Extract with pypdf 6.16.2 in plain mode, then apply the project's frozen
   `_normalise_lines` function: NFKC, line-end dehyphenation and whitespace
   collapse. Do not manually repair the observed text. Hash each full PDF and
   record its deterministic title/abstract extraction anchors. The PDFs are
   acquired separately and are not redistributed here.
4. Compare the rendered publisher page and publisher HTML title/abstract to
   transcribe gold. A single development agent did this, so gold is not
   independent truth or expert review. Use the same article as declared
   reference for each case, and report that dependence explicitly.
5. Run the frozen decision stage without gold and then score the sealed
   decisions against separate gold files. Compare BioSURE, direct correct-
   reference copy, normal diff/manual review and review-only learned signals
   on identical inputs. Do not change the gate or model after seeing results.
6. Report all attempted/scorable units and every outcome, including failures.
   Do not pool this two-source audit with the separate post-hoc JHU pilot, or
   infer real-world defect frequency, algorithmic superiority, user benefit,
   independent validation or safe unattended use.

The exact input/gold files and result JSON are in `fixtures/ooc_pdf_*` and
`results/ooc_pdf_*`. Reproduction and optional source-byte verification
commands are in the public README and evidence scorecard.
