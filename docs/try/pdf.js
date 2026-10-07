/* PDF bytes stay in this browser. Extracted text is unverified page text. */
(function () {
  'use strict';

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
      }
      if (!chunks.some(Boolean)) throw new Error('PDF has no usable text layer; OCR or manual transcription is required.');
      return { text: chunks.join('\n\n'), pages: pdf.numPages, warnings };
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
