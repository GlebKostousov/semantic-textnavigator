"""Сведение независимых совпадений без выбора удобного числового значения."""

from dataclasses import dataclass

from ._models import Citation, Fact, FactState
from ._text import unique_citations


@dataclass(frozen=True, slots=True)
class Observation[T]:
    """Одно распознанное утверждение в исходной строке."""

    value: T | None
    state: FactState
    citation: Citation
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class Extracted[T]:
    """Поле и признак, что документ действительно затрагивает это условие."""

    fact: Fact[T]
    mentioned: bool


def combine_observations[T](
    observations: list[Observation[T]], *, absent_reason: str
) -> Extracted[T]:
    """Отказывается выбирать одно из противоречащих утверждений."""
    if not observations:
        return Extracted(fact=Fact[T](reason=absent_reason), mentioned=False)
    citations = unique_citations([item.citation for item in observations])
    return Extracted(
        fact=_combine_present(observations, citations=citations), mentioned=True
    )


def _combine_present[T](
    observations: list[Observation[T]], *, citations: list[Citation]
) -> Fact[T]:
    values = {item.value for item in observations}
    states = {item.state for item in observations}
    if len(values) > 1 or len(states) > 1:
        return Fact[T](
            state="review",
            citations=citations,
            reason="В документе есть противоречащие сведения об этом условии.",
        )
    first = observations[0]
    return Fact[T](
        value=first.value,
        state=first.state,
        citations=citations,
        reason=first.reason,
    )


def reviewed[T](fact: Fact[T], *, reason: str, citations: list[Citation]) -> Fact[T]:
    """Убирает неподтвержденное значение, сохраняя все основания для проверки."""
    return Fact[T](
        state="review",
        citations=unique_citations([*citations, *fact.citations]),
        reason=reason,
        amended=fact.amended,
    )
