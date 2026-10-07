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
payload = json.loads(payload_json)
model = json.loads(model_json)
json.dumps({"workflow": run_workflow(payload), "learned": propose_learned(payload, model)}, ensure_ascii=False)
`));
    self.postMessage({ id, result });
  } catch (error) {
    self.postMessage({ id, error: String(error.message || error) });
  }
};
