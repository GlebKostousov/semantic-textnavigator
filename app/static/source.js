import { badge, element, kindLabel } from "./format.js";

/** Показывает исходные абзацы с номерами; текст и цитата остаются неизменными. */
export function renderSource({ documents, documentId, paragraphId, scrollToSource }) {
  const source = documents.find((item) => item.id === documentId);
  const select = document.querySelector("#source-select");
  select.replaceChildren(...documents.map((item) => {
    const option = element("option", "", item.name);
    option.value = item.id;
    return option;
  }));
  select.value = source?.id || "";

  const title = document.querySelector("#source-heading");
  const meta = document.querySelector("#source-meta");
  const scroll = document.querySelector("#source-scroll");
  const hint = document.querySelector("#source-hint");

  meta.replaceChildren();
  scroll.replaceChildren();

  if (!source) {
    title.textContent = "Выберите условие";
    hint.textContent = "Нажмите на сумму, срок или неустойку в таблице, чтобы открыть первоисточник.";
    scroll.append(element("p", "source-empty", "Откройте документ или выберите значение в таблице."));
    return;
  }

  title.textContent = source.name;
  const signatures = {
    signed: "Подписан обеими сторонами",
    unsigned: "Не подписан сторонами",
    unknown: "Статус не подтверждён",
  };
  const isSigned = source.status === "signed";
  meta.append(
    badge(kindLabel(source.kind), isSigned ? "positive" : "warning"),
    element("span", "source-status-text", signatures[source.status] || source.status)
  );

  hint.textContent = paragraphId !== null
    ? `Выделен абзац ${paragraphId} — действующее основание проверяемого условия.`
    : "Полный текст файла. Абзацы пронумерованы для верификации цитат.";

  scroll.setAttribute("aria-label", `Исходный текст: ${source.name}`);

  let selectedParagraph = null;
  for (const paragraph of source.paragraphs) {
    const item = element("div", "source-paragraph");
    item.dataset.paragraphId = String(paragraph.id);
    item.id = `source-paragraph-${paragraph.id}`;

    const num = element("span", "paragraph-number", String(paragraph.id));
    const txt = element("p", "paragraph-text", paragraph.text);
    item.append(num, txt);

    if (paragraph.id === paragraphId) {
      item.classList.add("is-highlighted");
      item.setAttribute("aria-current", "true");
      selectedParagraph = item;
    }
    scroll.append(item);
  }

  if (!source.paragraphs.length) {
    scroll.append(element("p", "source-empty", source.text || "Текст документа пуст."));
  }

  if (!scrollToSource) return;

  requestAnimationFrame(() => {
    const behavior = matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth";
    if (selectedParagraph) {
      const offset = selectedParagraph.getBoundingClientRect().top - scroll.getBoundingClientRect().top;
      scroll.scrollTo({ top: scroll.scrollTop + offset - scroll.clientHeight / 3, behavior });
    } else {
      scroll.scrollTo({ top: 0, behavior });
    }
    if (matchMedia("(max-width: 1050px)").matches) {
      document.querySelector("#source-panel")?.scrollIntoView({ block: "start", behavior });
    }
  });
}
