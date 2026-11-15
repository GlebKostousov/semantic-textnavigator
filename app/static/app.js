import { hasDeliveryProposal, longDate } from "./format.js";
import { markSelection, renderDetails, renderNotices, renderTable } from "./components.js";
import { renderSource } from "./source.js";

const elements = {
  form: document.querySelector("#upload-form"),
  files: document.querySelector("#file-input"),
  fileSummary: document.querySelector("#file-summary"),
  asOf: document.querySelector("#as-of"),
  analyze: document.querySelector("#analyze-button"),
  demo: document.querySelector("#demo-button"),
  clear: document.querySelector("#clear-button"),
  pending: document.querySelector("#pending-note"),
  loading: document.querySelector("#loading-status"),
  error: document.querySelector("#error-message"),
  results: document.querySelector("#results"),
  empty: document.querySelector("#empty-state"),
  summary: document.querySelector("#results-summary"),
  search: document.querySelector("#contract-search"),
  before: document.querySelector("#delivery-before"),
  proposals: document.querySelector("#proposals-only"),
  filterNote: document.querySelector("#filter-note"),
  noMatches: document.querySelector("#no-matches"),
  sourceSelect: document.querySelector("#source-select"),
};

const state = {
  files: [],
  source: null,
  data: null,
  selectedNumber: null,
  selectedField: "delivery_date",
  documentId: null,
  paragraphId: null,
  busy: false,
};

function setBusy(busy) {
  state.busy = busy;
  elements.analyze.disabled = busy || !state.source;
  elements.demo.disabled = busy;
  elements.clear.disabled = busy;
  elements.files.disabled = busy;
  elements.asOf.disabled = busy;
  elements.loading.hidden = !busy;
  elements.form.setAttribute("aria-busy", String(busy));
  elements.analyze.textContent = busy ? "Проверяем…" : "Проверить документы";
}

function setError(message) {
  elements.error.textContent = message;
  elements.error.hidden = !message;
}

function updateFileSummary() {
  if (state.source === "demo") {
    elements.fileSummary.textContent = "Учебный комплект документов";
    elements.fileSummary.removeAttribute("title");
  } else if (state.files.length) {
    elements.fileSummary.textContent = `Выбрано файлов: ${state.files.length}`;
    elements.fileSummary.title = state.files.map((file) => file.name).join("\n");
  } else {
    elements.fileSummary.textContent = "Файлы не выбраны";
    elements.fileSummary.removeAttribute("title");
  }
  elements.clear.hidden = !state.source && !state.data;
  elements.analyze.disabled = state.busy || !state.source;
}

function markPending() {
  if (!state.data) return;
  elements.pending.hidden = false;
  elements.pending.textContent = `Параметры изменены. Ниже остаётся предыдущий результат на ${longDate(state.data.as_of)}. Нажмите «Проверить документы».`;
}

function currentContract() {
  return state.data?.contracts.find((contract) => contract.number === state.selectedNumber);
}

function showReader(scrollToSource = false) {
  if (!state.data) return;
  renderSource({
    documents: state.data.documents,
    documentId: state.documentId,
    paragraphId: state.paragraphId,
    scrollToSource,
  });
}

function openCitation(citation, scrollToSource = true) {
  state.documentId = citation.document_id;
  state.paragraphId = citation.paragraph_id;
  showReader(scrollToSource);
}

function openDocument(documentId) {
  state.documentId = documentId;
  state.paragraphId = null;
  showReader(true);
}

function showDetails() {
  renderDetails({
    contract: currentContract(),
    documents: state.data.documents,
    asOf: state.data.as_of,
    field: state.selectedField,
    onSelect: selectFact,
    onCitation: openCitation,
    onDocument: openDocument,
  });
}

function selectFact(number, field, origin = "initial") {
  state.selectedNumber = number;
  state.selectedField = field;
  markSelection(number, field);
  showDetails();
  const citation = currentContract()?.[field].citations[0];
  if (citation) openCitation(citation, origin !== "initial");
  else {
    state.paragraphId = null;
    state.documentId = currentContract()?.related_documents[0]?.document_id || null;
    showReader(false);
  }
  if (origin === "details") {
    document.querySelector(`[data-detail-field="${field}"]`)?.focus({ preventScroll: true });
  }
}

function filteredContracts() {
  const query = elements.search.value.trim().toLocaleLowerCase("ru-RU");
  const before = elements.before.value;
  return state.data.contracts.filter((contract) => {
    const identity = `${contract.number} ${contract.supplier || ""}`.toLocaleLowerCase("ru-RU");
    if (query && !identity.includes(query)) return false;
    if (before && (contract.delivery_date.state !== "confirmed" || !contract.delivery_date.value || contract.delivery_date.value >= before)) return false;
    if (elements.proposals.checked && !hasDeliveryProposal(contract)) return false;
    return true;
  });
}

function updateFilters() {
  if (!state.data) return;
  const contracts = filteredContracts();
  if (!contracts.some((contract) => contract.number === state.selectedNumber)) {
    state.selectedNumber = contracts[0]?.number || null;
  }
  renderTable({
    contracts,
    selectedNumber: state.selectedNumber,
    selectedField: state.selectedField,
    onSelect: selectFact,
  });
  elements.noMatches.hidden = contracts.length > 0;
  if (!state.data.contracts.length) {
    elements.noMatches.textContent = "В комплекте не найдено договоров, которые удалось распознать. Откройте исходные файлы и проверьте формат.";
  } else {
    elements.noMatches.textContent = "По этим фильтрам договоров нет. Измените условия отбора.";
  }
  const uncertain = state.data.contracts.filter((contract) => contract.delivery_date.state !== "confirmed" || !contract.delivery_date.value).length;
  elements.filterNote.hidden = !elements.before.value;
  elements.filterNote.textContent = `Показаны договоры со сроком строго раньше ${formatFilterDate(elements.before.value)}.${uncertain ? ` Не включены в отбор: ${uncertain}. Их срок не определён или требует проверки.` : ""}`;
  if (state.selectedNumber) selectFact(state.selectedNumber, state.selectedField, "initial");
  else {
    showDetails();
    state.documentId = null;
    state.paragraphId = null;
    showReader(false);
  }
}

function formatFilterDate(value) {
  return value ? longDate(value) : "выбранной даты";
}

function acceptResult(data) {
  if (!Array.isArray(data.contracts) || !Array.isArray(data.documents)) {
    throw new Error("Не удалось прочитать результат проверки. Перезапустите приложение и повторите попытку.");
  }
  state.data = data;
  state.selectedNumber = data.contracts[0]?.number || null;
  state.selectedField = "delivery_date";
  elements.search.value = "";
  elements.before.value = "";
  elements.proposals.checked = false;
  clearScenarioPills();
  elements.results.hidden = false;
  elements.empty.hidden = true;
  elements.pending.hidden = true;
  elements.summary.textContent = `Договоров: ${data.contracts.length} · Документов: ${data.documents.length} · На ${longDate(data.as_of)}`;
  renderNotices({ data, onDocument: openDocument });
  updateFilters();
}

async function readResponse(response) {
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error("Сервер не вернул результат проверки. Убедитесь, что приложение запущено, и повторите попытку.");
  }
  if (!response.ok) {
    const message = body.error?.message || (typeof body.detail === "string" ? body.detail : null);
    throw new Error(message || `Не удалось проверить документы. Код ответа: ${response.status}.`);
  }
  return body;
}

async function analyze(source) {
  if (state.busy || !source) return;
  if (!elements.asOf.reportValidity()) return;
  setError("");
  setBusy(true);
  try {
    let response;
    if (source === "demo") {
      response = await fetch(`/api/demo?as_of=${encodeURIComponent(elements.asOf.value)}`);
    } else {
      const form = new FormData();
      form.append("as_of", elements.asOf.value);
      for (const file of state.files) form.append("files", file, file.name);
      response = await fetch("/api/analyze", { method: "POST", body: form });
    }
    const data = await readResponse(response);
    state.source = source;
    if (source === "demo") {
      state.files = [];
      elements.files.value = "";
    }
    acceptResult(data);
    updateFileSummary();
  } catch (error) {
    const message = error instanceof TypeError
      ? "Не удалось связаться с приложением. Проверьте, что локальный сервер запущен."
      : error.message || "Не удалось проверить документы.";
    setError(message);
    if (state.data) {
      elements.pending.hidden = false;
      elements.pending.textContent = `Новая проверка не выполнена. Ниже остаётся предыдущий результат на ${longDate(state.data.as_of)}.`;
    }
  } finally {
    setBusy(false);
  }
}

function clearScenarioPills() {
  for (const pill of document.querySelectorAll(".scenario-pill")) {
    pill.classList.remove("is-active");
  }
  const resetBtn = document.querySelector("#scenario-reset");
  if (resetBtn) resetBtn.hidden = true;
}

function applyScenario(scenario) {
  if (!state.data) return;
  const resetBtn = document.querySelector("#scenario-reset");
  for (const pill of document.querySelectorAll(".scenario-pill")) {
    pill.classList.remove("is-active");
  }

  if (scenario === "reset") {
    elements.search.value = "";
    elements.before.value = "";
    elements.proposals.checked = false;
    if (resetBtn) resetBtn.hidden = true;
    updateFilters();
    return;
  }

  const activePill = document.querySelector(`[data-scenario="${scenario}"]`);
  if (activePill) activePill.classList.add("is-active");
  if (resetBtn) resetBtn.hidden = false;

  if (scenario === "q1") {
    elements.search.value = "STN-101";
    elements.before.value = "";
    elements.proposals.checked = false;
    updateFilters();
    selectFact("STN-101", "delivery_date", "details");
  } else if (scenario === "q2") {
    elements.search.value = "STN-102";
    elements.before.value = "";
    elements.proposals.checked = false;
    updateFilters();
    selectFact("STN-102", "amount", "details");
  } else if (scenario === "q3") {
    elements.search.value = "STN-103";
    elements.before.value = "";
    elements.proposals.checked = false;
    updateFilters();
    selectFact("STN-103", "amount", "details");
  } else if (scenario === "q4") {
    elements.search.value = "";
    elements.before.value = "2026-04-01";
    elements.proposals.checked = false;
    updateFilters();
    selectFact("STN-102", "delivery_date", "details");
  }
}

function clear() {
  state.files = [];
  state.source = null;
  state.data = null;
  state.selectedNumber = null;
  state.documentId = null;
  state.paragraphId = null;
  elements.files.value = "";
  elements.search.value = "";
  elements.before.value = "";
  elements.proposals.checked = false;
  elements.results.hidden = true;
  elements.empty.hidden = false;
  elements.pending.hidden = true;
  clearScenarioPills();
  setError("");
  updateFileSummary();
  elements.demo.focus();
}

elements.files.addEventListener("change", () => {
  if (!elements.files.files.length) return;
  state.files = Array.from(elements.files.files);
  state.source = "upload";
  updateFileSummary();
  setError("");
  markPending();
});
elements.form.addEventListener("submit", (event) => { event.preventDefault(); analyze(state.source); });
elements.demo.addEventListener("click", () => analyze("demo"));
elements.clear.addEventListener("click", clear);
elements.asOf.addEventListener("change", markPending);
elements.search.addEventListener("input", () => { clearScenarioPills(); updateFilters(); });
elements.before.addEventListener("change", () => { clearScenarioPills(); updateFilters(); });
elements.proposals.addEventListener("change", () => { clearScenarioPills(); updateFilters(); });
for (const pill of document.querySelectorAll(".scenario-pill")) {
  pill.addEventListener("click", () => applyScenario(pill.dataset.scenario));
}
document.querySelector("#scenario-reset")?.addEventListener("click", () => applyScenario("reset"));
elements.sourceSelect.addEventListener("change", () => openDocument(elements.sourceSelect.value));
document.querySelector("#back-to-contract").addEventListener("click", () => {
  document.querySelector("#contract-details").scrollIntoView({ block: "start", behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
});
