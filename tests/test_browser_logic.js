const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness(script = 'batch.js') {
  const elements = new Map();
  function element() {
    return {value: '', checked: false, disabled: false, textContent: '', children: [], files: [], listeners: {},
      addEventListener(name, fn) {this.listeners[name] = fn;},
      replaceChildren() {this.children = [];}, append(...items) {this.children.push(...items);}};
  }
  const get = id => {if (!elements.has(id)) elements.set(id, element()); return elements.get(id);};
  const context = vm.createContext({document: {getElementById: get, createElement: element}, TextEncoder,
    fetch: () => new Promise(resolve => {context.resolveFetch = resolve;})});
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../biosure/static', script), 'utf8'), context);
  return {get, context, call: name => vm.runInContext(name + '()', context)};
}
const records = [{record_id: 'one', reference_paragraphs: ['A','B','C'], observed_paragraphs: ['A','C']}];

test('acknowledging during sample fetch does not discard the loaded input', async () => {
  const h = harness(); const pending = h.call('loadBatch');
  h.get('batch-ack').checked = true; h.get('batch-ack').listeners.change();
  h.context.resolveFetch({ok: true, json: async () => records}); await pending;
  assert.deepEqual(JSON.parse(h.get('batch-input').value), records);
});
test('upstream check submits the actual proposal with locked reference and observed inputs', async () => {
  const h = harness('workflow.js'); let sent;
  h.get('reference-input').value = 'A\n\nB\n\nC'; h.get('observed-input').value = 'A\n\nC';
  h.get('proposal-input').value = 'A\n\ninvented\n\nC'; h.get('reference-ack').checked = true;
  h.context.fetch = async (endpoint, options) => {
    sent = {endpoint, body: JSON.parse(options.body)};
    return {ok: true, json: async () => ({decision:{action:'ABSTAIN',reason_codes:['UNSUPPORTED']},
      adapter_status:'PROPOSAL_REJECTED',selected_output:null,receipt:{receipt_sha256:'abc'},review_changes:[]})};
  };
  await h.call('runProposalCheck');
  assert.equal(sent.endpoint, '/api/proposal');
  assert.deepEqual(sent.body.proposed_paragraphs, ['A','invented','C']);
  assert.deepEqual(sent.body.observed_paragraphs, ['A','C']);
  assert.match(h.get('workflow-status').textContent, /NO AUTOMATIC CHANGE/);
});
test('checking while a load is pending cannot invalidate the load', async () => {
  const h = harness(); const pending = h.call('loadBatch');
  h.get('batch-ack').checked = true; await h.call('checkBatch');
  h.context.resolveFetch({ok: true, json: async () => records}); await pending;
  assert.deepEqual(JSON.parse(h.get('batch-input').value), records);
});
test('acknowledging while a file is read preserves the imported text', async () => {
  const h = harness(); let finish;
  h.get('batch-file').files = [{size: 100, text: () => new Promise(resolve => {finish = resolve;})}];
  const pending = h.call('importBatch');
  h.get('batch-ack').checked = true; h.get('batch-ack').listeners.change();
  finish(JSON.stringify(records)); await pending;
  assert.deepEqual(JSON.parse(h.get('batch-input').value), records);
});
test('editing pending input prevents an older response from overwriting it', async () => {
  const h = harness(); const pending = h.call('loadBatch');
  h.get('batch-input').value = 'my edit'; h.get('batch-input').listeners.input();
  h.context.resolveFetch({ok: true, json: async () => records}); await pending;
  assert.equal(h.get('batch-input').value, 'my edit');
});
test('manual review displays both paragraph sequences and the changed position as literal text', () => {
  const h = harness(); h.context.fixture = {summary: {records: 1,automatic: 0,unchanged: 0,review_required: 1},results: [{
    request: {damaged: {record_id: 'one'}}, decision: {action: 'ABSTAIN',reason_codes: []},
    adapter_status: 'UNSUPPORTED_DIFFERENCE', selected_paragraphs: null, receipt: {receipt_sha256: 'abc'},
    reference_paragraphs: ['source <script>'], observed_paragraphs: ['altered <img>'],
    review_changes: [{kind: 'changed',reference_span: [0,1], observed_span: [0,1]}]}]};
  vm.runInContext('renderBatch(fixture)', h.context);
  const allText = node => [node.textContent, ...node.children.map(allText)].join('\n');
  const text = allText(h.get('batch-records'));
  assert.match(text, /source <script>/); assert.match(text, /altered <img>/); assert.match(text, /CHANGED/);
});

test('PDF import populates only the chosen side and preserves image omission warning', async () => {
  const h = harness('workflow.js'); let endpoint;
  const file = {size: 100, type: 'application/pdf'};
  h.get('pdf-file').files = [file];
  h.get('pdf-target').value = 'reference';
  h.get('observed-input').value = 'Converted text';
  h.get('reference-ack').checked = true;
  h.context.fetch = async (url, options) => {
    endpoint = url; assert.equal(options.body, file);
    return {ok: true, json: async () => ({paragraphs: [{text:'A'},{text:'B'}],
      pages: 2, image_count: 3, warnings:['IMAGE_TEXT_NOT_EXTRACTED','TEXT_SPACING_ARTIFACTS','LINE_END_HYPHEN_REQUIRES_REVIEW'], review_required:true})};
  };
  await h.call('importPdf');
  assert.equal(endpoint, '/api/pdf-extract');
  assert.equal(h.get('reference-input').value, 'A\n\nB');
  assert.equal(h.get('observed-input').value, 'Converted text');
  assert.equal(h.get('reference-ack').checked, false);
  assert.match(h.get('pdf-status').textContent, /3 image/);
  assert.match(h.get('pdf-status').textContent, /not extracted/);
  assert.match(h.get('pdf-status').textContent, /Broken letter spacing/);
  assert.match(h.get('pdf-status').textContent, /hyphen.*review/i);
  h.get('reference-ack').checked = true;
  h.context.fetch = async () => {throw new Error('workflow must not submit before PDF review');};
  await h.call('runParagraphCheck');
  assert.match(h.get('workflow-reason').textContent, /acknowledge PDF review/);
});

test('learned review displays lexical alerts without claiming automatic approval', async () => {
  const h = harness('workflow.js'); let endpoint;
  h.get('reference-input').value = 'Dose 5 mg.\n\nNo increase.';
  h.get('observed-input').value = 'Dose 6 mg.\n\nNo increase.';
  h.get('reference-ack').checked = true;
  h.context.fetch = async (url) => {
    endpoint = url;
    return {ok:true, json:async () => ({decision:{action:'ABSTAIN',reason_codes:['UNSUPPORTED']},
      mode:'learned_correspondence_review', adapter_status:'UNSUPPORTED_DIFFERENCE',
      selected_paragraphs:null, receipt:{receipt_sha256:'abc'}, review_changes:[],
      correspondences:[{observed_index:0,reference_index:0,probability:0.93,
        flags:['NUMBER_CHANGED'], ambiguous:false}]})};
  };
  await h.call('runLearnedReview');
  assert.equal(endpoint, '/api/ml-review');
  assert.match(h.get('ml-rankings').textContent, /NUMBER_CHANGED/);
  assert.match(h.get('workflow-status').textContent, /NO AUTOMATIC CHANGE/);
});

test('model evidence card reports the held-out lexical tie plainly', async () => {
  const h = harness('app.js');
  h.context.fetch = async url => {
    assert.equal(url, '/api/ml-summary');
    return {ok:true, json:async () => ({sources:{train:12,dev:6,test:6},queries:284,
      learned_correct:284,best_lexical_correct:284,baseline:'token_dice',
      accuracy_delta:0,unit_control_positives:8})};
  };
  await h.call('loadModelSummary');
  assert.match(h.get('ml-summary').textContent, /284\/284/);
  assert.match(h.get('ml-summary').textContent, /ties/);
  assert.match(h.get('ml-summary').textContent, /not natural PDF errors/);
});
