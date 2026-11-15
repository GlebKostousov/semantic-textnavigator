"""Сборка извлеченных фактов одного документа без выбора действующей версии."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ._extract import extract_amount, extract_delivery, extract_penalty
from ._facts import Extracted
from ._metadata import Metadata, extract_metadata, make_source
from ._models import InputDocument, SourceDocument


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    """Источник и независимые результаты распознавания его реквизитов и условий."""

    source: SourceDocument
    metadata: Metadata
    amount: Extracted[Decimal]
    delivery_date: Extracted[date]
    penalty: Extracted[str]


def parse_document(document: InputDocument) -> ParsedDocument:
    """Извлекает условия до применения правила о подписанном допсоглашении."""
    source = make_source(document)
    return ParsedDocument(
        source=source,
        metadata=extract_metadata(source),
        amount=extract_amount(source),
        delivery_date=extract_delivery(source),
        penalty=extract_penalty(source),
    )
