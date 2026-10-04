/* Local-first comparison instrument. It does not collect or publish results. */
(function () {
  'use strict';

  const MODES = ['manual', 'diff', 'biosure'];
  const DISPOSITIONS = ['keep', 'copy', 'escalate'];

  function object(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function paragraphs(value) {
    return Array.isArray(value) && value.length > 0 &&
      value.every(item => typeof item === 'string' && item.length > 0);
  }

  function validSpan(value, limit) {
    return Array.isArray(value) && value.length === 2 &&
      Number.isInteger(value[0]) && Number.isInteger(value[1]) &&
      value[0] >= 0 && value[0] <= value[1] && value[1] <= limit;
  }

  function validDecisionResult(result) {
    return object(result) && object(result.decision) &&
      ['ABSTAIN', 'AUTO_REPAIR', 'NO_CHANGE'].includes(result.decision.action) &&
      Array.isArray(result.decision.reason_codes) &&
      result.decision.reason_codes.every(code => typeof code === 'string') &&
      object(result.receipt) &&
      /^[0-9a-f]{64}$/.test(result.receipt.receipt_sha256 || '') &&
      !(result.decision.action === 'ABSTAIN' && result.selected_paragraphs != null) &&
      !(result.decision.action === 'AUTO_REPAIR' && !paragraphs(result.selected_paragraphs));
  }

  function validateManifest(bundle) {
    if (!object(bundle) || bundle.schema_version !== 'biosure.practical-study/1.0' ||
        !/^[0-9a-f]{64}$/.test(bundle.manifest_sha256 || '') ||
        !Array.isArray(bundle.tasks) || bundle.tasks.length !== 9 ||
        'participants' in bundle || 'results' in bundle) {
      throw new Error('invalid or result-bearing study manifest');
    }
    const ids = new Set();
    let fictional = 0;
    let publicCount = 0;
    for (const task of bundle.tasks) {
      if (!object(task) || typeof task.id !== 'string' || ids.has(task.id) ||
          typeof task.label !== 'string' ||
          !['fictional', 'public-article'].includes(task.kind) ||
          !object(task.source) || !object(task.input) ||
          !paragraphs(task.input.observed_paragraphs) ||
          !paragraphs(task.input.reference_paragraphs) ||
          !Array.isArray(task.plain_diff) || !validDecisionResult(task.biosure) ||
          !object(task.learned) ||
          !['ABSTAIN', 'PROPOSED_FOR_REVIEW'].includes(task.learned.proposal_status) ||
          typeof task.learned.proposal_reason !== 'string' ||
          (task.learned.proposal_status === 'ABSTAIN' && task.learned.proposed_paragraphs != null) ||
          (task.learned.proposal_status === 'PROPOSED_FOR_REVIEW' &&
            !paragraphs(task.learned.proposed_paragraphs)) ||
          (task.learned.proposed_paragraphs == null && task.learned_gate != null) ||
          (task.learned.proposed_paragraphs != null && !validDecisionResult(task.learned_gate)) ||
          !task.plain_diff.every(change => object(change) &&
            ['replace', 'delete', 'insert'].includes(change.tag) &&
            validSpan(change.observed_span, task.input.observed_paragraphs.length) &&
            validSpan(change.reference_span, task.input.reference_paragraphs.length)) ||
          'answer_key' in task || 'correct_disposition' in task) {
        throw new Error('invalid study task');
      }
      if (task.kind === 'public-article') {
        publicCount++;
        if (typeof task.source.article_url !== 'string' ||
            !task.source.article_url.startsWith('https://pmc.ncbi.nlm.nih.gov/articles/') ||
            task.source.license_uri !== 'https://creativecommons.org/licenses/by/4.0/' ||
            !Array.isArray(task.source.authors) || !task.source.authors.length ||
            !task.source.authors.every(author => typeof author === 'string' && author.trim()) ||
            typeof task.source.title !== 'string' || typeof task.source.doi !== 'string' ||
            typeof task.source.change_notice !== 'string') {
          throw new Error('missing public-article attribution');
        }
      } else {
        fictional++;
        if (task.source.note !== 'Project-authored fictional control') {
          throw new Error('fictional control label is missing');
        }
      }
      ids.add(task.id);
    }
    if (fictional !== 6 || publicCount !== 3) throw new Error('unexpected task mix');
    return bundle;
  }

  function hashOrder(value) {
    let hash = 2166136261;
    for (const char of value) {
      hash ^= char.codePointAt(0);
      hash = Math.imul(hash, 16777619);
    }
    return hash >>> 0;
  }

  function buildSchedule(bundle, slot) {
    validateManifest(bundle);
    if (!Number.isInteger(slot) || slot < 0 || slot > 5) throw new Error('slot must be 0–5');
    return bundle.tasks.map((task, index) => ({
      task, mode: MODES[(index + slot) % MODES.length],
    })).sort((a, b) =>
      hashOrder(`${slot}:${a.task.id}`) - hashOrder(`${slot}:${b.task.id}`) ||
      a.task.id.localeCompare(b.task.id));
  }

  class ActiveTimer {
    constructor(clock = () => performance.now()) {
      this.clock = clock;
      this.active = 0;
      this.since = null;
      this.origin = null;
      this.finishedWall = null;
      this.ended = false;
    }
    start() {
      this.active = 0;
      this.origin = this.clock();
      this.since = this.origin;
      this.finishedWall = null;
      this.ended = false;
    }
    pause() {
      if (this.since !== null) {
        this.active += Math.max(0, this.clock() - this.since);
        this.since = null;
      }
    }
    resume() {
      if (!this.ended && this.since === null) this.since = this.clock();
    }
    elapsed() {
      return Math.round(this.active +
        (this.since === null ? 0 : Math.max(0, this.clock() - this.since)));
    }
    wallElapsed() {
      if (this.finishedWall !== null) return this.finishedWall;
      return this.origin === null ? 0 : Math.max(this.elapsed(),
        Math.round(Math.max(0, this.clock() - this.origin)));
    }
    stop() {
      this.pause();
      this.finishedWall = this.wallElapsed();
      this.ended = true;
      return this.elapsed();
    }
  }

  function parsePosition(raw, difference) {
    if (difference !== 'yes') return null;
    if (raw == null || String(raw).trim() === '') return null;
    return Number(raw);
  }

  function makeRecord(item, answer, activeMs, wallMs = activeMs) {
    if (!object(item) || !object(item.task) || !MODES.includes(item.mode) ||
        !object(answer) || !['yes', 'no', 'unsure'].includes(answer.difference) ||
        !DISPOSITIONS.includes(answer.disposition) ||
        !Number.isInteger(activeMs) || activeMs < 0 ||
        !Number.isInteger(wallMs) || wallMs < activeMs) {
      throw new Error('incomplete study answer');
    }
    const maxPosition = item.task.input.reference_paragraphs.length;
    if (answer.difference === 'yes' &&
        (!Number.isInteger(answer.position) || answer.position < 0 || answer.position > maxPosition)) {
      throw new Error('first changed reference position is required');
    }
    if (answer.difference !== 'yes' && answer.position != null) {
      throw new Error('position must be empty when discrepancy is not identified');
    }
    return {
      task_id: item.task.id,
      source_kind: item.task.kind,
      mode: item.mode,
      difference: answer.difference,
      first_changed_reference_position: answer.difference === 'yes' ? answer.position : null,
      disposition: answer.disposition,
      active_ms: activeMs,
      wall_ms: wallMs,
    };
  }

  function recordTimedAnswer(item, answer, timer) {
    const record = makeRecord(item, answer, timer.elapsed(), timer.wallElapsed());
    timer.stop();
    return record;
  }

  function buildExport(slot, records, manifestSha) {
    if (!Number.isInteger(slot) || slot < 0 || slot > 5 || !Array.isArray(records) ||
        !/^[0-9a-f]{64}$/.test(manifestSha || '')) {
      throw new Error('invalid study session');
    }
    return {
      schema_version: 'biosure.practical-study-session/1.0',
      study_scope: 'instrument-only; automated or human origin must be reported separately',
      manifest_sha256: manifestSha,
      assignment_slot: slot,
      records: records.map(record => ({ ...record })),
    };
  }

  function textNode(tag, value, className = '') {
    const node = document.createElement(tag);
    node.textContent = String(value);
    if (className) node.className = className;
    return node;
  }

  function renderParagraphs(target, values) {
    const list = document.createElement('ol');
    for (const value of values) list.append(textNode('li', value));
    target.replaceChildren(list);
  }

  function formatSpan(span) {
    const [start, end] = span;
    if (start === end) return start === 0 ? 'gap before paragraph 1' : `gap after paragraph ${start}`;
    return end === start + 1 ? `paragraph ${start + 1}` : `paragraphs ${start + 1}–${end}`;
  }

  function deriveBioSureView(task) {
    return {
      originalAction: task.biosure.decision.action,
      originalReasons: task.biosure.decision.reason_codes,
      originalSelected: task.biosure.selected_paragraphs,
      modelStatus: task.learned.proposal_status,
      modelReason: task.learned.proposal_reason,
      modelProposal: task.learned.proposed_paragraphs,
      modelGateAction: task.learned_gate?.decision.action || null,
      modelGateReasons: task.learned_gate?.decision.reason_codes || [],
      modelGateSelected: task.learned_gate?.selected_paragraphs || null,
      receiptSha256: task.biosure.receipt.receipt_sha256,
    };
  }

  function appendOutput(panel, heading, values, emptyText) {
    panel.append(textNode('h3', heading));
    if (values) {
      const target = document.createElement('div');
      renderParagraphs(target, values);
      panel.append(target);
    } else {
      panel.append(textNode('p', emptyText));
    }
  }

  function renderMode(item) {
    const panel = document.getElementById('mode-detail');
    panel.replaceChildren();
    if (item.mode === 'manual') {
      panel.append(textNode('p', 'Plain side-by-side view: no computed difference marks or gate advice.'));
    } else if (item.mode === 'diff') {
      panel.append(textNode('p', 'Ordinary paragraph diff only; no AI or source verification.'));
      const changes = item.task.plain_diff;
      panel.append(textNode('p', changes.length ? changes.map(change =>
        `${change.tag}: observed ${formatSpan(change.observed_span)}, reference ${formatSpan(change.reference_span)}`
      ).join('; ') : 'No paragraph difference found.'));
    } else {
      const view = deriveBioSureView(item.task);
      panel.append(textNode('p', 'SOURCE UNVERIFIED. The fitted model ranks correspondence; the gate decides separately.'));
      panel.append(textNode('p', `Model: ${view.modelStatus} · ${view.modelReason}`));
      appendOutput(panel, 'Model candidate wording', view.modelProposal,
        'The model abstained; no candidate wording.');
      panel.append(textNode('p', `Original conversion gate: ${view.originalAction} · ${view.originalReasons.join(', ') || 'no reason code'}`));
      appendOutput(panel, 'Selected original-workflow output', view.originalSelected,
        'No original-workflow replacement applied.');
      if (view.modelGateAction) {
        panel.append(textNode('p', `Model proposal gate: ${view.modelGateAction} · ${view.modelGateReasons.join(', ') || 'no reason code'}`));
        appendOutput(panel, 'Selected model-proposal output', view.modelGateSelected,
          'No model-proposal replacement applied.');
      } else {
        panel.append(textNode('p', 'Model proposal gate: not run because the model abstained.'));
      }
      panel.append(textNode('p', `Original receipt SHA-256: ${view.receiptSha256}`, 'digest'));
      panel.append(textNode('p', 'Any selected wording comes from the declared reference, not independently verified source truth.'));
    }
  }

  async function init() {
    const status = document.getElementById('status');
    const start = document.getElementById('start');
    const form = document.getElementById('answer-form');
    if (!status || !start || !form) return;
    start.disabled = true;
    let bundle;
    try {
      const response = await fetch('./manifest.json', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      bundle = validateManifest(await response.json());
    } catch (error) {
      status.textContent = `Study instrument unavailable: ${error.message}`;
      status.className = 'error';
      return;
    }
    status.textContent = 'Nine frozen tasks loaded: six fictional controls and three public article titles. No answers are pre-filled.';
    start.disabled = false;
    let schedule = [];
    let slot = 0;
    let index = 0;
    const records = [];
    let timer = null;

    function showTask() {
      const item = schedule[index];
      if (!item) {
        document.getElementById('task-panel').hidden = true;
        document.getElementById('end-panel').hidden = false;
        document.getElementById('completed-count').textContent = String(records.length);
        return;
      }
      document.getElementById('progress').textContent = `Task ${index + 1} of ${schedule.length}`;
      document.getElementById('task-label').textContent = item.task.label;
      document.getElementById('mode-name').textContent = {
        manual: 'Plain side-by-side', diff: 'Ordinary paragraph diff', biosure: 'BioSURE review',
      }[item.mode];
      document.getElementById('source-kind').textContent = item.task.kind === 'fictional'
        ? 'FICTIONAL CONTROL — not natural-source evidence'
        : 'PUBLIC CC BY 4.0 ARTICLE TITLE — source truth not independently adjudicated';
      const link = document.getElementById('article-link');
      const credit = document.getElementById('source-credit');
      link.hidden = item.task.kind !== 'public-article';
      credit.hidden = item.task.kind !== 'public-article';
      if (item.task.kind === 'public-article') {
        link.href = item.task.source.article_url;
        credit.textContent = `${item.task.source.authors.join(', ')}. ${item.task.source.title}. DOI ${item.task.source.doi}. CC BY 4.0. ${item.task.source.change_notice}`;
      } else {
        link.removeAttribute('href');
        credit.textContent = '';
      }
      renderParagraphs(document.getElementById('observed'), item.task.input.observed_paragraphs);
      renderParagraphs(document.getElementById('reference'), item.task.input.reference_paragraphs);
      renderMode(item);
      form.reset();
      const position = document.getElementById('position');
      position.required = false;
      position.max = String(item.task.input.reference_paragraphs.length);
      position.disabled = true;
      timer = new ActiveTimer();
      timer.start();
      if (document.hidden) timer.pause();
    }

    start.addEventListener('click', () => {
      slot = Number(document.getElementById('slot').value);
      schedule = buildSchedule(bundle, slot);
      index = 0;
      document.getElementById('intro').hidden = true;
      document.getElementById('task-panel').hidden = false;
      showTask();
    });
    document.getElementById('difference').addEventListener('change', event => {
      const position = document.getElementById('position');
      const isYes = event.target.value === 'yes';
      position.disabled = !isYes;
      position.required = isYes;
      if (!isYes) position.value = '';
    });
    document.addEventListener('visibilitychange', () => {
      if (!timer) return;
      if (document.hidden) timer.pause();
      else timer.resume();
    });
    form.addEventListener('submit', event => {
      event.preventDefault();
      const data = new FormData(form);
      const difference = data.get('difference');
      const answer = {
        difference,
        position: parsePosition(data.get('position'), difference),
        disposition: data.get('disposition'),
      };
      try {
        records.push(recordTimedAnswer(schedule[index], answer, timer));
      } catch (error) {
        document.getElementById('task-error').textContent = error.message;
        return;
      }
      document.getElementById('task-error').textContent = '';
      index++;
      showTask();
    });
    document.getElementById('download').addEventListener('click', () => {
      const blob = new Blob([JSON.stringify(buildExport(slot, records, bundle.manifest_sha256), null, 2) + '\n'],
                            { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'biosure-study-session.json';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { validateManifest, buildSchedule, formatSpan, deriveBioSureView, ActiveTimer,
      parsePosition, makeRecord, recordTimedAnswer, buildExport };
  }
  if (typeof document !== 'undefined') document.addEventListener('DOMContentLoaded', init);
})();
