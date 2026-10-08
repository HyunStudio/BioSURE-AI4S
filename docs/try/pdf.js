/* PDF bytes stay in this browser. Extracted text is unverified page text. */
(function () {
  'use strict';

  // Keep these conservative line patterns aligned with biosure/pdf_extract.py.
  const CAPTION_START = /^(?:FIGURE|Figure|FIG|Fig\.?|TABLE|Table|Scheme|SCHEME)\s*\p{Nd}+[A-Za-z]?\s*(?:[|.:]|\s+[A-Z(])/u;
  // Python's \d and \b are Unicode-aware; JS's defaults are not.
  const PAGE_FURNITURE = /^\p{Nd}{1,3}\s?of\s?\p{Nd}{1,3}(?![\p{L}\p{N}_])|(?<![\p{L}\p{N}_])\p{Nd}{1,3}\s?of\s?\p{Nd}{1,3}$|^(?:Received|Accepted|Published|Revised)(?![\p{L}\p{N}_])|Creative Commons|(?<![\p{L}\p{N}_])10\.\p{Nd}{4,9}\/\S+\s+\p{Nd}{1,3}$|Check for updates|https?:\/\/doi\.org\/|^©|\(\p{Nd}{4}\)\s*\p{Nd}+:\p{Nd}+|^(?:Article\s*)?https?:\/\/|^www\./u;
  const MAX_REVIEW_HINTS = 64;

  function furnitureHints(chunk, page) {
    return chunk.split(/\r\n?|\n/).map(line => line.trim()).filter(Boolean)
      .filter(line => CAPTION_START.test(line) || ([...line].length <= 160 && PAGE_FURNITURE.test(line)))
      .map(line => ({page, kind: 'PROBABLE_CAPTION_OR_PAGE_FURNITURE', excerpt: [...line].slice(0, 120).join('')}));
  }

  async function extractPdf(file, pdfjs) {
    if (!file || !Number.isSafeInteger(file.size) || file.size < 1 ||
        typeof file.arrayBuffer !== 'function') {
      throw new Error('Choose a non-empty PDF file.');
    }
    if (file.size > 16 * 1024 * 1024) throw new Error('PDF must be at most 16 MiB.');
    if (!pdfjs || typeof pdfjs.getDocument !== 'function') {
      throw new Error('PDF text extraction is unavailable in this browser.');
    }

    let task;
    try {
      const data = new Uint8Array(await file.arrayBuffer());
      if (data.byteLength !== file.size) throw new Error('PDF file changed while reading.');
      task = pdfjs.getDocument({ data });
      const pdf = await task.promise;
      if (!Number.isSafeInteger(pdf.numPages) || pdf.numPages < 1) {
        throw new Error('PDF has no readable pages.');
      }
      if (pdf.numPages > 32) throw new Error('PDF must be at most 32 pages.');
      const chunks = [];
      const hintsByPage = [];
      let extractedLength = 0;
      const warnings = ['UNVERIFIED_PAGE_TEXT'];
      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber++) {
        const page = await pdf.getPage(pageNumber);
        const content = await page.getTextContent();
        const parts = [];
        if (pageNumber > 1) extractedLength += 2;
        for (const item of content.items || []) {
          if (typeof item.str !== 'string') continue;
          if (item.str) { parts.push(item.str); extractedLength += item.str.length; }
          if (item.hasEOL) { parts.push('\n'); extractedLength++; }
          else if (item.str) { parts.push(' '); extractedLength++; }
          if (extractedLength > 262144) throw new Error('PDF extracted text exceeds 262144 characters.');
        }
        const chunk = parts.join('').trim();
        if (!chunk) warnings.push(`NO_TEXT_ON_PAGE_${pageNumber}`);
        chunks.push(chunk);
        hintsByPage.push(furnitureHints(chunk, pageNumber));
      }
      if (!chunks.some(Boolean)) throw new Error('PDF has no usable text layer; OCR or manual transcription is required.');
      const review_hints = [];
      for (let offset = 0; review_hints.length < MAX_REVIEW_HINTS; offset++) {
        let added = false;
        for (const pageHints of hintsByPage) {
          if (offset < pageHints.length) {
            review_hints.push(pageHints[offset]);
            added = true;
            if (review_hints.length === MAX_REVIEW_HINTS) break;
          }
        }
        if (!added) break;
      }
      if (hintsByPage.some(pageHints => pageHints.length)) {
        warnings.push('CAPTION_OR_PAGE_FURNITURE_REQUIRES_REVIEW');
      }
      if (hintsByPage.reduce((count, pageHints) => count + pageHints.length, 0) > MAX_REVIEW_HINTS) {
        warnings.push('REVIEW_HINTS_TRUNCATED');
      }
      review_hints.sort((left, right) => left.page - right.page);
      return { text: chunks.join('\n\n'), pages: pdf.numPages, warnings, review_hints };
    } catch (error) {
      if (/^(PDF must|PDF has|PDF file changed)/.test(error.message)) throw error;
      throw new Error(`Could not read PDF text layer: ${error.message}`);
    } finally {
      if (task && typeof task.destroy === 'function') await task.destroy();
    }
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { extractPdf };
  if (typeof window !== 'undefined') window.BioSurePdf = { extractPdf };
})();
