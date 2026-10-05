const byId = (id) => document.getElementById(id);
const appendText = (parent, tag, value) => { const element = document.createElement(tag); element.textContent = value; parent.appendChild(element); return element; };
let activeDataset = "synthetic";
let loadVersion = 0;

async function getJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error("Local data unavailable");
  return response.json();
}

function clearCase() {
  for (const id of ["damaged-blocks", "candidate-list", "evidence-list"]) byId(id).replaceChildren();
  for (const id of ["record-id", "candidate-count", "reason", "receipt-hash", "selected-output"]) byId(id).textContent = "";
  byId("article-source").hidden = true;
  byId("decision").textContent = "Loading…";
  byId("decision").className = "decision";
}

function showBlocks(id, blocks, originalIds = new Set()) {
  const list = typeof id === "string" ? byId(id) : id;
  list.replaceChildren();
  for (const block of blocks) {
    const item = document.createElement("li");
    if (!originalIds.has(block.block_id)) item.classList.add("changed");
    appendText(item, "b", block.block_id);
    appendText(item, "code", block.kind + " · " + block.text_sha256.slice(0, 18) + "…");
    list.appendChild(item);
  }
}

function showCandidates(candidates, originalIds) {
  const list = byId("candidate-list");
  list.replaceChildren();
  for (const candidate of candidates) {
    const panel = document.createElement("section");
    panel.className = "candidate";
    appendText(panel, "h4", `${candidate.candidate_id} · ${candidate.operation}`);
    const blocks = document.createElement("ol");
    blocks.className = "blocks";
    showBlocks(blocks, candidate.document.blocks, originalIds);
    panel.appendChild(blocks);
    list.appendChild(panel);
  }
}

function showEvidence(evidence) {
  const list = byId("evidence-list");
  list.replaceChildren();
  const entries = [...evidence.trusted_insertions, ...evidence.trusted_identities];
  if (!entries.length) {
    appendText(list, "dt", "Source");
    appendText(list, "dd", "No trusted candidate evidence supplied.");
  }
  for (const item of entries) {
    appendText(list, "dt", "Source ID");
    appendText(list, "dd", item.source_id);
    appendText(list, "dt", "Constraint");
    appendText(list, "dd", item.block_id ? `${item.before_id} → ${item.block_id} → ${item.after_id}` : `retain ${item.retained_block_id}; remove ${item.duplicate_block_id}`);
    appendText(list, "dt", "Expected text hash");
    appendText(list, "dd", item.text_sha256.slice(0, 24) + "…");
  }
}

async function loadCase(name, dataset = activeDataset, version = ++loadVersion) {
  const data = await getJSON("/api/case/" + encodeURIComponent(name) + "?dataset=" + encodeURIComponent(dataset));
  if (version !== loadVersion) return;
  const originalIds = new Set(data.request.damaged.blocks.map((block) => block.block_id));
  byId("record-id").textContent = data.request.damaged.record_id;
  byId("candidate-count").textContent = data.request.candidates.length + " candidate(s)";
  showBlocks("damaged-blocks", data.request.damaged.blocks, originalIds);
  showCandidates(data.request.candidates, originalIds);
  showEvidence(data.request.evidence);
  byId("article-source").hidden = !data.source;
  if (data.source) {
    const link = byId("article-link");
    link.textContent = data.source.title;
    link.href = "https://pmc.ncbi.nlm.nih.gov/articles/" + encodeURIComponent(data.source.pmcid) + "/";
    byId("article-doi").textContent = data.source.pmcid + " · DOI " + data.source.doi;
  }
  const decision = byId("decision");
  decision.textContent = data.decision.action === "AUTO_REPAIR" ? "AUTO REPAIR" : "ABSTAIN";
  decision.className = "decision " + (data.decision.action === "AUTO_REPAIR" ? "auto" : "abstain");
  byId("reason").textContent = data.decision.reason_codes.length ? data.decision.reason_codes.join(" · ") : "One uniquely supported candidate.";
  byId("receipt-hash").textContent = data.receipt.receipt_sha256;
  byId("selected-output").textContent = data.receipt.selected_output_sha256 || "No output applied";
}

async function loadDataset(dataset) {
  activeDataset = dataset;
  const version = ++loadVersion;
  const select = byId("case-select");
  select.replaceChildren();
  select.disabled = true;
  clearCase();
  byId("coverage").textContent = "—";
  byId("public-summary").textContent = "Loading…";
  byId("coverage-caption").textContent = "Loading selected evaluation set…";
  byId("dataset-count").textContent = "Loading…";
  try {
    const query = "?dataset=" + encodeURIComponent(dataset);
    const [listing, summary] = await Promise.all([
      getJSON("/api/cases" + query), getJSON("/api/summary" + query)
    ]);
    if (version !== loadVersion) return;
    if (!listing.cases.length) throw new Error("This evaluation set has no cases");
    for (const name of listing.cases) appendText(select, "option", name).value = name;
    select.value = listing.cases[0];
    select.disabled = false;
    byId("stat-label").textContent = "Fixed constructed graph test";
    for (const id of ["workbench-title", "public-results-title"]) byId(id).textContent = listing.label;
    byId("dataset-note").textContent = listing.note;
    byId("dataset-count").textContent = `${summary.cases} derived cases · ${summary.source_graphs} source graphs`;
    byId("coverage").textContent = `${summary.automatic} / ${summary.cases}`;
    byId("coverage-caption").textContent = "Automatic gate decisions on supplied graph evidence; not user-document corrections.";
    byId("public-summary").textContent = `${summary.exact_auto} exact automatic repairs, ${summary.abstentions} abstentions, ${summary.incorrect_auto} incorrect automatic repairs. Schema/locality: ${summary.schema_locality_baseline.automatic} applied / ${summary.schema_locality_baseline.incorrect_auto} incorrect. Hash-only evidence: ${summary.hash_evidence_baseline.automatic} applied / ${summary.hash_evidence_baseline.incorrect_auto} incorrect. Whole-graph evidence reconstruction: ${summary.evidence_reconstruction_baseline.automatic} applied / ${summary.evidence_reconstruction_baseline.incorrect_auto} incorrect. All evidence comparators receive the same declared references. ${summary.source_graphs} source graphs underlie these cases.`;
    await loadCase(select.value, dataset, version);
  } catch (error) {
    if (version === loadVersion) {
      byId("public-summary").textContent = "Evaluation data unavailable.";
      byId("coverage").textContent = "—";
      byId("coverage-caption").textContent = "Evaluation data unavailable.";
      byId("dataset-count").textContent = "Data unavailable";
      showError(error);
    }
  }
}

async function loadModelSummary() {
  try {
    const result = await getJSON('/api/ml-summary');
    const constructed = `${result.learned_correct}/${result.queries} intended references found on ${result.sources.test} unseen articles. The learned model ties ${result.baseline} (${result.best_lexical_correct}/${result.queries}); accuracy difference ${result.accuracy_delta.toFixed(3)}. ${result.unit_control_positives} constructed unit-change alerts tested. This is not natural PDF errors or biological validation.`;
    const real = result.real_source_audit;
    const sourceAudit = real ? ` Separate real-source extraction audit: ${real.held_out_sources} held-out sources, learned rank ${real.learned_rank_correct}/${real.held_out_units}; difflib ${real.difflib_rank_correct}/${real.held_out_units}, token Dice ${real.token_dice_rank_correct}/${real.held_out_units}, correct-reference copy ${real.direct_copy_exact}/${real.held_out_units}, reversed-reference failure control ${real.reversed_reference_exact}/${real.held_out_units}. ${real.scope}` : '';
    byId('ml-summary').textContent = constructed + sourceAudit;
    byId('ml-source-rows').textContent = real && real.sources
      ? real.sources.map(row => `${row.source_id} · ${row.split} · learned ${row.learned_rank_correct}/${row.compared_units} · ${row.proposal_status}`).join('\n')
      : 'Source-level audit unavailable in these fixtures.';
  } catch (error) {
    byId('ml-summary').textContent = 'Model evaluation unavailable in these fixtures.';
    byId('ml-source-rows').textContent = '';
  }
}

async function init() {
  byId("dataset-select").addEventListener("change", () => loadDataset(byId("dataset-select").value));
  byId("case-select").addEventListener("change", () => {
    const version = ++loadVersion;
    clearCase();
    loadCase(byId("case-select").value, activeDataset, version).catch((error) => {
      if (version === loadVersion) showError(error);
    });
  });
  loadDataset(byId("dataset-select").value || "synthetic");
  loadModelSummary();
  try {
    const prior = await getJSON("/api/prior");
    byId("prior-card").hidden = false;
    byId("dke-summary").textContent = `${prior.automatic}/${prior.held_out} known-spec inversions were automatically applied and exact; ${prior.abstained} source-unavailable cases abstained. This is prior methodological evidence, not the new blind-mode score.`;
  } catch (error) { byId("prior-card").hidden = true; }
}

function showError(error) {
  clearCase();
  byId("decision").textContent = "DATA UNAVAILABLE";
  byId("decision").className = "decision abstain";
  byId("reason").textContent = error.message || "Could not load the local case.";
}

init();
