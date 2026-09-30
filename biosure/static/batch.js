const batchElement = (id) => document.getElementById(id);
let batchVersion = 0;
let batchResult = null;

function resetBatchResult() {
  ++batchVersion;
  batchResult = null;
  batchElement("download-batch").disabled = true;
  batchElement("run-batch").disabled = false;
  batchElement("batch-records").replaceChildren();
  batchElement("batch-status").textContent = "READY";
  batchElement("batch-status").className = "decision";
  batchElement("batch-summary").textContent = "No batch result yet.";
}

function batchError(message) {
  batchElement("batch-status").textContent = "BATCH NOT ACCEPTED";
  batchElement("batch-status").className = "decision abstain";
  batchElement("batch-summary").textContent = message;
}

function clearBatch() {
  resetBatchResult();
  batchElement("batch-input").value = "";
  batchElement("batch-file").value = "";
  batchElement("batch-ack").checked = false;
}

async function loadBatch() {
  clearBatch();
  const version = batchVersion;
  batchElement("batch-summary").textContent = "Loading fictional examples…";
  try {
    const response = await fetch("/api/examples/batch");
    const data = await response.json();
    if (version !== batchVersion) return;
    if (!response.ok) throw new Error("Fictional examples unavailable.");
    batchElement("batch-input").value = JSON.stringify(data, null, 2);
    batchElement("batch-summary").textContent = "Six fictional records loaded; acknowledge the reference assumption before checking.";
  } catch (error) {
    if (version === batchVersion) batchError(error.message);
  }
}

async function importBatch() {
  const file = batchElement("batch-file").files[0];
  resetBatchResult();
  batchElement("batch-ack").checked = false;
  batchElement("batch-input").value = "";
  const version = batchVersion;
  if (!file) return;
  try {
    if (file.size > 1048576) throw new Error("File exceeds 1 MiB; use the CLI for larger batches.");
    const text = await file.text();
    if (version !== batchVersion) return;
    batchElement("batch-input").value = text;
    batchElement("batch-summary").textContent = "JSON imported locally. No original file was changed. Acknowledge the reference assumption before checking.";
  } catch (error) {
    if (version === batchVersion) batchError(error.message);
  }
}

function renderBatch(data) {
  batchResult = data;
  batchElement("batch-status").textContent = "BATCH CHECKED";
  batchElement("batch-status").className = "decision auto";
  const summary = data.summary;
  batchElement("batch-summary").textContent = summary.records + " records · " + summary.automatic + " corrected · " + summary.unchanged + " unchanged · " + summary.review_required + " require review. These are reference-conditioned decisions, not authenticated facts.";
  for (const result of data.results) {
    const item = document.createElement("details");
    item.className = "batch-record";
    const heading = document.createElement("summary");
    const automatic = result.decision.action === "AUTO_REPAIR";
    heading.textContent = result.request.damaged.record_id + " · " + (automatic ? "CORRECTED" : result.adapter_status === "NO_CHANGE" ? "UNCHANGED" : "REVIEW REQUIRED");
    const reason = document.createElement("p");
    reason.textContent = result.adapter_status + " · " + (result.decision.reason_codes.join(" · ") || "One supported edit.");
    const output = document.createElement("pre");
    output.textContent = automatic ? result.selected_paragraphs.join("\n\n") : "No automatic output applied. Inspect the supplied reference and converted text manually.";
    const receipt = document.createElement("code");
    receipt.textContent = "Receipt SHA-256: " + result.receipt.receipt_sha256;
    item.append(heading, reason, output, receipt);
    batchElement("batch-records").append(item);
  }
  batchElement("download-batch").disabled = false;
}

async function checkBatch() {
  resetBatchResult();
  const version = batchVersion;
  if (!batchElement("batch-ack").checked) {
    batchError("Acknowledge the batch reference assumption before checking.");
    return;
  }
  batchElement("run-batch").disabled = true;
  batchElement("batch-status").textContent = "CHECKING…";
  try {
    const body = batchElement("batch-input").value;
    if (new TextEncoder().encode(body).length > 1048576) throw new Error("JSON exceeds 1 MiB; use the CLI for larger batches.");
    const parsed = JSON.parse(body);
    if (!Array.isArray(parsed) || parsed.length < 1 || parsed.length > 100) throw new Error("Expected a JSON array of 1–100 workflow records.");
    // Send the original string: server strict parsing must still detect duplicate keys.
    const response = await fetch("/api/batch", {method: "POST", headers: {"Content-Type": "application/json"}, body});
    const data = await response.json();
    if (version !== batchVersion) return;
    if (!response.ok) throw new Error(data.error || "Batch input rejected.");
    renderBatch(data);
  } catch (error) {
    if (version === batchVersion) batchError(error.message);
  } finally {
    if (version === batchVersion) batchElement("run-batch").disabled = false;
  }
}

function downloadBatch() {
  if (!batchResult) return;
  const blob = new Blob([JSON.stringify(batchResult, null, 2) + "\n"], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "biosure-batch-results.json";
  link.click();
  URL.revokeObjectURL(url);
}

batchElement("load-batch").addEventListener("click", loadBatch);
batchElement("batch-file").addEventListener("change", importBatch);
batchElement("batch-input").addEventListener("input", resetBatchResult);
batchElement("batch-ack").addEventListener("change", resetBatchResult);
batchElement("run-batch").addEventListener("click", checkBatch);
batchElement("clear-batch").addEventListener("click", clearBatch);
batchElement("download-batch").addEventListener("click", downloadBatch);
