const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');

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

test('expanded PDF text is bounded before assembling a browser input', async () => {
  const { extractPdf } = load();
  const { pdfjs, calls } = reader([[{ str: 'x'.repeat(262145), hasEOL: false }]]);
  await assert.rejects(extractPdf(localFile(), pdfjs), /262144 characters/);
  assert.equal(calls.destroyed, true);
});

test('PDF.js caption and furniture hints match the seven Python-positive lines without editing text', async () => {
  const { extractPdf } = load();
  const lines = [
    'Fig. 1 | Mini-bladder model of the human urothelium',
    'FIG 3 Cytokine production in the maternal chamber',
    'Figure 4. Barrier integrity after reperfusion',
    'TABLE 1 Versatility of composites',
    'Nature Communications | (2026) 17:2322 5',
    'Infection and Immunity December 2025 Volume 93 Issue 12 10.1128/iai.00346-25 2',
    'Received: 14 February 2025',
  ];
  const { pdfjs } = reader([lines.map(str => ({ str, hasEOL: true }))]);
  const result = await extractPdf(localFile(), pdfjs);
  assert.equal(result.text, lines.join('\n'));
  assert.ok(result.warnings.includes('CAPTION_OR_PAGE_FURNITURE_REQUIRES_REVIEW'));
  assert.deepEqual(result.review_hints, lines.map(excerpt => ({
    page: 1, kind: 'PROBABLE_CAPTION_OR_PAGE_FURNITURE', excerpt,
  })));
});

test('PDF.js does not mislabel the three Python-negative body lines', async () => {
  const { extractPdf } = load();
  const lines = [
    'Figure 2 shows that cells remained viable',
    'cells were seeded in 3 of 4 wells and the medium',
    'as described previously (doi:10.1038/s41467-026-68573-3).',
  ];
  const { pdfjs } = reader([lines.map(str => ({ str, hasEOL: true }))]);
  const result = await extractPdf(localFile(), pdfjs);
  assert.equal(result.text, lines.join('\n'));
  assert.deepEqual(result.review_hints, []);
  assert.equal(result.warnings.includes('CAPTION_OR_PAGE_FURNITURE_REQUIRES_REVIEW'), false);
});

test('PDF.js uses Python-compatible Unicode digits, word boundaries, and code-point limits for hints', async () => {
  const { extractPdf } = load();
  const within = '©' + '😀'.repeat(79); // 80 Unicode code points, 159 UTF-16 units.
  const boundary = '©' + '😀'.repeat(159); // 160 code points, 319 UTF-16 units.
  const beyond = '©' + '😀'.repeat(160); // 161 code points.
  const lines = ['Figure ٢. Authored result', 'Receivedβ', within, boundary, beyond];
  const { pdfjs } = reader([lines.map(str => ({ str, hasEOL: true }))]);
  const result = await extractPdf(localFile(), pdfjs);
  assert.equal(result.text, lines.join('\n'));
  assert.deepEqual(result.review_hints.map(hint => hint.excerpt), [
    lines[0], within, [...boundary].slice(0, 120).join(''),
  ]);
  assert.ok(result.review_hints.every(hint => [...hint.excerpt].length <= 120));
});

test('PDF.js bounds furniture hints at 64 and retains later-page coverage', async () => {
  const { extractPdf } = load();
  const first = Array.from({ length: 70 }, (_, index) => ({
    str: `FIGURE ${index + 1} | A source line ${index + 1} with context ${'x'.repeat(120)}`,
    hasEOL: true,
  }));
  const { pdfjs } = reader([first, [{ str: 'TABLE 1. Later-page legend', hasEOL: true }]]);
  const result = await extractPdf(localFile(), pdfjs);
  assert.equal(result.review_hints.length, 64);
  assert.ok(result.review_hints.every(hint => hint.excerpt.length <= 120));
  assert.ok(result.review_hints.some(hint => hint.page === 2));
  assert.ok(result.warnings.includes('REVIEW_HINTS_TRUNCATED'));
  assert.ok(result.text.includes('FIGURE 70 | A source line 70'));
  assert.ok(result.text.includes('TABLE 1. Later-page legend'));
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
    proposed_paragraphs: null, correspondences: [], upstream_receipt: {receipt_sha256: 'def'}},
  critical_alerts: [], critical_unchecked_spans: [] };
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

test('critical token alerts render changed values as text without applying an edit', () => {
  const { renderResult } = trial();
  const root = fakeRoot();
  const result = {workflow: {
    reference_paragraphs: ['Dose 5 mg.', 'Cells did not recover.'],
    observed_paragraphs: ['Dose 50 mg.', 'Cells did recover.'],
    review_changes: [{kind:'changed',reference_span:[0,2],observed_span:[0,2]}],
    decision:{action:'ABSTAIN',reason_codes:['NO_VALID_CANDIDATE']},
    selected_paragraphs:null,receipt:{receipt_sha256:'abc'},
  }, learned:{proposal_status:'ABSTAIN',proposal_reason:'LOW_CONFIDENCE',
    proposed_paragraphs:null,upstream_receipt:{receipt_sha256:'def'}},
  critical_unchecked_spans: [],
  critical_alerts:[
    {reference_index:0,observed_index:0,flags:['NUMBER_CHANGED'],
      reference_tokens:{numbers:['5'],units:['mg'],negations:[]},
      observed_tokens:{numbers:['5E+1'],units:['mg'],negations:[]}},
    {reference_index:1,observed_index:1,flags:['NEGATION_CHANGED'],
      reference_tokens:{numbers:[],units:[],negations:['not']},
      observed_tokens:{numbers:[],units:[],negations:[]}},
  ]};
  renderResult(root,result);
  const text = root.getElementById('critical-alerts').textContent;
  assert.match(text, /NUMBER_CHANGED: 5 → 50 \(mg\)/);
  assert.match(text, /NEGATION_CHANGED: not → ∅/);
  assert.match(root.getElementById('critical-note').textContent, /review|not a correction/i);
  assert.equal(root.getElementById('selected').textContent, 'No output applied. Review the original source manually.');
  assert.equal(root.getElementById('gate-action').textContent, 'ABSTAIN · NO_VALID_CANDIDATE');
  const benign = structuredClone(result);
  benign.critical_alerts = [];
  renderResult(root,benign);
  assert.equal(root.getElementById('critical-alerts').textContent, 'no lexical alert');
});

test('critical display subtracts unchanged number tokens and discloses unpaired spans', () => {
  const { renderResult } = trial();
  const root = fakeRoot();
  const result = {workflow: {
    reference_paragraphs:['Dose 5 and 10 mg.'],
    observed_paragraphs:['Dose 50 and 10 mg.','New paragraph.'],
    review_changes:[{kind:'changed',reference_span:[0,1],observed_span:[0,2]}],
    decision:{action:'ABSTAIN',reason_codes:['NO_VALID_CANDIDATE']},
    selected_paragraphs:null,receipt:{receipt_sha256:'abc'},
  },learned:{proposal_status:'ABSTAIN',proposal_reason:'LOW_CONFIDENCE',
    proposed_paragraphs:null,upstream_receipt:{receipt_sha256:'def'}},
  critical_alerts:[{reference_index:0,observed_index:0,flags:['NUMBER_CHANGED'],
    reference_tokens:{numbers:['10','5'],units:['mg'],negations:[]},
    observed_tokens:{numbers:['10','5E+1'],units:['mg'],negations:[]}}],
  critical_unchecked_spans:[{reference_span:[0,1],observed_span:[0,2]}]};
  renderResult(root,result);
  const displayed = root.getElementById('critical-alerts').textContent;
  assert.match(displayed,/NUMBER_CHANGED: 5 → 50/);
  assert.doesNotMatch(displayed,/50 \(mg\)/);
  assert.doesNotMatch(displayed,/10, 5/);
  assert.match(displayed,/lexical check not performed/i);
  assert.equal(root.getElementById('selected').textContent,'No output applied. Review the original source manually.');
});

test('number alert does not label a changed year with an unrelated unit', () => {
  const { renderResult } = trial();
  const root = fakeRoot();
  const result = {workflow:{
    reference_paragraphs:['In 2024, dose 5 mg.'],
    observed_paragraphs:['In 2025, dose 5 mg.'],
    review_changes:[{kind:'changed',reference_span:[0,1],observed_span:[0,1]}],
    decision:{action:'ABSTAIN',reason_codes:['NO_VALID_CANDIDATE']},
    selected_paragraphs:null,receipt:{receipt_sha256:'abc'},
  },learned:{proposal_status:'ABSTAIN',proposal_reason:'LOW_CONFIDENCE',
    proposed_paragraphs:null,upstream_receipt:{receipt_sha256:'def'}},
  critical_alerts:[{reference_index:0,observed_index:0,flags:['NUMBER_CHANGED'],
    reference_tokens:{numbers:['2024','5'],units:['mg'],negations:[]},
    observed_tokens:{numbers:['2025','5'],units:['mg'],negations:[]}}],
  critical_unchecked_spans:[]};
  renderResult(root,result);
  const displayed = root.getElementById('critical-alerts').textContent;
  assert.match(displayed,/NUMBER_CHANGED: 2024 → 2025/);
  assert.doesNotMatch(displayed,/2025 \(mg\)/);
});

async function runRealPythonWorker(payload) {
  const source = fs.readFileSync(path.join(__dirname, '../docs/try/engine-worker.js'), 'utf8');
  const modelJson = fs.readFileSync(path.join(__dirname, '../docs/try/model.json'), 'utf8');
  const messages = [], globals = new Map();
  const script = `import ast, os
payload_json = os.environ['BIOSURE_PAYLOAD_JSON']
model_json = os.environ['BIOSURE_MODEL_JSON']
tree = ast.parse(os.environ['BIOSURE_WORKER_CODE'])
last = tree.body.pop()
exec(compile(tree, '<browser-worker>', 'exec'))
print(eval(compile(ast.Expression(last.value), '<browser-worker>', 'eval')))
`;
  const pyodide = {
    FS:{writeFile(){}},globals:{set:(name,value)=>globals.set(name,value)},
    runPython(code){
      if (!code.includes('propose_learned')) return;
      return execFileSync(process.env.PYTHON || 'python', ['-B','-c',script], {
        cwd:path.join(__dirname,'..'),encoding:'utf8',
        env:{...process.env,PYTHONIOENCODING:'utf-8',BIOSURE_PAYLOAD_JSON:globals.get('payload_json'),
          BIOSURE_MODEL_JSON:globals.get('model_json'),BIOSURE_WORKER_CODE:code},
      }).trim();
    },
  };
  const context = vm.createContext({self:{postMessage:message=>messages.push(message)},
    importScripts:()=>{},loadPyodide:async()=>pyodide,
    fetch:async url=>({ok:true,arrayBuffer:async()=>new Uint8Array([1]).buffer,
      text:async()=>url==='./model.json'?modelJson:''}),Uint8Array,JSON,Error});
  vm.runInContext(source,context);
  await context.self.onmessage({data:{id:19,payload}});
  assert.equal(messages[0].error,undefined,messages[0].error);
  return messages[0].result;
}

test('real Python worker reports number, unit, and negation changes without changing the gate', async () => {
  const result = await runRealPythonWorker({record_id:'critical-trial',
    reference_paragraphs:['Anchor A.','Dose 5 mg.','Anchor B.','Use 5 mL of medium.',
      'Anchor C.','Cells did not recover.'],
    observed_paragraphs:['Anchor A.','Dose 50 mg.','Anchor B.','Use 5 uL of medium.',
      'Anchor C.','Cells did recover.']});
  assert.deepEqual(result.critical_alerts.map(item=>item.flags),[
    ['NUMBER_CHANGED'],['UNIT_CHANGED'],['NEGATION_CHANGED']]);
  assert.deepEqual(result.critical_alerts.map(item=>item.reference_index),[1,3,5]);
  assert.equal(result.critical_alerts[0].reference_tokens.numbers[0],'5');
  assert.equal(result.critical_alerts[0].observed_tokens.numbers[0],'5E+1');
  assert.equal(result.critical_alerts[1].reference_tokens.units[0],'mL');
  assert.equal(result.critical_alerts[1].observed_tokens.units[0],'μL');
  assert.equal(result.workflow.decision.action,'ABSTAIN');
  assert.equal(result.workflow.selected_paragraphs,null);
});

test('real Python worker gives no lexical alert for wording-only change', async () => {
  const result = await runRealPythonWorker({record_id:'benign-trial',
    reference_paragraphs:['Cells remained viable.'],observed_paragraphs:['Cells appeared viable.']});
  assert.deepEqual(result.critical_alerts,[]);
  assert.equal(result.workflow.decision.action,'ABSTAIN');
  assert.equal(result.workflow.selected_paragraphs,null);
});

test('real Python worker marks unequal changed spans as unchecked instead of claiming no alert', async () => {
  const result = await runRealPythonWorker({record_id:'unpaired-trial',
    reference_paragraphs:['Anchor A.','Dose 5 mg.','Anchor B.'],
    observed_paragraphs:['Anchor A.','Dose 50 mg.','New paragraph.','Anchor B.']});
  assert.deepEqual(result.critical_alerts,[]);
  assert.deepEqual(result.critical_unchecked_spans.map(item=>item.reference_span),[[1,2]]);
  assert.deepEqual(result.critical_unchecked_spans.map(item=>item.observed_span),[[1,3]]);
  assert.equal(result.workflow.decision.action,'ABSTAIN');
  assert.equal(result.workflow.selected_paragraphs,null);
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

test('failed PDF import leaves existing pasted text available for correction', async () => {
  const { initTrial } = trial();
  const root = fakeRoot();
  initTrial(root, {runEngine: async () => ({}), getPdfJs: async () => ({}),
    extractPdf: async () => { throw new Error('Could not read PDF text layer'); }});
  root.getElementById('observed').value = 'keep my edits';
  root.getElementById('pdf-target').value = 'observed';
  root.getElementById('pdf-file').files = [{name: 'damaged.pdf'}];
  await root.getElementById('import-pdf').fire('click');
  assert.equal(root.getElementById('observed').value, 'keep my edits');
  assert.match(root.getElementById('status').textContent, /Could not read PDF/);
});

test('PDF import status names caption hints as manual review, never an applied removal', async () => {
  const { initTrial } = trial();
  const root = fakeRoot();
  initTrial(root, {runEngine: async () => ({}), getPdfJs: async () => ({}),
    extractPdf: async () => ({text: 'Body\nFIGURE 2 Caption', pages: 1,
      warnings: ['CAPTION_OR_PAGE_FURNITURE_REQUIRES_REVIEW'],
      review_hints: [{page: 1, kind: 'PROBABLE_CAPTION_OR_PAGE_FURNITURE',
        excerpt: 'FIGURE 2 Caption'}]})});
  root.getElementById('pdf-file').files = [{name: 'example.pdf'}];
  root.getElementById('pdf-target').value = 'observed';
  await root.getElementById('import-pdf').fire('click');
  assert.equal(root.getElementById('observed').value, 'Body\nFIGURE 2 Caption');
  assert.match(root.getElementById('status').textContent, /Page 1.*FIGURE 2 Caption/);
  assert.match(root.getElementById('status').textContent, /not removed|never removed/i);
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

test('browser worker can retry loading after a transient runtime failure', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../docs/try/engine-worker.js'), 'utf8');
  const posted = [];
  let attempts = 0;
  const pyodide = {
    FS: { writeFile() {} }, globals: { set() {} },
    runPython(code) { return code.includes('propose_learned')
      ? JSON.stringify({workflow:{selected_paragraphs:null},learned:{proposal_status:'ABSTAIN'}})
      : undefined; },
  };
  const context = vm.createContext({
    self: {postMessage: value => posted.push(value)},
    importScripts: () => {},
    loadPyodide: async () => { if (++attempts === 1) throw new Error('temporary CDN failure'); return pyodide; },
    fetch: async () => ({ok:true, arrayBuffer:async()=>new Uint8Array([1]).buffer,
      text:async()=>'{}'}), Uint8Array, JSON, Error,
  });
  vm.runInContext(source, context);
  await context.self.onmessage({data:{id:1,payload:{record_id:'one'}}});
  await context.self.onmessage({data:{id:2,payload:{record_id:'two'}}});
  assert.match(posted[0].error, /temporary CDN failure/);
  assert.ok(posted[1].result);
});
