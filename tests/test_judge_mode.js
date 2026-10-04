const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const { validateBundle, deriveView, loadBundle, formatSpan } = require('../docs/judge/app.js');
const bundle = JSON.parse(fs.readFileSync(path.join(__dirname, '../docs/judge/data.json'), 'utf8'));

test('rejects altered or incomplete gate results before rendering', () => {
  assert.equal(validateBundle(bundle).scenarios.length, 3);
  const altered = structuredClone(bundle);
  altered.scenarios[0].workflow.decision.action = 'APPROVE';
  assert.throws(() => validateBundle(altered), /invalid gate action/);
  const incomplete = structuredClone(bundle);
  delete incomplete.scenarios[0].workflow.receipt;
  assert.throws(() => validateBundle(incomplete), /receipt/);
});

test('real public case visibly abstains and disclaims source authority', () => {
  const view = deriveView(bundle.scenarios[0]);
  assert.equal(view.sourceUnverified, true);
  assert.equal(view.gateAction, 'ABSTAIN');
  assert.equal(view.selectedParagraphs, null);
  assert.equal(view.learnedProposalNote, 'No model proposal: LOW_CONFIDENCE.');
  assert.equal(view.isFictional, false);
  assert.ok(view.changes.length > 0);
  assert.match(view.articleUrl, /PMC12864593/);
});

test('fictional bounded fix and invented proposal stay separate', () => {
  const accepted = deriveView(bundle.scenarios[1]);
  const rejected = deriveView(bundle.scenarios[2]);
  assert.equal(accepted.isFictional, true);
  assert.equal(accepted.gateAction, 'AUTO_REPAIR');
  assert.deepEqual(accepted.selectedParagraphs, bundle.scenarios[1].input.reference_paragraphs);
  assert.equal(rejected.proposalAction, 'ABSTAIN');
  assert.equal(rejected.proposalSelectedParagraphs, null);
});

test('failed asset fetch returns an error rather than a staged result', async () => {
  const failed = await loadBundle(async () => ({ ok: false, status: 503 }));
  assert.equal(failed.ok, false);
  assert.match(failed.error, /503/);
  assert.equal(failed.data, undefined);
});

test('half-open engine spans display actual paragraph positions', () => {
  assert.equal(formatSpan([0, 1]), 'paragraph 1');
  assert.equal(formatSpan([1, 3]), 'paragraphs 2–3');
  assert.equal(formatSpan([1, 1]), 'gap after paragraph 1');
});
