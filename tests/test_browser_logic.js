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
      removeAttribute(name) {delete this[name];},
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

test('PDF review hints show the page and literal suspicious excerpt', async () => {
  const h = harness('workflow.js');
  h.get('pdf-file').files = [{size: 100, type: 'application/pdf'}];
  h.get('pdf-target').value = 'observed';
  h.context.fetch = async () => ({ok: true, json: async () => ({
    paragraphs: [{text: 'f o r d r u g'}], pages: 1, image_count: 0,
    warnings: ['TEXT_SPACING_ARTIFACTS'],
    review_hints: [{page: 1, kind: 'TEXT_SPACING_ARTIFACTS', excerpt: 'f o r <script>'}]
  })});
  await h.call('importPdf');
  assert.match(h.get('pdf-review-hints').children[0].textContent, /Page 1 · Check broken letter spacing.*f o r <script>/);
});

test('independent spacing suggestion is visible but never auto-applied', async () => {
  const h = harness('workflow.js');
  h.get('pdf-file').files = [{size: 100, type: 'application/pdf'}];
  h.get('pdf-target').value = 'observed';
  h.context.fetch = async () => ({ok: true, json: async () => ({
    paragraphs: [{text: 'elimination ef ficiency'}], pages: 1, image_count: 0,
    warnings: ['CROSS_EXTRACTOR_SPACING_REQUIRES_REVIEW'],
    review_hints: [{page: 1, kind: 'CROSS_EXTRACTOR_SPACING_SUGGESTION',
      excerpt: 'ef ficiency', suggestion: 'efficiency'}]
  })});
  await h.call('importPdf');
  assert.equal(h.get('observed-input').value, 'elimination ef ficiency');
  assert.match(h.get('pdf-review-hints').children[0].textContent,
    /Possible word spacing \(not applied\).*ef ficiency → efficiency/);
  assert.match(h.get('pdf-status').textContent, /verify each against the visible page/);
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

test('learned upstream shows source-unverified proposal and separate gate result literally', async () => {
  const h = harness('workflow.js'); let endpoint;
  h.get('reference-input').value = 'Source <script> 5 mg.\n\nClosing note.';
  h.get('observed-input').value = 'Source <script> 6 mg.\n\nClosing note.';
  h.get('reference-ack').checked = true;
  h.context.fetch = async url => {
    endpoint = url;
    return {ok:true, json:async () => ({mode:'learned_upstream_proposal', review_changes:[],
      original_workflow_review:{decision:{action:'ABSTAIN',reason_codes:['UNSUPPORTED']}},
      correspondences:[{observed_index:0,reference_index:0,probability:0.91,flags:['NUMBER_CHANGED'],ambiguous:false}],
      proposal_status:'PROPOSED_FOR_REVIEW', proposal_reason:'MATCHED_DECLARED_REFERENCE',
      proposed_paragraphs:['Source <script> 5 mg.','Closing note.'],
      proposal_check:{decision:{action:'ABSTAIN',reason_codes:['UNSUPPORTED']},selected_paragraphs:null,
        receipt:{receipt_sha256:'gate'}},
      upstream_receipt:{receipt_sha256:'upstream'}})};
  };
  await h.call('runLearnedProposal');
  assert.equal(endpoint, '/api/learned-proposal');
  assert.equal(h.get('learned-proposal-text').textContent, 'Source <script> 5 mg.\n\nClosing note.');
  assert.match(h.get('learned-proposal-status').textContent, /SOURCE UNVERIFIED/);
  assert.match(h.get('learned-proposal-status').textContent, /ABSTAIN/);
  assert.equal(h.get('learned-proposal-receipt').textContent, 'upstream');
  assert.equal(h.get('observed-input').value, 'Source <script> 6 mg.\n\nClosing note.');
  h.get('observed-input').listeners.input();
  assert.equal(h.get('learned-proposal-text').textContent, '');
});

test('learned abstention never displays a different baseline automatic repair', async () => {
  const h = harness('workflow.js');
  h.get('reference-input').value = 'The channel was washed.\n\nTHE CHANNEL WAS WASHED.\n\nClosing paragraph.';
  h.get('observed-input').value = 'The channel was washed.\n\nClosing paragraph.';
  h.get('reference-ack').checked = true;
  h.context.fetch = async () => ({ok:true, json:async () => ({
    mode:'learned_upstream_proposal', proposal_status:'ABSTAIN', proposal_reason:'AMBIGUOUS_MATCH',
    proposed_paragraphs:null, proposal_check:null, review_changes:[], correspondences:[],
    original_workflow_review:{decision:{action:'AUTO_REPAIR',reason_codes:[]},
      selected_paragraphs:['The channel was washed.','THE CHANNEL WAS WASHED.','Closing paragraph.']},
    upstream_receipt:{receipt_sha256:'upstream'}})});
  await h.call('runLearnedProposal');
  assert.match(h.get('workflow-status').textContent, /NO LEARNED PROPOSAL/);
  assert.match(h.get('learned-proposal-status').textContent, /AMBIGUOUS_MATCH/);
  assert.match(h.get('workflow-output').textContent, /No output applied/);
  assert.equal(h.get('workflow-receipt').textContent, '');
});

test('learned candidate displays only its own gate-approved selected text', async () => {
  const h = harness('workflow.js');
  h.get('reference-input').value = 'A\n\nB\n\nC';
  h.get('observed-input').value = 'A\n\nC';
  h.get('reference-ack').checked = true;
  h.context.fetch = async () => ({ok:true, json:async () => ({
    mode:'learned_upstream_proposal', proposal_status:'PROPOSED_FOR_REVIEW',
    proposal_reason:'MATCHED_DECLARED_REFERENCE', proposed_paragraphs:['A','B','C'],
    original_workflow_review:{decision:{action:'ABSTAIN',reason_codes:['OTHER']}},
    proposal_check:{decision:{action:'AUTO_REPAIR',reason_codes:[]},
      selected_paragraphs:['A','B','C'], receipt:{receipt_sha256:'candidate-gate'}},
    review_changes:[], correspondences:[], upstream_receipt:{receipt_sha256:'upstream'}})});
  await h.call('runLearnedProposal');
  assert.match(h.get('workflow-status').textContent, /REFERENCE MATCH.*SOURCE UNVERIFIED/);
  assert.equal(h.get('workflow-output').textContent, 'A\n\nB\n\nC');
  assert.equal(h.get('workflow-receipt').textContent, 'candidate-gate');
});

test('real public extraction loader shows attributed inputs and clears prior trust acknowledgements', async () => {
  const h = harness('workflow.js'); let endpoint;
  h.get('public-source-select').value = 'PMC12864593';
  h.get('reference-ack').checked = true;
  h.get('pdf-ack').checked = true;
  h.context.fetch = async url => {
    endpoint = url;
    return {ok:true, json:async () => ({source_id:'PMC12864593',split:'development',
      source:{pmcid:'PMC12864593',doi:'10.1002/adhm.202502711',
        license_uri:'https://creativecommons.org/licenses/by/4.0/',pdf_sha256:'a'.repeat(64)},
      reference_paragraphs:['Drug Effects in a Liver Chip','Reference abstract'],
      observed_paragraphs:['DrugEffectsinaLiverChip','PDF abstract'],
      note:'Actual public PDF text-layer excerpt; manually check deposited page.'})};
  };
  await h.call('loadPublicExtraction');
  assert.equal(endpoint, '/api/examples/public-extraction?source=PMC12864593');
  assert.equal(h.get('reference-input').value, 'Drug Effects in a Liver Chip\n\nReference abstract');
  assert.equal(h.get('observed-input').value, 'DrugEffectsinaLiverChip\n\nPDF abstract');
  assert.equal(h.get('reference-ack').checked, false);
  assert.equal(h.get('pdf-ack').checked, false);
  assert.match(h.get('public-source-note').textContent, /PMC12864593.*CC BY 4.0.*manually check/);
  assert.equal(h.get('public-article-link').href, 'https://pmc.ncbi.nlm.nih.gov/articles/PMC12864593/');
  assert.match(h.get('public-article-link').textContent, /Open.*PMC12864593/);
  assert.equal(h.get('public-source-link-row').hidden, false);
  assert.equal(h.get('workflow-status').textContent, 'READY');
});

test('public extraction load revokes prior acknowledgement before the network response', async () => {
  const h = harness('workflow.js');
  h.get('reference-ack').checked = true;
  h.get('pdf-ack').checked = true;
  let resolveResponse;
  h.context.fetch = () => new Promise(resolve => {resolveResponse = resolve;});
  const pending = h.call('loadPublicExtraction');
  assert.equal(h.get('reference-ack').checked, false);
  assert.equal(h.get('pdf-ack').checked, false);
  assert.equal(h.get('load-public-extraction').disabled, true);
  resolveResponse({ok:false, json:async () => ({error:'test unavailable'})});
  await pending;
  assert.equal(h.get('load-public-extraction').disabled, false);
});

test('acknowledging while public excerpt loads does not strand the response or preserve trust', async () => {
  const h = harness('workflow.js');
  let resolveResponse;
  h.context.fetch = () => new Promise(resolve => {resolveResponse = resolve;});
  const pending = h.call('loadPublicExtraction');
  h.get('reference-ack').checked = true;
  h.get('reference-ack').listeners.change();
  resolveResponse({ok:true,json:async () => ({source_id:'PMC12864593',
    reference_paragraphs:['Reference'], observed_paragraphs:['Observed'],
    note:'manually check original page'})});
  await pending;
  assert.equal(h.get('reference-input').value, 'Reference');
  assert.equal(h.get('observed-input').value, 'Observed');
  assert.equal(h.get('reference-ack').checked, false);
  assert.match(h.get('public-source-note').textContent, /manually check/);
  assert.equal(h.get('load-public-extraction').disabled, false);
});

test('completed public load invalidates a check made against prior inputs', async () => {
  const h = harness('workflow.js');
  h.get('reference-input').value = 'Old reference';
  h.get('observed-input').value = 'Old observed';
  let resolvePublic;
  h.context.fetch = url => url.startsWith('/api/examples/public-extraction')
    ? new Promise(resolve => {resolvePublic = resolve;})
    : Promise.resolve({ok:true,json:async () => ({decision:{action:'AUTO_REPAIR',reason_codes:[]},
      adapter_status:'CANDIDATE_PROPOSED', selected_paragraphs:['Old reference'],
      receipt:{receipt_sha256:'old'}, review_changes:[]})});
  const pending = h.call('loadPublicExtraction');
  h.get('reference-ack').checked = true;
  h.get('reference-ack').listeners.change();
  await h.call('runParagraphCheck');
  resolvePublic({ok:true,json:async () => ({source_id:'PMC12864593',
    reference_paragraphs:['New reference'], observed_paragraphs:['New observed'], note:'manually check'})});
  await pending;
  assert.equal(h.get('reference-input').value, 'New reference');
  assert.equal(h.get('reference-ack').checked, false);
  assert.equal(h.get('workflow-status').textContent, 'READY');
  assert.equal(h.get('workflow-output').textContent, '');
});

test('paragraph review shows the actual changed text and clears it after input changes', async () => {
  const h = harness('workflow.js');
  h.get('reference-input').value = 'A\n\nSource <script> text\n\nC';
  h.get('observed-input').value = 'A\n\nC';
  h.get('reference-ack').checked = true;
  h.context.fetch = async () => ({ok: true, json: async () => ({
    decision: {action: 'ABSTAIN', reason_codes: ['REVIEW']}, adapter_status: 'UNSUPPORTED_DIFFERENCE',
    selected_paragraphs: null, selected_output: null, receipt: {receipt_sha256: 'abc'},
    reference_paragraphs: ['A', 'Source <script> text', 'C'], observed_paragraphs: ['A', 'C'],
    review_changes: [{kind: 'missing', reference_span: [1, 2], observed_span: [1, 1]}]
  })});
  await h.call('runParagraphCheck');
  const panel = h.get('workflow-change-details');
  const allText = node => [node.textContent, ...node.children.map(allText)].join('\n');
  assert.equal(panel.children.length, 1);
  assert.match(allText(panel), /Source <script> text/);
  assert.match(allText(panel), /Converted text[\s\S]*\(no paragraph\)/);
  h.get('observed-input').listeners.input();
  assert.equal(panel.children.length, 0);
});

test('a selected output is visibly marked as conditional on unverified reference truth', async () => {
  const h = harness('workflow.js');
  h.get('reference-input').value = 'A\n\nB\n\nC';
  h.get('observed-input').value = 'A\n\nC';
  h.get('reference-ack').checked = true;
  h.context.fetch = async () => ({ok: true, json: async () => ({
    decision: {action: 'AUTO_REPAIR', reason_codes: []}, adapter_status: 'CANDIDATE_PROPOSED',
    selected_paragraphs: ['A', 'B', 'C'], receipt: {receipt_sha256: 'abc'},
    reference_paragraphs: ['A', 'B', 'C'], observed_paragraphs: ['A', 'C'],
    review_changes: [{kind: 'missing', reference_span: [1, 2], observed_span: [1, 1]}]
  })});
  await h.call('runParagraphCheck');
  assert.match(h.get('workflow-status').textContent, /SOURCE UNVERIFIED/);
  assert.match(h.get('workflow-status').className, /provisional/);
  assert.equal(h.get('workflow-output').textContent, 'A\n\nB\n\nC');
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

test('model evidence card distinguishes real-source held-out loss from constructed tie', async () => {
  const h = harness('app.js');
  h.context.fetch = async () => ({ok:true, json:async () => ({sources:{train:12,dev:6,test:6},queries:284,
    learned_correct:284,best_lexical_correct:284,baseline:'token_dice',accuracy_delta:0,
    unit_control_positives:8, real_source_audit:{development_sources:4,held_out_sources:4,
      held_out_units:8,learned_rank_correct:7,difflib_rank_correct:8,token_dice_rank_correct:8,
      direct_copy_exact:8,reversed_reference_exact:0,
      scope:'Gold is the same article JATS reference; not independent truth.'}})});
  await h.call('loadModelSummary');
  const summary = h.get('ml-summary').textContent;
  assert.match(summary, /7\/8/);
  assert.match(summary, /difflib 8\/8/);
  assert.match(summary, /same article JATS reference/);
  assert.match(summary, /not natural PDF errors/);
});

test('real-source evidence lists the two failed articles without source prose', async () => {
  const h = harness('app.js');
  h.context.fetch = async () => ({ok:true, json:async () => ({sources:{train:12,dev:6,test:6},queries:284,
    learned_correct:284,best_lexical_correct:284,baseline:'token_dice',accuracy_delta:0,
    unit_control_positives:8,real_source_audit:{development_sources:4,held_out_sources:4,
      held_out_units:8,learned_rank_correct:7,difflib_rank_correct:8,token_dice_rank_correct:8,
      direct_copy_exact:8,reversed_reference_exact:0,scope:'Gold is the same article JATS reference.',
      sources:[{source_id:'PMC12864593',split:'development',learned_rank_correct:1,compared_units:2,
        proposal_status:'ABSTAIN'},{source_id:'PMC12789962',split:'held_out',learned_rank_correct:1,
        compared_units:2,proposal_status:'ABSTAIN'}]}})});
  await h.call('loadModelSummary');
  assert.match(h.get('ml-source-rows').textContent, /PMC12864593.*development.*1\/2.*ABSTAIN/);
  assert.match(h.get('ml-source-rows').textContent, /PMC12789962.*held_out.*1\/2.*ABSTAIN/);
  assert.doesNotMatch(h.get('ml-source-rows').textContent, /Gold is the same article/);
});
