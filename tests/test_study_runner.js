'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const { validateManifest, buildSchedule, formatSpan, deriveBioSureView,
  ActiveTimer, parsePosition,
  makeRecord, recordTimedAnswer, buildExport } =
  require('../docs/study/app.js');

const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, '../docs/study/manifest.json'), 'utf8'));

test('manifest rejects missing attribution, decisions and invented participant results', () => {
  assert.equal(validateManifest(manifest), manifest);
  assert.match(manifest.manifest_sha256, /^[0-9a-f]{64}$/);
  assert.throws(() => validateManifest({ ...manifest, results: [] }));
  assert.throws(() => validateManifest({ ...manifest, tasks: manifest.tasks.slice(1) }));
  const altered = structuredClone(manifest);
  delete altered.tasks[6].source.license_uri;
  assert.throws(() => validateManifest(altered));
  const missingAuthors = structuredClone(manifest);
  delete missingAuthors.tasks[6].source.authors;
  assert.throws(() => validateManifest(missingAuthors));
  const noDecision = structuredClone(manifest);
  delete noDecision.tasks[0].biosure.receipt;
  assert.throws(() => validateManifest(noDecision));
  const badDiff = structuredClone(manifest);
  badDiff.tasks[0].plain_diff = [null];
  assert.throws(() => validateManifest(badDiff));
  const noReason = structuredClone(manifest);
  delete noReason.tasks[0].biosure.decision.reason_codes;
  assert.throws(() => validateManifest(noReason));
  const noModelStatus = structuredClone(manifest);
  delete noModelStatus.tasks[0].learned.proposal_status;
  assert.throws(() => validateManifest(noModelStatus));
  const abstainButApplied = structuredClone(manifest);
  const abstainTask = abstainButApplied.tasks.find(task => task.biosure.decision.action === 'ABSTAIN');
  abstainTask.biosure.selected_paragraphs = ['invented result'];
  assert.throws(() => validateManifest(abstainButApplied));
  const missingProposalGate = structuredClone(manifest);
  const proposedTask = missingProposalGate.tasks.find(task => task.learned.proposed_paragraphs != null);
  proposedTask.learned_gate = null;
  assert.throws(() => validateManifest(missingProposalGate));
  const falseProposalGate = structuredClone(manifest);
  const noProposalTask = falseProposalGate.tasks.find(task => task.learned.proposed_paragraphs == null);
  noProposalTask.learned_gate = proposedTask.biosure;
  assert.throws(() => validateManifest(falseProposalGate));
});

test('six slots rotate every case through all views, three cases per view', () => {
  const schedules = Array.from({ length: 6 }, (_, slot) => buildSchedule(manifest, slot));
  for (const schedule of schedules) {
    assert.equal(schedule.length, 9);
    assert.equal(new Set(schedule.map(item => item.task.id)).size, 9);
    for (const mode of ['manual', 'diff', 'biosure']) {
      assert.equal(schedule.filter(item => item.mode === mode).length, 3);
    }
  }
  for (const task of manifest.tasks) {
    const modes = schedules.map(schedule => schedule.find(item => item.task.id === task.id).mode);
    for (const mode of ['manual', 'diff', 'biosure']) {
      assert.equal(modes.filter(item => item === mode).length, 2);
    }
  }
  assert.deepEqual(buildSchedule(manifest, 2).map(item => item.task.id),
                   buildSchedule(manifest, 2).map(item => item.task.id));
  assert.deepEqual(buildSchedule(manifest, 0).map(item => item.task.id), [
    'public-PMC12707140-title', 'public-PMC12864593-title', 'sample-omission',
    'sample-ambiguous', 'sample-substitution', 'sample-unchanged',
    'sample-duplicate', 'sample-boundary', 'public-PMC12789962-title',
  ]);
  assert.throws(() => buildSchedule(manifest, 6));
});

test('plain diff presents half-open spans as readable paragraph positions', () => {
  assert.equal(formatSpan([0, 1]), 'paragraph 1');
  assert.equal(formatSpan([1, 3]), 'paragraphs 2–3');
  assert.equal(formatSpan([0, 0]), 'gap before paragraph 1');
  assert.equal(formatSpan([2, 2]), 'gap after paragraph 2');
});

test('BioSURE view separates model wording from each gate-selected output', () => {
  const omission = manifest.tasks.find(task => task.id === 'sample-omission');
  const applied = deriveBioSureView(omission);
  assert.equal(applied.originalAction, 'AUTO_REPAIR');
  assert.deepEqual(applied.originalSelected, omission.biosure.selected_paragraphs);
  assert.deepEqual(applied.modelProposal, omission.learned.proposed_paragraphs);
  assert.deepEqual(applied.modelGateSelected, omission.learned_gate.selected_paragraphs);
  const duplicate = manifest.tasks.find(task => task.id === 'sample-duplicate');
  const abstainedModel = deriveBioSureView(duplicate);
  assert.equal(abstainedModel.originalAction, 'AUTO_REPAIR');
  assert.equal(abstainedModel.modelProposal, null);
  assert.equal(abstainedModel.modelGateAction, null);
  const publicTitle = manifest.tasks.find(task => task.id === 'public-PMC12864593-title');
  assert.equal(deriveBioSureView(publicTitle).originalSelected, null);
});

test('active timer excludes hidden-tab time', () => {
  let now = 100;
  const timer = new ActiveTimer(() => now);
  timer.start();
  now = 340;
  timer.pause();
  now = 1400;
  assert.equal(timer.elapsed(), 240);
  assert.equal(timer.wallElapsed(), 1300);
  timer.resume();
  now = 1690;
  assert.equal(timer.stop(), 530);
  assert.equal(timer.elapsed(), 530);
  assert.equal(timer.wallElapsed(), 1590);
});

test('records require structured answer and never invent human metrics', () => {
  assert.equal(parsePosition('', 'yes'), null);
  assert.equal(parsePosition('  ', 'yes'), null);
  assert.equal(parsePosition('0', 'yes'), 0);
  assert.equal(parsePosition('1', 'no'), null);
  const item = buildSchedule(manifest, 0)[0];
  assert.throws(() => makeRecord(item, { difference: 'yes', disposition: 'copy' }, 1));
  assert.throws(() => makeRecord(item, { difference: 'yes', position: 999, disposition: 'copy' }, 1));
  assert.throws(() => makeRecord(item, { difference: 'no', position: 1, disposition: 'keep' }, 1));
  assert.throws(() => makeRecord(item, { difference: 'no', position: null, disposition: 'keep' }, 530, 500));
  const record = makeRecord(item, { difference: 'yes', position: 1, disposition: 'escalate' }, 530, 1590);
  assert.equal(record.active_ms, 530);
  assert.equal(record.wall_ms, 1590);
  assert.equal(record.task_id, item.task.id);
  const exported = buildExport(0, [record], manifest.manifest_sha256);
  assert.equal(exported.study_scope, 'instrument-only; automated or human origin must be reported separately');
  assert.equal(exported.manifest_sha256, manifest.manifest_sha256);
  assert.deepEqual(exported.records, [record]);
  assert.equal(JSON.stringify(exported).includes('timestamp'), false);
  assert.equal(JSON.stringify(exported).includes('participant_id'), false);
});

test('an invalid answer does not stop the active timer', () => {
  let now = 0;
  const timer = new ActiveTimer(() => now);
  timer.start();
  const item = buildSchedule(manifest, 0)[0];
  now = 100;
  assert.throws(() => recordTimedAnswer(item, { difference: 'yes', disposition: 'copy' }, timer));
  now = 350;
  const record = recordTimedAnswer(item,
    { difference: 'no', position: null, disposition: 'escalate' }, timer);
  assert.equal(record.active_ms, 350);
  assert.equal(record.wall_ms, 350);
  now = 900;
  assert.equal(timer.elapsed(), 350);
});

test('runner has no server-write, tracking or persistent-storage path', () => {
  const source = fs.readFileSync(path.join(__dirname, '../docs/study/app.js'), 'utf8');
  for (const forbidden of ['localStorage', 'sessionStorage', 'sendBeacon', 'XMLHttpRequest',
                           'method: "POST"', "method: 'POST'", 'analytics']) {
    assert.equal(source.includes(forbidden), false, forbidden);
  }
});
