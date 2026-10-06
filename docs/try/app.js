/* Live, local-browser review. Python runs in a Web Worker; inputs are never posted to a server. */
(function () {
  'use strict';

  const PDFJS_URL = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.mjs';
  const PDFJS_WORKER_URL = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.10.38/build/pdf.worker.mjs';
  const OUTPUT_IDS = ['view-reference', 'view-observed', 'changes', 'model', 'proposal',
    'gate-action', 'selected', 'receipt'];

  function prepareInput(referenceText, observedText) {
    function parse(text, label) {
      if (typeof text !== 'string' || !text.trim()) throw new Error(`${label} text is required.`);
      const pieces = text.replace(/\r\n?/g, '\n').trim().split(/\n\s*\n/);
      if (pieces.length > 128) throw new Error(`${label} must have at most 128 paragraphs.`);
      return pieces.map(piece => {
        if (piece.length > 4096) throw new Error(`${label} paragraphs must be at most 4096 characters.`);
        const normalized = piece.replace(/\s+/g, ' ').trim();
        if (!normalized) throw new Error(`${label} paragraphs must be nonempty.`);
        return normalized;
      });
    }
    const reference = parse(referenceText, 'Reference');
    const observed = parse(observedText, 'Observed');
    if (reference.concat(observed).reduce((sum, part) => sum + part.length, 0) > 262144) {
      throw new Error('Combined paragraph text exceeds 262144 characters.');
    }
    return { record_id: 'browser-trial', reference_paragraphs: reference,
      observed_paragraphs: observed };
  }

  function makeWorkerRunner(worker) {
    let sequence = 0;
    const pending = new Map();
    worker.onmessage = event => {
      const { id, result, error } = event.data || {};
      const handlers = pending.get(id);
      if (!handlers) return;
      pending.delete(id);
      if (error) handlers.reject(new Error(error));
      else handlers.resolve(result);
    };
    worker.onerror = () => {
      for (const handlers of pending.values()) handlers.reject(new Error('Browser Python engine failed to load.'));
      pending.clear();
    };
    return payload => new Promise((resolve, reject) => {
      const id = ++sequence;
      pending.set(id, { resolve, reject });
      try { worker.postMessage({ id, payload }); }
      catch (error) { pending.delete(id); reject(error); }
    });
  }

  function clearResult(root) {
    root.getElementById('result').hidden = true;
    for (const id of OUTPUT_IDS) root.getElementById(id).textContent = '';
  }

  function formatSpan([start, end]) {
    if (start === end) return start === 0 ? 'gap before paragraph 1' : `gap after paragraph ${start}`;
    return end === start + 1 ? `paragraph ${start + 1}` : `paragraphs ${start + 1}–${end}`;
  }

  function renderResult(root, result) {
    const workflow = result && result.workflow;
    const learned = result && result.learned;
    if (!workflow || !learned || !workflow.decision || !workflow.receipt ||
        workflow.decision.action === 'AUTO_REPAIR' || workflow.selected_paragraphs != null) {
      throw new Error('Invalid review-only engine result; no output displayed.');
    }
    root.getElementById('view-reference').textContent = workflow.reference_paragraphs.join('\n\n');
    root.getElementById('view-observed').textContent = workflow.observed_paragraphs.join('\n\n');
    const changes = (workflow.review_changes || []).map(change =>
      `${change.kind.toUpperCase()} · reference ${formatSpan(change.reference_span)}, observed ${formatSpan(change.observed_span)}`);
    root.getElementById('changes').textContent = changes.join('\n') || 'No paragraph difference after whitespace normalization.';
    root.getElementById('model').textContent =
      `${learned.proposal_status} · ${learned.proposal_reason}. The model ranks correspondence; it does not authenticate a source.`;
    root.getElementById('proposal').textContent = learned.proposed_paragraphs
      ? learned.proposed_paragraphs.join('\n\n') : 'No model proposal.';
    root.getElementById('gate-action').textContent =
      `${workflow.decision.action} · ${(workflow.decision.reason_codes || []).join(', ') || 'no reason code'}`;
    root.getElementById('selected').textContent = 'No output applied. Review the original source manually.';
    root.getElementById('receipt').textContent = JSON.stringify({
      gate_receipt: workflow.receipt, model_receipt: learned.upstream_receipt,
      proposal_gate_receipt: learned.proposal_check?.receipt || null,
    }, null, 2);
    root.getElementById('result').hidden = false;
  }

  async function loadPdfJs() {
    const pdfjs = await import(PDFJS_URL);
    pdfjs.GlobalWorkerOptions.workerSrc = PDFJS_WORKER_URL;
    return pdfjs;
  }

  function initTrial(root, { runEngine, extractPdf = globalThis.BioSurePdf?.extractPdf,
                             getPdfJs = loadPdfJs }) {
    const get = id => root.getElementById(id);
    let version = 0;
    let pdfImported = false;
    const invalidate = () => {
      version++;
      clearResult(root);
      get('import-pdf').disabled = false;
      get('run').disabled = false;
      get('ack').checked = false;
      get('pdf-ack').checked = false;
      get('status').textContent = 'Input changed. Confirm the declared reference before checking.';
    };
    for (const id of ['reference', 'observed']) get(id).addEventListener('input', invalidate);
    get('pdf-file').addEventListener('change', invalidate);

    get('import-pdf').addEventListener('click', async () => {
      const file = get('pdf-file').files[0];
      const target = get('pdf-target').value;
      if (!['reference', 'observed'].includes(target)) {
        get('status').textContent = 'Choose reference or observed as the PDF destination.';
        return;
      }
      invalidate();
      const current = version;
      get(target).value = '';
      get('import-pdf').disabled = true;
      get('run').disabled = true;
      get('status').textContent = 'Reading PDF text layer in this browser…';
      try {
        const pdfjs = await getPdfJs();
        const extracted = await extractPdf(file, pdfjs);
        if (current !== version) return;
        get(target).value = extracted.text;
        pdfImported = true;
        const missing = extracted.warnings.filter(item => item.startsWith('NO_TEXT_ON_PAGE_'));
        get('status').textContent = `Extracted ${extracted.pages} page-text chunk(s) locally. ` +
          `These are not verified paragraphs; compare every page, split/correct the text, then acknowledge PDF review.` +
          (missing.length ? ` ${missing.length} page(s) had no text layer.` : '');
      } catch (error) {
        if (current === version) get('status').textContent = error.message;
      } finally {
        if (current === version) { get('import-pdf').disabled = false; get('run').disabled = false; }
      }
    });

    get('run').addEventListener('click', async () => {
      clearResult(root);
      const current = ++version;
      if (!get('ack').checked) {
        get('status').textContent = 'Acknowledge that the declared reference is unverified.';
        return;
      }
      if (pdfImported && !get('pdf-ack').checked) {
        get('status').textContent = 'Compare and correct the PDF text against its pages, then acknowledge PDF review.';
        return;
      }
      let payload;
      try { payload = prepareInput(get('reference').value, get('observed').value); }
      catch (error) { get('status').textContent = error.message; return; }
      get('run').disabled = true;
      get('status').textContent = 'Running the public Python review engine locally in your browser…';
      try {
        const result = await runEngine(payload);
        if (current !== version) return;
        renderResult(root, result);
        get('status').textContent = 'Review complete. Source authenticity and biological meaning remain unverified.';
      } catch (error) {
        if (current === version) { clearResult(root); get('status').textContent = error.message; }
      } finally {
        if (current === version) get('run').disabled = false;
      }
    });
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { prepareInput, makeWorkerRunner, clearResult, renderResult, initTrial };
  }
  if (typeof document !== 'undefined') document.addEventListener('DOMContentLoaded', () => {
    try {
      const worker = new Worker('./engine-worker.js');
      initTrial(document, { runEngine: makeWorkerRunner(worker) });
      document.getElementById('status').textContent = 'Ready. Paste text or import a PDF text layer.';
    } catch (error) {
      document.getElementById('status').textContent = `Browser engine unavailable: ${error.message}`;
    }
  });
})();
