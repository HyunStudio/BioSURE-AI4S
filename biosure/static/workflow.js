const workflowElement = (id) => document.getElementById(id);
let workflowVersion = 0;
let workflowResult = null;

function resetWorkflowResult() {
  ++workflowVersion;
  workflowResult = null;
  workflowElement("download-result").disabled = true;
  workflowElement("run-workflow").disabled = false;
  workflowElement("run-candidate").disabled = false;
  workflowElement("workflow-output").textContent = "";
  workflowElement("workflow-changes").textContent = "";
  workflowElement("workflow-receipt").textContent = "";
  workflowElement("workflow-status").textContent = "READY";
  workflowElement("workflow-status").className = "decision";
  workflowElement("workflow-reason").textContent = "Your reference is a declared assumption. No result applied yet.";
}

function clearWorkflow() {
  resetWorkflowResult();
  for (const id of ["reference-input", "observed-input", "candidate-input"]) workflowElement(id).value = "";
  workflowElement("reference-ack").checked = false;
}

function loadWorkflowExample() {
  clearWorkflow();
  const reference = [
    "Fictitious OoC example: this record links an assay section to a source document.",
    "The source methods paragraph describes the channel preparation workflow.",
    "The source results paragraph points to a separate measurement record.",
    "Closing note: this sample contains no real experimental claims."
  ];
  const observed = [...reference];
  const mode = workflowElement("example-select").value;
  if (mode === "duplicate") observed.splice(2, 0, reference[1]);
  else if (mode === "substitution") observed[1] = "This changed paragraph is not supported by the source.";
  else observed.splice(1, 1);
  workflowElement("reference-input").value = reference.join("\n\n");
  workflowElement("observed-input").value = observed.join("\n\n");
}

function paragraphs(text) {
  return text.replace(/\r\n?/g, "\n").trim().split(/\n\s*\n/).map((part) => part.trim());
}

async function submitWorkflow(endpoint, body) {
  resetWorkflowResult();
  const version = workflowVersion;
  if (!workflowElement("reference-ack").checked) {
    workflowElement("workflow-reason").textContent = "Acknowledge the reference assumption before checking.";
    return;
  }
  workflowElement("run-workflow").disabled = true;
  workflowElement("run-candidate").disabled = true;
  workflowElement("workflow-status").textContent = "CHECKING…";
  try {
    const response = await fetch(endpoint, {method: "POST", headers: {"Content-Type": "application/json"}, body});
    const data = await response.json();
    if (version !== workflowVersion) return;
    if (!response.ok) throw new Error(data.error || "Input check failed");
    workflowResult = data;
    const automatic = data.decision.action === "AUTO_REPAIR";
    workflowElement("workflow-status").textContent = automatic ? "REFERENCE MATCH · APPLIED" : "NO AUTOMATIC CHANGE";
    workflowElement("workflow-status").className = "decision " + (automatic ? "auto" : "abstain");
    workflowElement("workflow-reason").textContent = (data.adapter_status || "DECLARED_CANDIDATE") + " · " + (data.decision.reason_codes.join(" · ") || "One uniquely supported bounded edit.") + " Reference authenticity and biological meaning are not verified.";
    workflowElement("workflow-output").textContent = data.selected_paragraphs ? data.selected_paragraphs.join("\n\n") : (data.selected_output ? JSON.stringify(data.selected_output, null, 2) : "No output applied. Review the input and reference manually.");
    const span = ([start, end]) => start === end ? "none (after position " + start + ")" : (start + 1) + (end === start + 1 ? "" : "–" + end);
    workflowElement("workflow-changes").textContent = data.review_changes ? (data.review_changes.map((change) => change.kind.toUpperCase() + " · reference " + span(change.reference_span) + " · converted " + span(change.observed_span)).join("\n") || "No normalized paragraph difference.") : "Graph request: inspect the candidate and evidence below.";
    workflowElement("workflow-receipt").textContent = data.receipt.receipt_sha256;
    workflowElement("download-result").disabled = false;
  } catch (error) {
    if (version !== workflowVersion) return;
    workflowElement("workflow-status").textContent = "INPUT NOT ACCEPTED";
    workflowElement("workflow-status").className = "decision abstain";
    workflowElement("workflow-reason").textContent = error.message;
  } finally {
    if (version === workflowVersion) {
      workflowElement("run-workflow").disabled = false;
      workflowElement("run-candidate").disabled = false;
    }
  }
}

async function runParagraphCheck() {
  return submitWorkflow("/api/workflow", JSON.stringify({record_id: "local-paragraph-conversion",
    reference_paragraphs: paragraphs(workflowElement("reference-input").value),
    observed_paragraphs: paragraphs(workflowElement("observed-input").value)}));
}

function downloadWorkflowResult() {
  if (!workflowResult) return;
  const blob = new Blob([JSON.stringify(workflowResult, null, 2) + "\n"], {type: "application/json"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "biosure-result.json";
  link.click();
  URL.revokeObjectURL(url);
}

workflowElement("load-example").addEventListener("click", loadWorkflowExample);
workflowElement("run-workflow").addEventListener("click", runParagraphCheck);
workflowElement("clear-workflow").addEventListener("click", clearWorkflow);
workflowElement("download-result").addEventListener("click", downloadWorkflowResult);
workflowElement("run-candidate").addEventListener("click", () => submitWorkflow("/api/decide", workflowElement("candidate-input").value));
for (const id of ["reference-input", "observed-input", "candidate-input"]) workflowElement(id).addEventListener("input", resetWorkflowResult);
workflowElement("reference-ack").addEventListener("change", resetWorkflowResult);
