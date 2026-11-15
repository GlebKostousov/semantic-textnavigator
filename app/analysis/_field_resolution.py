"""Выбор действующего значения отдельно для каждого условия договора."""

from collections import defaultdict
from collections.abc import Callable
from datetime import date

from ._applicability import AssessedDocument
from ._facts import Extracted, reviewed
from ._models import Fact, RelatedDocument
from ._parse import ParsedDocument
from ._text import unique_citations


def resolve_field[T](
    base: Extracted[T],
    related: list[AssessedDocument],
    *,
    base_relation: RelatedDocument,
    getter: Callable[[ParsedDocument], Extracted[T]],
) -> Fact[T]:
    """Применяет только изменения этого поля и не подменяет неопределенность."""
    if base_relation.state != "base":
        return reviewed(
            base.fact,
            reason=base_relation.explanation,
            citations=base_relation.citations,
        )
    fact = _apply_changes(base.fact, related, getter=getter)
    return _check_unresolved(fact, related, getter=getter)


def _apply_changes[T](
    fact: Fact[T],
    related: list[AssessedDocument],
    *,
    getter: Callable[[ParsedDocument], Extracted[T]],
) -> Fact[T]:
    applicable = [item for item in related if item.relation.state == "applied"]
    for group in _effective_groups(applicable):
        facts = [
            getter(item.parsed).fact for item in group if getter(item.parsed).mentioned
        ]
        if facts:
            fact = _apply_group(fact, facts)
    return fact


def _effective_groups(
    documents: list[AssessedDocument],
) -> list[list[AssessedDocument]]:
    groups: dict[date, list[AssessedDocument]] = defaultdict(list)
    for document in documents:
        effective_on = document.parsed.metadata.effective_on.value
        if effective_on is not None:
            groups[effective_on].append(document)
    return [groups[key] for key in sorted(groups)]


def _apply_group[T](previous: Fact[T], changes: list[Fact[T]]) -> Fact[T]:
    signatures = {(fact.value, fact.state) for fact in changes}
    citations = unique_citations(
        [citation for fact in changes for citation in fact.citations]
        + previous.citations
    )
    if len(signatures) != 1:
        return Fact[T](
            state="review",
            citations=citations,
            reason=(
                "Допсоглашения с одной датой вступления в силу противоречат друг другу."
            ),
            amended=True,
        )
    first = changes[0]
    return Fact[T](
        value=first.value,
        state=first.state,
        citations=citations,
        reason=first.reason or "Условие изменено подписанным допсоглашением.",
        amended=True,
    )


def _check_unresolved[T](
    fact: Fact[T],
    related: list[AssessedDocument],
    *,
    getter: Callable[[ParsedDocument], Extracted[T]],
) -> Fact[T]:
    unresolved = [
        item
        for item in related
        if item.relation.state == "review" and getter(item.parsed).mentioned
    ]
    if not unresolved:
        return fact
    citations = [
        citation
        for item in unresolved
        for citation in [*getter(item.parsed).fact.citations, *item.relation.citations]
    ]
    reasons = dict.fromkeys(item.relation.explanation for item in unresolved)
    return reviewed(fact, reason=" ".join(reasons), citations=citations)
