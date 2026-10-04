# English caption transcript (silent video; no recorded audio)

1. BioSURE v0.3.14 is an offline workbench for comparing organ-on-chip research PDF extractions with article text. It creates an evidence packet for human approval, not biological validation.
2. The real public example is Kim et al., PMC12864593, DOI 10.1002/adhm.202502711, CC BY 4.0. The declared reference is JATS and the observed input is pre-extracted PDF text; neither is authenticated by the app.
3. The ordinary difference and expandable before/after views expose changed locations and literal text. In the locked eight-source audit there were 11 observed/JATS discrepancies and zero automatic repairs.
4. The fitted matcher abstains on the selected real source because of LOW_CONFIDENCE. Overall model ranking was 14/16; `difflib` and token Dice each ranked 16/16. Held-out ranking was 7/8 versus 8/8 for both lexical comparators.
5. A fictional missing-paragraph control receives one bounded edit. The proposed output is marked SOURCE UNVERIFIED and displayed with a SHA-256 decision receipt; it is not written to a source file.
6. A receipt is traceable, not an authenticator. A forged declared reference can still lead to a false result.
7. The app's evidence card reports the fixed evaluation. The caption also states that the release ZIP reproduced, 296 Python and 22 Node tests passed, and both CI operating-system jobs passed as of recording. Those checks establish package behavior, not independent scientific validity.

The published video is silent and uses project-authored explanatory overlays. Browser automation records actual app responses only; it is not a human-use or speed study. Source credit, modifications and limits appear in RIGHTS and the public scorecard.
