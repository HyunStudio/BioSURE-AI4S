const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function load() { return require('../docs/try/pdf.js'); }

function localFile(bytes = Uint8Array.from([37, 80, 68, 70]), size = bytes.byteLength) {
  return { size, async arrayBuffer() { return bytes.buffer; } };
}

function reader(pages) {
  const calls = { args: null, page: 0, destroyed: false };
  const pdfjs = { getDocument(args) {
    calls.args = args;
    return {
      promise: Promise.resolve({
        numPages: pages.length,
        async getPage(index) {
          calls.page++;
          return { async getTextContent() { return { items: pages[index - 1] }; } };
        },
      }),
      async destroy() { calls.destroyed = true; },
    };
  } };
  return { pdfjs, calls };
}

test('two-page PDF text stays in local byte input and returns editable page chunks', async () => {
  const { extractPdf } = load();
  const { pdfjs, calls } = reader([
    [{ str: 'First line', hasEOL: true }, { str: 'of page one', hasEOL: false }],
    [{ str: 'Page two', hasEOL: false }],
  ]);
  const priorFetch = global.fetch;
  global.fetch = () => { throw new Error('document must not be uploaded'); };
  try {
    const result = await extractPdf(localFile(), pdfjs);
    assert.equal(result.pages, 2);
    assert.equal(result.text, 'First line\nof page one\n\nPage two');
    assert.ok(result.warnings.includes('UNVERIFIED_PAGE_TEXT'));
    assert.ok(calls.args.data instanceof Uint8Array);
    assert.equal('url' in calls.args, false);
    assert.equal(calls.page, 2);
    assert.equal(calls.destroyed, true);
  } finally { global.fetch = priorFetch; }
});

test('oversize PDF is rejected before parsing', async () => {
  const { extractPdf } = load();
  const { pdfjs, calls } = reader([]);
  await assert.rejects(extractPdf(localFile(undefined, 16 * 1024 * 1024 + 1), pdfjs), /16 MiB/);
  assert.equal(calls.args, null);
});

test('more than 32 PDF pages is rejected before reading a page', async () => {
  const { extractPdf } = load();
  const { pdfjs, calls } = reader(Array.from({ length: 33 }, () => [{ str: 'text' }]));
  await assert.rejects(extractPdf(localFile(), pdfjs), /32 pages/);
  assert.equal(calls.page, 0);
  assert.equal(calls.destroyed, true);
});

test('image-only PDF cannot masquerade as an empty document audit', async () => {
  const { extractPdf } = load();
  const { pdfjs } = reader([[{ str: '' }], []]);
  await assert.rejects(extractPdf(localFile(), pdfjs), /no usable text layer/i);
});

test('malformed PDF yields an actionable error', async () => {
  const { extractPdf } = load();
  const pdfjs = { getDocument() { throw new Error('bad structure'); } };
  await assert.rejects(extractPdf(localFile(), pdfjs), /Could not read PDF/);
});

function trial() { return require('../docs/try/app.js'); }

function fakeRoot() {
  const nodes = new Map();
  const getElementById = id => {
    if (!nodes.has(id)) nodes.set(id, {
      value: '', checked: false, hidden: true, disabled: false, textContent: '', files: [],
      listeners: {}, addEventListener(name, callback) { this.listeners[name] = callback; },
      fire(name) { return this.listeners[name](); },
      set innerHTML(_) { throw new Error('user text must not become HTML'); },
    });
    return nodes.get(id);
  };
  return { getElementById };
}

test('pasted paragraphs use Python workflow limits and normalization', () => {
  const { prepareInput } = trial();
  assert.deepEqual(prepareInput('  A  line\n continues \n\n  second ', ' A line continues '), {
    record_id: 'browser-trial', reference_paragraphs: ['A line continues', 'second'],
    observed_paragraphs: ['A line continues'],
  });
  assert.throws(() => prepareInput('', 'x'), /reference/i);
  assert.throws(() => prepareInput('x', '  '), /observed/i);
  assert.throws(() => prepareInput('x'.repeat(4097), 'x'), /4096/);
  assert.throws(() => prepareInput(Array(129).fill('x').join('\n\n'), 'x'), /128/);
});

test('review result renders script-looking text literally and rejects an applied edit', () => {
  const { renderResult } = trial();
  const root = fakeRoot();
  const result = { workflow: {
    reference_paragraphs: ['source <script>alert(1)</script>'], observed_paragraphs: ['observed <img>'],
    review_changes: [{kind: 'changed', reference_span: [0, 1], observed_span: [0, 1]}],
    decision: {action: 'ABSTAIN', reason_codes: ['NO_VALID_CANDIDATE']},
    selected_paragraphs: null, receipt: {receipt_sha256: 'abc'},
  }, learned: {proposal_status: 'ABSTAIN', proposal_reason: 'LOW_CONFIDENCE',
    proposed_paragraphs: null, correspondences: [], upstream_receipt: {receipt_sha256: 'def'}} };
  renderResult(root, result);
  assert.match(root.getElementById('view-reference').textContent, /<script>/);
  assert.match(root.getElementById('view-observed').textContent, /<img>/);
  assert.match(root.getElementById('changes').textContent, /reference paragraph 1, observed paragraph 1/);
  assert.match(root.getElementById('selected').textContent, /No output applied/);
  assert.equal(root.getElementById('result').hidden, false);
  const unsafe = structuredClone(result);
  unsafe.workflow.decision.action = 'AUTO_REPAIR';
  unsafe.workflow.selected_paragraphs = ['forged'];
  assert.throws(() => renderResult(root, unsafe), /review-only/);
});

test('worker failure rejects instead of showing a frozen or invented result', async () => {
  const { makeWorkerRunner } = trial();
  const worker = { postMessage(message) { this.onmessage({data:{id:message.id,error:'engine unavailable'}}); } };
  const runner = makeWorkerRunner(worker);
  await assert.rejects(runner({record_id:'x'}), /engine unavailable/);
});

test('editing input while engine runs invalidates old result and receipt', async () => {
  const { initTrial } = trial();
  const root = fakeRoot();
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  initTrial(root, {runEngine: () => pending});
  root.getElementById('reference').value = 'one\n\ntwo';
  root.getElementById('observed').value = 'one';
  root.getElementById('ack').checked = true;
  const active = root.getElementById('run').fire('click');
  root.getElementById('reference').value = 'edited';
  root.getElementById('reference').fire('input');
  finish({workflow:{decision:{action:'ABSTAIN'},selected_paragraphs:null}});
  await active;
  assert.equal(root.getElementById('result').hidden, true);
  assert.equal(root.getElementById('receipt').textContent, '');
  assert.equal(root.getElementById('run').disabled, false);
});

test('editing input during PDF extraction releases disabled controls and discards stale text', async () => {
  const { initTrial } = trial();
  const root = fakeRoot();
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  initTrial(root, {runEngine: async () => ({}), getPdfJs: async () => ({}),
    extractPdf: () => pending});
  root.getElementById('pdf-file').files = [{name: 'example.pdf'}];
  const active = root.getElementById('import-pdf').fire('click');
  root.getElementById('observed').value = 'replacement text';
  root.getElementById('observed').fire('input');
  finish({text: 'stale PDF content', pages: 1, warnings: []});
  await active;
  assert.equal(root.getElementById('observed').value, 'replacement text');
  assert.equal(root.getElementById('import-pdf').disabled, false);
  assert.equal(root.getElementById('run').disabled, false);
});

test('browser worker evaluates current input through packaged Python, never a frozen sample', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../docs/try/engine-worker.js'), 'utf8');
  const posted = [], fetched = [], globals = new Map();
  const pyodide = {
    FS: { writeFile(name, bytes) { assert.equal(name, '/biosure-engine.zip'); assert.ok(bytes.length); } },
    globals: { set: (name, value) => globals.set(name, value) },
    runPython(code) {
      if (!code.includes('propose_learned')) return;
      const payload = JSON.parse(globals.get('payload_json'));
      return JSON.stringify({workflow:{observed_paragraphs:payload.observed_paragraphs},
        learned:{proposal_status:'ABSTAIN'}});
    },
  };
  const context = vm.createContext({
    self: {postMessage: value => posted.push(value)},
    importScripts: () => {}, loadPyodide: async () => pyodide,
    fetch: async url => {
      fetched.push(url);
      return {ok:true, arrayBuffer:async()=>new Uint8Array([1]).buffer,
        text:async()=>'{"schema_version":"biosure.ml-model/1.0"}'};
    },
    Uint8Array, JSON, Error,
  });
  vm.runInContext(source, context);
  await context.self.onmessage({data:{id:7,payload:{record_id:'own-case',
    reference_paragraphs:['source'],observed_paragraphs:['visitor text']}}});
  assert.equal(posted[0].id, 7);
  assert.equal(posted[0].result.workflow.observed_paragraphs[0], 'visitor text');
  assert.deepEqual(fetched, ['./engine.zip', './model.json']);
});
