"""Разбиение текста с сохранением координат для проверяемых цитат."""

import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

from ._models import Citation, Paragraph, SourceDocument

DATE_PATTERN = r"\d{1,2}\.\d{1,2}\.\d{4}"
_PARAGRAPH_BREAK = re.compile(r"(?:\r?\n)[\t ]*(?:\r?\n)+")


@dataclass(frozen=True, slots=True)
class TextLine:
    """Непустая строка и содержащий ее исходный абзац."""

    text: str
    paragraph: Paragraph


def make_paragraphs(text: str) -> list[Paragraph]:
    """Выделяет абзацы без изменения исходной строки и ее смещений."""
    boundaries = [0, *[match.end() for match in _PARAGRAPH_BREAK.finditer(text)]]
    endings = [
        *[match.start() for match in _PARAGRAPH_BREAK.finditer(text)],
        len(text),
    ]
    spans = [(start, end) for start, end in zip(boundaries, endings, strict=True)]
    return _trimmed_paragraphs(text, spans)


def _trimmed_paragraphs(text: str, spans: list[tuple[int, int]]) -> list[Paragraph]:
    """Убирает только окружающий пробел, корректируя координаты абзацев."""
    result: list[Paragraph] = []
    for start, end in spans:
        raw = text[start:end]
        content = raw.strip()
        if content:
            offset = start + len(raw) - len(raw.lstrip())
            result.append(
                Paragraph(
                    id=len(result) + 1,
                    text=content,
                    start=offset,
                    end=offset + len(content),
                )
            )
    return result


def lines(document: SourceDocument) -> Iterator[TextLine]:
    """Возвращает строки отдельно, чтобы срок оплаты не смешивался с поставкой."""
    for paragraph in document.paragraphs:
        for text in paragraph.text.splitlines():
            yield TextLine(text=text, paragraph=paragraph)


def cite(document: SourceDocument, paragraph: Paragraph) -> Citation:
    """Создает ссылку на весь исходный абзац, включая пункт договора."""
    return Citation(
        document_id=document.id,
        filename=document.name,
        paragraph_id=paragraph.id,
        quote=paragraph.text,
        start=paragraph.start,
        end=paragraph.end,
    )


def unique_citations(citations: list[Citation]) -> list[Citation]:
    """Сохраняет порядок оснований и убирает повтор одной цитаты."""
    unique = {(item.document_id, item.paragraph_id): item for item in citations}
    return list(unique.values())


def parse_date(value: str) -> date | None:
    """Проверяет календарную корректность числовой даты из документа."""
    day, month, year = (int(part) for part in value.split("."))
    try:
        return date(year, month, day)
    except ValueError:
        return None
