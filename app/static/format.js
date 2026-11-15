const kindLabels = {
  contract: "Договор",
  amendment: "Допсоглашение",
  draft: "Проект",
  letter: "Письмо поставщика",
  unknown: "Тип не определён",
};

const stateLabels = {
  base: "Исходный договор",
  applied: "Учтён",
  proposal: "Не согласовано",
  future: "Позднее даты проверки",
  review: "Нужна проверка",
  ignored: "Не применён",
};

/** Создаёт DOM-элемент, не интерпретируя текст документов как HTML. */
export function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}

export function button(className, text, onClick) {
  const node = element("button", className, text);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

export function money(value, { currency = true } = {}) {
  if (value === null || value === undefined) return "Нет данных";
  const parts = String(value).match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!parts) return String(value);
  const integer = parts[2].replace(/\B(?=(\d{3})+(?!\d))/g, "\u202f");
  const decimals = parts[3] && !/^0+$/.test(parts[3]) ? `,${parts[3]}` : "";
  return `${parts[1]}${integer}${decimals}${currency ? " ₽" : ""}`;
}

export function shortDate(value) {
  if (!value) return "Нет данных";
  const parts = String(value).split("-");
  return parts.length === 3 ? `${parts[2]}.${parts[1]}.${parts[0]}` : String(value);
}

export function longDate(value) {
  if (!value) return "дата не указана";
  return new Intl.DateTimeFormat("ru-RU", {
    year: "numeric", month: "long", day: "numeric", timeZone: "UTC",
  }).format(new Date(`${value}T12:00:00Z`));
}

export function factValue(fact, field, { currency = true } = {}) {
  if (fact.state === "review") return "Нужна проверка";
  if (fact.state === "missing" || fact.value === null || fact.value === undefined) return "Нет данных";
  if (field === "amount") return money(fact.value, { currency });
  if (field === "delivery_date") return shortDate(fact.value);
  if (field === "penalty") return String(fact.value);
  return String(fact.value);
}

export function kindLabel(kind) {
  return kindLabels[kind] || "Документ";
}

export function stateLabel(state) {
  return stateLabels[state] || "Нужна проверка";
}

export function hasDeliveryProposal(contract) {
  return contract.proposals.some((item) => item.delivery_date.value !== null
    || item.delivery_date.state === "review"
    || item.delivery_date.citations.length > 0);
}

export function badge(text, tone = "neutral") {
  return element("span", `badge badge-${tone}`, text);
}
