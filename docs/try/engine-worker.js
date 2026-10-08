/* Pyodide runs the unchanged public Python text engine. No document upload. */
'use strict';

const PYODIDE_BASE = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/';
let enginePromise;

function loadEngine() {
  if (!enginePromise) enginePromise = (async () => {
    importScripts(PYODIDE_BASE + 'pyodide.js');
    const pyodide = await loadPyodide({ indexURL: PYODIDE_BASE });
    const [archive, model] = await Promise.all([fetch('./engine.zip'), fetch('./model.json')]);
    if (!archive.ok || !model.ok) throw new Error('Browser engine assets are unavailable.');
    pyodide.FS.writeFile('/biosure-engine.zip', new Uint8Array(await archive.arrayBuffer()));
    pyodide.runPython('import sys; sys.path.insert(0, "/biosure-engine.zip")');
    const modelJson = await model.text();
    JSON.parse(modelJson);
    return { pyodide, modelJson };
  })().catch(error => { enginePromise = undefined; throw error; });
  return enginePromise;
}

self.onmessage = async event => {
  const { id, payload } = event.data || {};
  try {
    const { pyodide, modelJson } = await loadEngine();
    pyodide.globals.set('payload_json', JSON.stringify(payload));
    pyodide.globals.set('model_json', modelJson);
    const result = JSON.parse(pyodide.runPython(`
import json
from biosure.workflow import run_workflow
from biosure.learned_upstream import propose_learned
from biosure.ml_review import critical_changes
payload = json.loads(payload_json)
model = json.loads(model_json)
workflow = run_workflow(payload)
learned = propose_learned(payload, model)
critical_alerts = []
critical_unchecked_spans = []
for change in workflow['review_changes']:
    if change['kind'] != 'changed':
        continue
    start_ref, end_ref = change['reference_span']
    start_obs, end_obs = change['observed_span']
    if end_ref - start_ref != end_obs - start_obs:
        critical_unchecked_spans.append({'reference_span': change['reference_span'],
                                         'observed_span': change['observed_span']})
        continue  # No trustworthy one-to-one paragraph pairing in this span.
    for reference_index, observed_index in zip(range(start_ref, end_ref), range(start_obs, end_obs)):
        difference = critical_changes(workflow['reference_paragraphs'][reference_index],
                                      workflow['observed_paragraphs'][observed_index])
        if difference['flags']:
            critical_alerts.append({'reference_index': reference_index,
                                    'observed_index': observed_index, **difference})
json.dumps({"workflow": workflow, "learned": learned,
            "critical_alerts": critical_alerts,
            "critical_unchecked_spans": critical_unchecked_spans}, ensure_ascii=False)
`));
    self.postMessage({ id, result });
  } catch (error) {
    self.postMessage({ id, error: String(error.message || error) });
  }
};
