const workflowElement = (id) => document.getElementById(id);
let workflowVersion = 0;
let publicInputVersion = 0;
let workflowResult = null;
let pdfImported = false;

function invalidatePublicExample(message) {
  ++publicInputVersion;
  workflowElement("load-public-extraction").disabled = false;
  workflowElement("public-source-note").textContent = message;
  workflowElement("public-article-link").removeAttribute("href");
  workflowElement("public-article-link").textContent = "";
  workflowElement("public-source-link-row").hidden = true;
}

function resetWorkflowResult() {
  ++workflowVersion;
  workflowResult = null;
  workflowElement("download-result").disabled = true;
  workflowElement("run-workflow").disabled = false;
  workflowElement("run-ml").disabled = false;
  workflowElement("run-learned-proposal").disabled = false;
  workflowElement("run-candidate").disabled = false;
  workflowElement("run-proposal").disabled = false;
  workflowElement("workflow-output").textContent = "";
  workflowElement("workflow-changes").textContent = "";
  workflowElement("workflow-change-details").replaceChildren();
  workflowElement("ml-rankings").textContent = "";
  workflowElement("learned-proposal-status").textContent = "No learned proposal generated.";
  workflowElement("learned-proposal-text").textContent = "";
  workflowElement("learned-proposal-receipt").textContent = "";
  workflowElement("workflow-receipt").textContent = "";
  workflowElement("workflow-status").textContent = "READY";
  workflowElement("workflow-status").className = "decision";
  workflowElement("workflow-reason").textContent = "Your reference is a declared assumption. No result applied yet.";
}

function clearWorkflow() {
  resetWorkflowResult();
  invalidatePublicExample("Public example cleared. Manually check original sources before acknowledging a reference.");
  workflowElement("pdf-review-hints").replaceChildren();
  for (const id of ["reference-input", "observed-input", "candidate-input", "proposal-input"]) workflowElement(id).value = "";
  workflowElement("reference-ack").checked = false;
  workflowElement("pdf-ack").checked = false;
  pdfImported = false;
}

async function loadPublicExtraction() {
  resetWorkflowResult();
  workflowElement("reference-ack").checked = false;
  workflowElement("pdf-ack").checked = false;
  const version = ++publicInputVersion;
  const button = workflowElement("load-public-extraction");
  const sourceId = workflowElement("public-source-select").value;
  const note = workflowElement("public-source-note");
  button.disabled = true;
  workflowElement("public-article-link").removeAttribute("href");
  workflowElement("public-article-link").textContent = "";
  workflowElement("public-source-link-row").hidden = true;
  note.textContent = `Loading ${sourceId} public excerpt…`;
  try {
    const response = await fetch(`/api/examples/public-extraction?source=${encodeURIComponent(sourceId)}`);
    const data = await response.json();
    if (version !== publicInputVersion) return;
    if (!response.ok) throw new Error(data.error || "Public excerpt unavailable");
    resetWorkflowResult();
    workflowElement("reference-input").value = data.reference_paragraphs.join("\n\n");
    workflowElement("observed-input").value = data.observed_paragraphs.join("\n\n");
    workflowElement("reference-ack").checked = false;
    workflowElement("pdf-ack").checked = false;
    workflowElement("pdf-review-hints").replaceChildren();
    workflowElement("pdf-status").textContent = "Pre-extracted public PDF text layer loaded; no PDF was imported in this session.";
    pdfImported = false;
    note.textContent = `${data.source_id} · CC BY 4.0 · ${data.note}`;
    if (/^PMC[0-9]+$/.test(data.source_id)) {
      workflowElement("public-article-link").href = `https://pmc.ncbi.nlm.nih.gov/articles/${data.source_id}/`;
      workflowElement("public-article-link").textContent = `Open ${data.source_id} article (PDF available there)`;
      workflowElement("public-source-link-row").hidden = false;
    }
  } catch (error) {
    if (version === publicInputVersion) note.textContent = `Could not load ${sourceId}: ${error.message}`;
  } finally {
    if (version === publicInputVersion) button.disabled = false;
  }
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

async function importPdf() {
  const file = workflowElement("pdf-file").files[0];
  const status = workflowElement("pdf-status");
  if (!file) { status.textContent = "Choose a PDF first."; return; }
  if (file.size > 16 * 1024 * 1024 || !file.size) {
    status.textContent = "PDF must be non-empty and at most 16 MiB."; return;
  }
  const target = workflowElement("pdf-target").value;
  if (!['reference', 'observed'].includes(target)) {
    status.textContent = "Choose the destination field."; return;
  }
  invalidatePublicExample("PDF import started. Manually check the imported pages before acknowledging a reference.");
  resetWorkflowResult();
  const version = workflowVersion;
  const button = workflowElement("import-pdf");
  const hintList = workflowElement("pdf-review-hints");
  hintList.replaceChildren();
  button.disabled = true;
  status.textContent = "Extracting local PDF text layer…";
  try {
    const response = await fetch('/api/pdf-extract', {
      method: 'POST', headers: {'Content-Type': 'application/pdf'}, body: file
    });
    const data = await response.json();
    if (version !== workflowVersion) return;
    if (!response.ok) throw new Error(data.error || 'PDF extraction failed');
    workflowElement(target + '-input').value = data.paragraphs.map(item => item.text).join('\n\n');
    workflowElement('reference-ack').checked = false;
    workflowElement('pdf-ack').checked = false;
    pdfImported = true;
    resetWorkflowResult();
    const warning = data.warnings.includes('IMAGE_TEXT_NOT_EXTRACTED')
      ? ` ${data.image_count} image(s): text inside figures was not extracted.` : '';
    const noText = data.warnings.includes('NO_TEXT_LAYER')
      ? ' A page had no text layer; OCR/manual transcription is required.' : '';
    const spacing = data.warnings.includes('TEXT_SPACING_ARTIFACTS')
      ? ' Broken letter spacing was detected; manual retranscription may be needed.' : '';
    const crosscheck = data.warnings.includes('CROSS_EXTRACTOR_SPACING_REQUIRES_REVIEW')
      ? ' A second PDF parser found possible spacing corrections; verify each against the visible page before editing.' : '';
    const crosscheckMissing = data.warnings.includes('SECOND_EXTRACTOR_UNAVAILABLE')
      ? ' The second-parser crosscheck was unavailable; review spacing manually.' : '';
    const hyphen = data.warnings.includes('LINE_END_HYPHEN_REQUIRES_REVIEW')
      ? ' Line-end hyphens were preserved; review each hyphen against the original page before checking.' : '';
    for (const hint of (data.review_hints || [])) {
      const item = document.createElement('li');
      const label = hint.kind === 'CROSS_EXTRACTOR_SPACING_SUGGESTION' ? 'Possible word spacing (not applied)'
        : hint.kind === 'TEXT_SPACING_ARTIFACTS' ? 'Check broken letter spacing'
        : hint.kind === 'LINE_END_HYPHEN_REQUIRES_REVIEW' ? 'Check line-break hyphen'
        : hint.kind === 'PROBABLE_CAPTION_OR_PAGE_FURNITURE' ? 'Possible caption or page header inside text (not removed)'
        : 'Review text layer';
      item.textContent = `Page ${hint.page} · ${label}: ${hint.excerpt}${hint.suggestion ? ' → ' + hint.suggestion : ''}`;
      hintList.append(item);
    }
    const furniture = data.warnings.includes('CAPTION_OR_PAGE_FURNITURE_REQUIRES_REVIEW')
      ? ' Figure/table captions or page headers may be spliced into body text; remove them manually where they interrupt a paragraph.' : '';
    const truncated = data.warnings.includes('REVIEW_HINTS_TRUNCATED')
      ? ' The location list is capped; inspect every page, not just the listed examples.' : '';
    status.textContent = `Extracted ${data.paragraphs.length} unverified page-text chunk(s) from ${data.pages} page(s) into ${target}. These are NOT paragraph boundaries. Compare reading order against each page, then split/correct text manually before checking.${warning}${noText}${spacing}${crosscheck}${crosscheckMissing}${hyphen}${furniture}${truncated}`;
  } catch (error) {
    if (version === workflowVersion) status.textContent = error.message;
  } finally {
    button.disabled = false;
  }
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
  if (pdfImported && !workflowElement('pdf-ack').checked) {
    workflowElement('workflow-reason').textContent = 'Review and correct PDF page chunks against the original, then acknowledge PDF review.';
    return;
  }
  workflowElement("run-workflow").disabled = true;
  workflowElement("run-ml").disabled = true;
  workflowElement("run-learned-proposal").disabled = true;
  workflowElement("run-candidate").disabled = true;
  workflowElement("run-proposal").disabled = true;
  workflowElement("workflow-status").textContent = "CHECKING…";
  try {
    const response = await fetch(endpoint, {method: "POST", headers: {"Content-Type": "application/json"}, body});
    const data = await response.json();
    if (version !== workflowVersion) return;
    if (!response.ok) throw new Error(data.error || "Input check failed");
    workflowResult = data;
    const learnedProposal = data.mode === 'learned_upstream_proposal';
    const checked = learnedProposal ? data.proposal_check : data;
    const automatic = checked?.decision?.action === "AUTO_REPAIR";
    workflowElement("workflow-status").textContent = learnedProposal && !checked
      ? "NO LEARNED PROPOSAL" : automatic ? "REFERENCE MATCH · SOURCE UNVERIFIED" : "NO AUTOMATIC CHANGE";
    workflowElement("workflow-status").className = "decision " + (automatic ? "provisional" : "abstain");
    const reason = learnedProposal && !checked ? `${data.proposal_reason} · separate gate not run`
      : (checked?.adapter_status || data.adapter_status || "DECLARED_CANDIDATE") + " · "
        + (checked.decision.reason_codes.join(" · ") || "One uniquely supported bounded edit.");
    workflowElement("workflow-reason").textContent = reason + " Reference authenticity and biological meaning are not verified.";
    workflowElement("workflow-output").textContent = checked?.selected_paragraphs
      ? checked.selected_paragraphs.join("\n\n")
      : (!learnedProposal && data.selected_output ? JSON.stringify(data.selected_output, null, 2)
        : "No output applied. Review the input and reference manually.");
    const span = ([start, end]) => start === end ? "none (after position " + start + ")" : (start + 1) + (end === start + 1 ? "" : "–" + end);
    workflowElement("workflow-changes").textContent = data.review_changes ? (data.review_changes.map((change) => change.kind.toUpperCase() + " · reference " + span(change.reference_span) + " · converted " + span(change.observed_span)).join("\n") || "No normalized paragraph difference.") : "Graph request: inspect the candidate and evidence below.";
    if (data.review_changes && data.reference_paragraphs && data.observed_paragraphs) {
      const detailsPanel = workflowElement("workflow-change-details");
      for (const change of data.review_changes) {
        const detail = document.createElement("details");
        detail.className = "change-detail";
        const summary = document.createElement("summary");
        summary.textContent = change.kind.toUpperCase() + " · reference " + span(change.reference_span) + " · converted " + span(change.observed_span);
        detail.append(summary);
        for (const [label, paragraphs, range] of [
          ["Reference text", data.reference_paragraphs, change.reference_span],
          ["Converted text", data.observed_paragraphs, change.observed_span]]) {
          const heading = document.createElement("div");
          heading.className = "change-detail-label";
          heading.textContent = label;
          const text = document.createElement("pre");
          text.textContent = paragraphs.slice(range[0], range[1]).join("\n\n") || "(no paragraph)";
          detail.append(heading, text);
        }
        detailsPanel.append(detail);
      }
    }
    workflowElement("ml-rankings").textContent = data.correspondences ? data.correspondences.map(item =>
      `Converted ${item.observed_index + 1} → reference ${item.reference_index + 1} · score ${item.probability.toFixed(3)} · ${item.flags.join(', ') || 'no lexical alert'}${item.ambiguous ? ' · AMBIGUOUS' : ''}`).join('\n') : 'Run learned review to inspect candidate matches.';
    if (data.mode === 'learned_upstream_proposal') {
      const gateAction = data.proposal_check ? data.proposal_check.decision.action : 'NOT_RUN';
      workflowElement('learned-proposal-status').textContent = data.proposed_paragraphs
        ? `SOURCE UNVERIFIED · model alignment ${data.proposal_status} · separate gate ${gateAction}. Review against the original source.`
        : `No learned proposal · ${data.proposal_reason}. Separate gate not run.`;
      workflowElement('learned-proposal-text').textContent = data.proposed_paragraphs
        ? data.proposed_paragraphs.join('\n\n') : '';
      workflowElement('learned-proposal-receipt').textContent = data.upstream_receipt.receipt_sha256;
    }
    workflowElement("workflow-receipt").textContent = checked?.receipt?.receipt_sha256 || "";
    workflowElement("download-result").disabled = false;
  } catch (error) {
    if (version !== workflowVersion) return;
    workflowElement("workflow-status").textContent = "INPUT NOT ACCEPTED";
    workflowElement("workflow-status").className = "decision abstain";
    workflowElement("workflow-reason").textContent = error.message;
  } finally {
    if (version === workflowVersion) {
      workflowElement("run-workflow").disabled = false;
      workflowElement("run-ml").disabled = false;
      workflowElement("run-learned-proposal").disabled = false;
      workflowElement("run-candidate").disabled = false;
      workflowElement("run-proposal").disabled = false;
    }
  }
}

async function runParagraphCheck() {
  return submitWorkflow("/api/workflow", JSON.stringify({record_id: "local-paragraph-conversion",
    reference_paragraphs: paragraphs(workflowElement("reference-input").value),
    observed_paragraphs: paragraphs(workflowElement("observed-input").value)}));
}

async function runLearnedReview() {
  return submitWorkflow('/api/ml-review', JSON.stringify({record_id:'local-learned-review',
    reference_paragraphs:paragraphs(workflowElement('reference-input').value),
    observed_paragraphs:paragraphs(workflowElement('observed-input').value)}));
}

async function runLearnedProposal() {
  return submitWorkflow('/api/learned-proposal', JSON.stringify({record_id:'local-learned-proposal',
    reference_paragraphs:paragraphs(workflowElement('reference-input').value),
    observed_paragraphs:paragraphs(workflowElement('observed-input').value)}));
}

async function runProposalCheck() {
  return submitWorkflow("/api/proposal", JSON.stringify({record_id: "local-upstream-proposal",
    reference_paragraphs: paragraphs(workflowElement("reference-input").value),
    observed_paragraphs: paragraphs(workflowElement("observed-input").value),
    proposed_paragraphs: paragraphs(workflowElement("proposal-input").value)}));
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
workflowElement("load-public-extraction").addEventListener("click", loadPublicExtraction);
workflowElement("import-pdf").addEventListener("click", importPdf);
workflowElement("run-workflow").addEventListener("click", runParagraphCheck);
workflowElement("run-ml").addEventListener("click", runLearnedReview);
workflowElement("run-learned-proposal").addEventListener("click", runLearnedProposal);
workflowElement("run-proposal").addEventListener("click", runProposalCheck);
workflowElement("clear-workflow").addEventListener("click", clearWorkflow);
workflowElement("download-result").addEventListener("click", downloadWorkflowResult);
workflowElement("run-candidate").addEventListener("click", () => submitWorkflow("/api/decide", workflowElement("candidate-input").value));
for (const id of ["reference-input", "observed-input", "candidate-input", "proposal-input"]) workflowElement(id).addEventListener("input", () => {
  resetWorkflowResult();
  invalidatePublicExample("Inputs changed. Manually check the original source before acknowledging a reference.");
});
workflowElement("reference-ack").addEventListener("change", resetWorkflowResult);
workflowElement("pdf-ack").addEventListener("change", resetWorkflowResult);
