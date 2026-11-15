"""Сборка проверенных условий договора и отдельного списка предложений."""

from datetime import date
from decimal import Decimal

from ._applicability import (
    AssessedDocument,
    assess_base,
    assess_related,
    metadata_citations,
)
from ._facts import Extracted
from ._field_resolution import resolve_field
from ._models import ContractResult, Fact, Proposal, RelatedDocument
from ._parse import ParsedDocument
from ._text import unique_citations


def resolve_contract(
    number: str, documents: list[ParsedDocument], *, as_of: date
) -> ContractResult:
    """Разрешает комплект одного договора без приоритета порядка загрузки."""
    bases = [item for item in documents if item.source.kind == "contract"]
    if len(bases) != 1:
        return _ambiguous_base(number, documents, bases=bases, as_of=as_of)
    base = bases[0]
    related = _assess_others(
        documents,
        supplier=base.metadata.supplier,
        buyer=base.metadata.buyer,
        as_of=as_of,
    )
    return _single_base(number, base, related=related, as_of=as_of)


def _single_base(
    number: str,
    base: ParsedDocument,
    *,
    related: list[AssessedDocument],
    as_of: date,
) -> ContractResult:
    base_relation = assess_base(base, as_of=as_of)
    amount = resolve_field(
        base.amount, related, base_relation=base_relation, getter=_amount
    )
    delivery = resolve_field(
        base.delivery_date, related, base_relation=base_relation, getter=_delivery
    )
    penalty = resolve_field(
        base.penalty, related, base_relation=base_relation, getter=_penalty
    )
    relations = [base_relation, *[item.relation for item in related]]
    return ContractResult(
        number=number,
        supplier=base.metadata.supplier,
        amount=amount,
        delivery_date=delivery,
        penalty=penalty,
        related_documents=relations,
        proposals=_proposals(related),
        issues=_issues(amount, delivery, penalty, relations=relations),
    )


def _assess_others(
    documents: list[ParsedDocument],
    *,
    supplier: str | None,
    buyer: str | None,
    as_of: date,
) -> list[AssessedDocument]:
    return [
        assess_related(item, supplier=supplier, buyer=buyer, as_of=as_of)
        for item in documents
        if item.source.kind != "contract"
    ]


def _proposals(documents: list[AssessedDocument]) -> list[Proposal]:
    return [
        Proposal(
            document_id=item.parsed.source.id,
            kind=item.parsed.source.kind,
            amount=item.parsed.amount.fact,
            delivery_date=item.parsed.delivery_date.fact,
            penalty=item.parsed.penalty.fact,
            reason=item.relation.explanation,
            status_citations=item.relation.citations,
        )
        for item in documents
        if item.relation.state == "proposal"
    ]


def _issues(
    amount: Fact[Decimal],
    delivery: Fact[date],
    penalty: Fact[str],
    *,
    relations: list[RelatedDocument],
) -> list[str]:
    reasons = [item.explanation for item in relations if item.state == "review"]
    reasons.extend(_review_reasons([amount, delivery, penalty]))
    return list(dict.fromkeys(reasons))


def _review_reasons(facts: list[Fact[Decimal] | Fact[date] | Fact[str]]) -> list[str]:
    return [
        fact.reason
        for fact in facts
        if fact.state == "review" and fact.reason is not None
    ]


def _ambiguous_base(
    number: str,
    documents: list[ParsedDocument],
    *,
    bases: list[ParsedDocument],
    as_of: date,
) -> ContractResult:
    reason = "Загружено несколько редакций базового договора; нужна проверка источника."
    related = _assess_others(documents, supplier=None, buyer=None, as_of=as_of)
    base_relations = [_ambiguous_relation(item, reason=reason) for item in bases]
    suppliers = {item.metadata.supplier for item in bases}
    return ContractResult(
        number=number,
        supplier=next(iter(suppliers)) if len(suppliers) == 1 else None,
        amount=_ambiguous_amount(bases, reason=reason),
        delivery_date=_ambiguous_delivery(bases, reason=reason),
        penalty=_ambiguous_penalty(bases, reason=reason),
        related_documents=[*base_relations, *[item.relation for item in related]],
        proposals=_proposals(related),
        issues=[reason],
    )


def _ambiguous_relation(document: ParsedDocument, *, reason: str) -> RelatedDocument:
    return RelatedDocument(
        document_id=document.source.id,
        kind=document.source.kind,
        state="review",
        explanation=reason,
        citations=metadata_citations(document),
    )


def _ambiguous_amount(documents: list[ParsedDocument], *, reason: str) -> Fact[Decimal]:
    return Fact[Decimal](
        state="review",
        reason=reason,
        citations=unique_citations(
            [citation for item in documents for citation in item.amount.fact.citations]
        ),
    )


def _ambiguous_delivery(documents: list[ParsedDocument], *, reason: str) -> Fact[date]:
    return Fact[date](
        state="review",
        reason=reason,
        citations=unique_citations(
            [
                citation
                for item in documents
                for citation in item.delivery_date.fact.citations
            ]
        ),
    )


def _ambiguous_penalty(documents: list[ParsedDocument], *, reason: str) -> Fact[str]:
    return Fact[str](
        state="review",
        reason=reason,
        citations=unique_citations(
            [citation for item in documents for citation in item.penalty.fact.citations]
        ),
    )


def _amount(document: ParsedDocument) -> Extracted[Decimal]:
    return document.amount


def _delivery(document: ParsedDocument) -> Extracted[date]:
    return document.delivery_date


def _penalty(document: ParsedDocument) -> Extracted[str]:
    return document.penalty
