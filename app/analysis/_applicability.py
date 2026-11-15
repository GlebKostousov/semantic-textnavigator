"""Проверка подписей, даты действия и связи со сторонами базового договора."""

import re
from dataclasses import dataclass
from datetime import date

from ._models import Citation, Fact, RelatedDocument, RelationState
from ._parse import ParsedDocument
from ._text import unique_citations


@dataclass(frozen=True, slots=True)
class AssessedDocument:
    """Документ вместе с результатом проверки его применимости."""

    parsed: ParsedDocument
    relation: RelatedDocument


type Gate = tuple[bool, RelationState, str]
type Decision = tuple[RelationState, str]


def metadata_citations(document: ParsedDocument) -> list[Citation]:
    """Возвращает основания о статусе, подписи и вступлении в силу."""
    metadata = document.metadata
    return unique_citations(
        [
            *metadata.status_citations,
            *metadata.signed_on.citations,
            *metadata.effective_on.citations,
            *metadata.document_date.citations,
        ]
    )


def assess_base(document: ParsedDocument, *, as_of: date) -> RelatedDocument:
    """Проверяет, можно ли использовать базовый договор на выбранную дату."""
    signature = _signature_decision(document, as_of=as_of)
    decision = signature or _base_date_decision(document, as_of=as_of)
    return _relation(document, decision=decision)


def _base_date_decision(document: ParsedDocument, *, as_of: date) -> Decision:
    checks: list[Gate] = [
        (
            document.metadata.effective_on.state == "review",
            "review",
            "Не удалось подтвердить дату вступления базового договора в силу.",
        ),
        (
            _after(document.metadata.effective_on, as_of),
            "future",
            "Базовый договор вступает в силу после даты проверки.",
        ),
    ]
    return _first_failure(checks) or (
        "base",
        "Базовый договор подписан обеими сторонами к дате проверки.",
    )


def assess_related(
    document: ParsedDocument,
    *,
    supplier: str | None,
    buyer: str | None,
    as_of: date,
) -> AssessedDocument:
    """Отделяет действующие соглашения от предложений и неопределенных документов."""
    decision = _related_decision(document, as_of=as_of)
    if decision[0] == "applied" and _parties_mismatch(
        document, supplier=supplier, buyer=buyer
    ):
        decision = (
            "review",
            "Номер договора совпадает, но стороны отличаются; связь нужно проверить.",
        )
    return AssessedDocument(parsed=document, relation=_relation(document, decision))


def _related_decision(document: ParsedDocument, *, as_of: date) -> Decision:
    if document.source.kind in {"draft", "letter"}:
        return _proposal_decision(document, as_of=as_of)
    return _amendment_decision(document, as_of=as_of)


def _proposal_decision(document: ParsedDocument, *, as_of: date) -> Decision:
    if _after(document.metadata.document_date, as_of):
        return "future", "Предложение датировано позднее даты проверки."
    return (
        "proposal",
        "Письмо или проект содержит сведения для проверки "
        "и не меняет условия договора.",
    )


def _amendment_decision(document: ParsedDocument, *, as_of: date) -> Decision:
    if document.source.kind != "amendment":
        return "review", "Не удалось определить вид связанного документа."
    if document.source.status == "unsigned":
        return "proposal", "Допсоглашение не подписано обеими сторонами."
    return _signature_decision(document, as_of=as_of) or _effective_decision(
        document, as_of=as_of
    )


def _signature_decision(document: ParsedDocument, *, as_of: date) -> Decision | None:
    checks: list[Gate] = [
        (
            document.source.status != "signed",
            "review",
            "Подписание обеими сторонами не подтверждено явным статусом.",
        ),
        (
            document.metadata.signed_on.state != "confirmed",
            "review",
            "Дата подписания обеими сторонами не установлена однозначно.",
        ),
        (
            _after(document.metadata.signed_on, as_of),
            "future",
            "Документ подписан после даты проверки.",
        ),
    ]
    return _first_failure(checks)


def _effective_decision(document: ParsedDocument, *, as_of: date) -> Decision:
    checks: list[Gate] = [
        (
            document.metadata.effective_on.state != "confirmed",
            "review",
            "Дата вступления допсоглашения в силу не установлена однозначно.",
        ),
        (
            _after(document.metadata.effective_on, as_of),
            "future",
            "Допсоглашение вступает в силу после даты проверки.",
        ),
    ]
    return _first_failure(checks) or (
        "applied",
        "Допсоглашение подписано обеими сторонами и вступило в силу к дате проверки.",
    )


def _first_failure(checks: list[Gate]) -> Decision | None:
    return next(((state, reason) for failed, state, reason in checks if failed), None)


def _after(fact: Fact[date], as_of: date) -> bool:
    return fact.value is not None and fact.value > as_of


def _parties_mismatch(
    document: ParsedDocument, *, supplier: str | None, buyer: str | None
) -> bool:
    return _party_differs(document.metadata.supplier, supplier) or _party_differs(
        document.metadata.buyer, buyer
    )


def _party_differs(actual: str | None, expected: str | None) -> bool:
    if actual is None or expected is None:
        return False
    return _normalized_supplier(actual) != _normalized_supplier(expected)


def _normalized_supplier(value: str) -> str:
    return re.sub(r'[\s«»"“”]+', "", value).casefold()


def _relation(document: ParsedDocument, decision: Decision) -> RelatedDocument:
    return RelatedDocument(
        document_id=document.source.id,
        kind=document.source.kind,
        state=decision[0],
        explanation=decision[1],
        citations=metadata_citations(document),
    )
