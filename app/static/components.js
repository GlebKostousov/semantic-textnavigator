import {
  badge, button, element, factValue, hasDeliveryProposal, kindLabel,
  longDate, stateLabel,
} from "./format.js";

export function renderTable({ contracts, selectedNumber, selectedField, onSelect }) {
  const body = document.querySelector("#contracts-body");
  body.replaceChildren(...contracts.map((contract) => {
    const row = element("tr");
    row.dataset.contractNumber = contract.number;
    const identity = element("td", "contract-identity");
    identity.append(button("contract-link", contract.number, () => onSelect(contract.number, "delivery_date", "table")));
    identity.append(element("span", "supplier-name", contract.supplier || "Поставщик не определён"));
    row.append(identity);
    for (const field of ["amount", "delivery_date", "penalty"]) {
      const fact = contract[field];
      const cell = element("td", "fact-cell");
      const control = button("fact-button", null, () => onSelect(contract.number, field, "table"));
      control.dataset.contractNumber = contract.number;
      control.dataset.field = field;
      const title = field === "amount" ? "сумму" : field === "delivery_date" ? "срок поставки" : "неустойку";
      control.setAttribute("aria-label", `Проверить ${title} договора ${contract.number}`);
      control.append(element("span", `fact-value fact-${fact.state}`, factValue(fact, field, { currency: false })));
      const note = fact.amended ? "Изменено допсоглашением" : "Проверить основание";
      control.append(element("span", "fact-note", note));
      cell.append(control);
      row.append(cell);
    }
    const changes = element("td", "changes-cell");
    if (contract.proposals.length) {
      changes.append(badge("Не согласовано", "warning"));
      changes.append(element("span", "change-note", hasDeliveryProposal(contract) ? "Есть предложение по сроку" : "Есть предложение по сумме"));
    } else {
      changes.append(element("span", "muted", "Нет предложений"));
    }
    if (contract.issues.length || contract.amount.state === "review" || contract.delivery_date.state === "review" || contract.penalty.state === "review") {
      changes.append(element("span", "review-note", "Требует проверки"));
    }
    row.append(changes);
    return row;
  }));
  markSelection(selectedNumber, selectedField);
}

export function markSelection(number, field) {
  for (const row of document.querySelectorAll("#contracts-body tr")) {
    row.classList.toggle("is-selected", row.dataset.contractNumber === number);
  }
  for (const control of document.querySelectorAll(".fact-button")) {
    const selected = control.dataset.contractNumber === number && control.dataset.field === field;
    control.classList.toggle("is-active", selected);
    control.setAttribute("aria-pressed", String(selected));
  }
}

function citationFigure(citation, onCitation, { compact = false } = {}) {
  const figure = element("figure", compact ? "citation citation-compact" : "citation");
  const caption = element("figcaption", "citation-caption");
  const filename = button("source-link", citation.filename, () => onCitation(citation));
  filename.title = `Открыть ${citation.filename}, абзац ${citation.paragraph_id}`;
  caption.append(filename, element("span", "paragraph-label", `абз. ${citation.paragraph_id}`));
  const quote = element("blockquote", "citation-quote", citation.quote);
  const jump = button("text-button citation-jump", "Показать в тексте →", () => onCitation(citation));
  figure.append(caption, quote, jump);
  return figure;
}

function renderFact(contract, field, onCitation) {
  const fact = contract[field];
  const section = element("section", "fact-detail");
  const line = element("div", "fact-detail-heading");
  const labels = {
    amount: "Действующая сумма",
    delivery_date: "Действующий срок поставки",
    penalty: "Действующая ставка неустойки",
  };
  const label = labels[field] || "Условие договора";
  line.append(element("h4", "", label));
  if (fact.state === "review") line.append(badge("Нужна проверка", "warning"));
  else if (fact.state === "missing") line.append(badge("Нет данных"));
  else if (fact.amended) line.append(badge("Новая редакция", "positive"));
  section.append(line, element("p", "detail-value", factValue(fact, field)));
  if (fact.reason) section.append(element("p", "fact-reason", fact.reason));
  if (!fact.citations.length) {
    section.append(element("p", "muted", "Основание в загруженных документах не найдено. Значение не определено."));
  }
  for (const citation of fact.citations) section.append(citationFigure(citation, onCitation));
  return section;
}

function renderProposals(contract, documents, onCitation, onDocument) {
  const section = element("section", "proposals-section");
  const heading = element("div", "section-heading");
  heading.append(element("h4", "", "Несогласованные изменения"), badge(String(contract.proposals.length), "warning"));
  section.append(heading, element("p", "section-description", "Эти предложения не меняют действующие условия."));
  for (const proposal of contract.proposals) {
    const item = element("article", "proposal");
    const source = documents.find((doc) => doc.id === proposal.document_id);
    item.append(element("p", "proposal-kind", kindLabel(proposal.kind)));
    item.append(button("source-link proposal-filename", source?.name || "Открыть документ", () => onDocument(proposal.document_id)));
    item.append(element("p", "proposal-reason", proposal.reason));
    for (const field of ["amount", "delivery_date", "penalty"]) {
      const fact = proposal[field];
      if (!fact || (fact.value === null && fact.state !== "review" && !fact.citations.length)) continue;
      const labels = {
        amount: "Предлагаемая сумма",
        delivery_date: "Предлагаемый срок",
        penalty: "Предлагаемая неустойка",
      };
      const label = labels[field] || "Предлагаемое условие";
      const value = element("p", "proposal-value");
      value.append(element("span", "", label), element("strong", "", factValue(fact, field)));
      item.append(value);
      for (const citation of fact.citations) item.append(citationFigure(citation, onCitation, { compact: true }));
    }
    if (proposal.status_citations.length) {
      const details = element("details", "status-evidence");
      details.append(element("summary", "", "Почему изменение не согласовано"));
      for (const citation of proposal.status_citations) details.append(citationFigure(citation, onCitation, { compact: true }));
      item.append(details);
    }
    section.append(item);
  }
  return section;
}

function renderRelated(contract, documents, onDocument, onCitation) {
  const section = element("section", "related-section");
  section.append(element("h4", "", "Документы договора"));
  for (const related of contract.related_documents) {
    const source = documents.find((doc) => doc.id === related.document_id);
    const item = element("article", "related-document");
    const head = element("div", "related-heading");
    head.append(button("source-link", source?.name || "Открыть документ", () => onDocument(related.document_id)));
    const tone = related.state === "applied" ? "positive" : ["proposal", "review"].includes(related.state) ? "warning" : "neutral";
    head.append(badge(stateLabel(related.state), tone));
    item.append(head, element("p", "related-explanation", related.explanation));
    if (related.citations.length) {
      const details = element("details", "status-evidence");
      details.append(element("summary", "", "Основание статуса"));
      for (const citation of related.citations) details.append(citationFigure(citation, onCitation, { compact: true }));
      item.append(details);
    }
    section.append(item);
  }
  return section;
}

export function renderDetails({ contract, documents, asOf, field, onSelect, onCitation, onDocument }) {
  const target = document.querySelector("#contract-details");
  target.replaceChildren();
  if (!contract) return;
  const header = element("header", "detail-header");
  const title = element("div");
  title.append(element("p", "eyebrow", "Выбранный договор"), element("h3", "", contract.number));
  header.append(title, element("p", "detail-date", `На ${longDate(asOf)}`));
  target.append(header);
  const fields = element("div", "field-switch", null);
  fields.setAttribute("role", "group");
  fields.setAttribute("aria-label", "Выбрать проверяемое условие");
  for (const [key, label] of [["amount", "Сумма договора"], ["delivery_date", "Срок поставки"], ["penalty", "Неустойка"]]) {
    const control = button(`field-tab${key === field ? " is-active" : ""}`, label, () => onSelect(contract.number, key, "details"));
    control.dataset.detailField = key;
    control.setAttribute("aria-pressed", String(key === field));
    fields.append(control);
  }
  target.append(fields);
  if (contract.issues.length) {
    const notice = element("div", "notice notice-warning");
    notice.append(element("strong", "", "Нужна проверка документов"));
    const list = element("ul");
    for (const issue of contract.issues) list.append(element("li", "", issue));
    notice.append(list);
    target.append(notice);
  }
  target.append(renderFact(contract, field, onCitation));
  if (contract.proposals.length) target.append(renderProposals(contract, documents, onCitation, onDocument));
  target.append(renderRelated(contract, documents, onDocument, onCitation));
}

export function renderNotices({ data, onDocument }) {
  const target = document.querySelector("#analysis-notices");
  target.replaceChildren();
  if (data.warnings.length) {
    const notice = element("div", "notice notice-warning");
    notice.append(element("strong", "", "Обратите внимание"));
    const list = element("ul");
    for (const warning of data.warnings) list.append(element("li", "", warning));
    notice.append(list);
    target.append(notice);
  }
  if (data.unlinked_document_ids.length) {
    const notice = element("div", "notice notice-warning unlinked-notice");
    notice.append(element("strong", "", "Не удалось связать с договором"));
    const list = element("ul");
    for (const id of data.unlinked_document_ids) {
      const source = data.documents.find((doc) => doc.id === id);
      const item = element("li");
      item.append(button("source-link", source?.name || "Открыть документ", () => onDocument(id)));
      list.append(item);
    }
    notice.append(list, element("p", "", "Проверьте номер договора и состав загруженного комплекта."));
    target.append(notice);
  }
}
