"""Проверка реквизитов документа без доверия к имени загруженного файла."""

import re
from dataclasses import dataclass
from datetime import date
from hashlib import sha256

from ._facts import Observation, combine_observations
from ._models import Citation, DocumentKind, Fact, InputDocument, SourceDocument
from ._text import DATE_PATTERN, TextLine, cite, lines, make_paragraphs, parse_date

_TOKEN = r"[A-ZА-ЯЁ0-9][A-ZА-ЯЁ0-9/_.-]*"
_CONTRACT_NUMBER = re.compile(
    r"\bдоговор(?:а|у|ом|е)?(?:\s+поставки)?\s+(?:№\s*)?"
    r"(?P<number>(?=[A-ZА-ЯЁ0-9/_.-]*\d)" + _TOKEN + r")",
    re.IGNORECASE,
)
_STATUS = re.compile(r"^\s*Статус:[ \t]*(?P<status>.+)$", re.IGNORECASE)
_SIGNED = re.compile(r"подписан[оа]?\s+(?:обеими\s+)?сторонами", re.IGNORECASE)
_UNSIGNED = re.compile(
    r"не\s+подписан|подписан[оа]?\s+(?:только\s+)?одной\s+стороной|проект",
    re.IGNORECASE,
)
_DOCUMENT_DATE = re.compile(
    r"^\s*Дата(?:\s+проекта)?:\s*(?P<value>" + DATE_PATTERN + r")",
    re.IGNORECASE,
)
_SIGNATURE_DATE = re.compile(
    r"^\s*Статус:[^\n]*?подписан[оа]?\s+(?:обеими\s+)?сторонами\s*"
    r"(?P<value>" + DATE_PATTERN + r")",
    re.IGNORECASE,
)
_EFFECTIVE_DATE = re.compile(
    r"вступ(?:ает|ают|ит|ят)\s+в\s+силу\s+(?:с\s+)?"
    r"(?P<value>" + DATE_PATTERN + r")",
    re.IGNORECASE,
)
_SUPPLIER = re.compile(
    r"Поставщик:[ \t]*(?P<value>.+?)(?=\.\s*(?:Покупатель:|Предмет:)|$)",
    re.IGNORECASE,
)
_BUYER = re.compile(
    r"Покупатель:[ \t]*(?P<value>.+?)(?=\.\s*(?:Поставщик:|Предмет:)|$)",
    re.IGNORECASE,
)
_SENDER = re.compile(r"^\s*От:[ \t]*(?P<value>.+)$", re.IGNORECASE)
_NEGATED_EFFECTIVE = re.compile(
    r"не\s+вступ(?:ает|ают|ит|ят)\s+в\s+силу", re.IGNORECASE
)


@dataclass(frozen=True, slots=True)
class Metadata:
    """Реквизиты, необходимые для связи и проверки временной применимости."""

    supplier: str | None
    buyer: str | None
    document_date: Fact[date]
    signed_on: Fact[date]
    effective_on: Fact[date]
    status_citations: list[Citation]


def make_source(document: InputDocument) -> SourceDocument:
    """Создает адресуемый источник; имя файла не участвует в извлечении полей."""
    paragraphs = make_paragraphs(document.text)
    header = document.text.lstrip().splitlines()[0] if paragraphs else ""
    signature = _signature_status(document.text)
    return SourceDocument(
        id=sha256((document.name + "\0" + document.text).encode()).hexdigest()[:20],
        name=document.name,
        text=document.text,
        kind=_document_kind(header),
        contract_number=_contract_number(document.text),
        status=signature,
        paragraphs=paragraphs,
    )


def _document_kind(header: str) -> DocumentKind:
    kinds: list[tuple[str, DocumentKind]] = [
        (r"^\s*проект.*дополнительн", "draft"),
        (r"^\s*дополнительн.*соглашен", "amendment"),
        (r"^\s*договор\b", "contract"),
        (r"^\s*письмо\b", "letter"),
    ]
    matches = [kind for pattern, kind in kinds if re.search(pattern, header, re.I)]
    return matches[0] if matches else "unknown"


def _contract_number(text: str) -> str | None:
    numbers = {
        match.group("number").rstrip(".,;:").upper()
        for match in _CONTRACT_NUMBER.finditer(text)
    }
    return next(iter(numbers)) if len(numbers) == 1 else None


def _signature_status(text: str) -> str:
    statuses = {
        _status_value(match.group("status"))
        for line in text.splitlines()
        if (match := _STATUS.search(line))
    }
    return next(iter(statuses)) if len(statuses) == 1 else "unknown"


def _status_value(text: str) -> str:
    if _UNSIGNED.search(text):
        return "unsigned"
    return "signed" if _SIGNED.search(text) else "unknown"


def extract_metadata(document: SourceDocument) -> Metadata:
    """Извлекает только явно названные даты документа, подписания и действия."""
    return Metadata(
        supplier=_supplier(document),
        buyer=_buyer(document),
        document_date=_date_fact(document, pattern=_DOCUMENT_DATE),
        signed_on=_date_fact(document, pattern=_SIGNATURE_DATE),
        effective_on=_date_fact(document, pattern=_EFFECTIVE_DATE),
        status_citations=_status_citations(document),
    )


def _supplier(document: SourceDocument) -> str | None:
    suppliers = _supplier_values(document, pattern=_SUPPLIER)
    suppliers = suppliers or _supplier_values(document, pattern=_SENDER)
    return next(iter(suppliers)) if len(suppliers) == 1 else None


def _buyer(document: SourceDocument) -> str | None:
    buyers = _supplier_values(document, pattern=_BUYER)
    return next(iter(buyers)) if len(buyers) == 1 else None


def _supplier_values(document: SourceDocument, *, pattern: re.Pattern[str]) -> set[str]:
    return {
        match.group("value").strip().rstrip(".")
        for line in lines(document)
        if (match := pattern.search(line.text))
    }


def _date_fact(document: SourceDocument, *, pattern: re.Pattern[str]) -> Fact[date]:
    observations = [
        _date_observation(document, line, match.group("value"))
        for line in lines(document)
        for match in pattern.finditer(line.text)
    ]
    return combine_observations(
        observations, absent_reason="Нужная дата не указана явно."
    ).fact


def _date_observation(
    document: SourceDocument, line: TextLine, raw_value: str
) -> Observation[date]:
    value = parse_date(raw_value)
    if _NEGATED_EFFECTIVE.search(line.text):
        return Observation(
            value=None,
            state="review",
            citation=cite(document, line.paragraph),
            reason="Текст отрицает вступление документа в силу в указанную дату.",
        )
    if value is None:
        return Observation(
            value=None,
            state="review",
            citation=cite(document, line.paragraph),
            reason="В реквизитах документа указана некорректная календарная дата.",
        )
    return Observation(
        value=value, state="confirmed", citation=cite(document, line.paragraph)
    )


def _status_citations(document: SourceDocument) -> list[Citation]:
    citations = [
        cite(document, line.paragraph)
        for line in lines(document)
        if _STATUS.search(line.text)
    ]
    if not citations and document.paragraphs:
        return [cite(document, document.paragraphs[0])]
    return citations
