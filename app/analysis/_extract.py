"""Узкие правила извлечения суммы и срока из текстовых пунктов договора."""

import re
from datetime import date
from decimal import Decimal

from ._facts import Extracted, Observation, combine_observations
from ._models import SourceDocument
from ._text import DATE_PATTERN, TextLine, cite, lines, parse_date

_AMOUNT_CONTEXT_TEXT = (
    r"(?:общ(?:ая|ую|ей)\s+стоимост[ьи](?:\s+(?:поставки|договора))?"
    r"|сумм[ауы]\s+договора|итогов(?:ая|ую)\s+стоимост[ьи]\s+договора)"
)
_AMOUNT_CONTEXT = re.compile(_AMOUNT_CONTEXT_TEXT, re.IGNORECASE)
_NUMBER = r"(?:\d{1,3}(?:[ \u00a0\u202f]\d{3})+|\d+)(?:[.,]\d{1,2})?"
_AMOUNT_VALUE = re.compile(
    _AMOUNT_CONTEXT_TEXT
    + r"\s*(?:составляет|составит|равна|установлена\s+в\s+размере|на|[:—=-])"
    + r"\s*(?P<value>"
    + _NUMBER
    + r")\s*(?:\([^\n)]*\)\s*)?(?:руб(?:лей|ля|ль|\.)?|₽)(?!\w)",
    re.IGNORECASE,
)
_AMOUNT_DISTRACTOR = re.compile(
    r"аванс|лимит|бюджет|оплат|указанная\s+сумма|эта\s+сумма", re.IGNORECASE
)
_AMOUNT_MISSING = re.compile(
    r"не\s+(?:указан|установлен|определен|определён)"
    r"|определяется\s+(?:спецификацией|приложением)",
    re.IGNORECASE,
)
_DELIVERY_CONTEXT = re.compile(
    r"обязуется\s+поставить|(?:срок(?:а)?|дат[ауы])\s+поставки",
    re.IGNORECASE,
)
_NON_CHANGE = re.compile(
    r"не\s+изменяет|остаются\s+без\s+изменений|оста[её]тся\s+без\s+изменений"
    r"|является\s+сроком\s+оплаты|не\s+меняется",
    re.IGNORECASE,
)
_DELIVERY_VALUE = re.compile(
    r"(?:поставить[^\n]*?(?:не\s+позднее|до)"
    r"|(?:срок(?:а)?|дат[ауы])\s+поставки\s*[:—-]?\s*"
    r"(?:(?:не\s+позднее|до|на|составляет|установлен[ао]?)\s*)?)"
    r"\s*(?P<value>" + DATE_PATTERN + r")",
    re.IGNORECASE,
)
_DELIVERY_MOVE = re.compile(
    r"срок\s+поставки\s+с\s+"
    + DATE_PATTERN
    + r"\s+на\s+(?P<value>"
    + DATE_PATTERN
    + r")",
    re.IGNORECASE,
)
_DELIVERY_MISSING = re.compile(
    r"не\s+(?:указан|установлен|определен|определён)", re.IGNORECASE
)
_PENALTY_CONTEXT = re.compile(
    r"неустойк[аиеу]|штраф(?:н[аы]е)?\s+санкци[ия]",
    re.IGNORECASE,
)
_PENALTY_VALUE = re.compile(
    r"(?:неустойк[^\n]*?|штраф[^\n]*?)"
    r"(?:составляет|составит|в\s+размере|равн[ао]|–|-|:)?\s*"
    r"(?P<rate>\d+[.,]\d+\s*%|\d+\s*%)"
    r"(?:[^\n]*?(?P<per_day>за\s+каждый\s+день|в\s+день))?",
    re.IGNORECASE,
)
_PENALTY_MISSING = re.compile(
    r"не\s+(?:установлен|указан|определен|определён)", re.IGNORECASE
)


def extract_amount(document: SourceDocument) -> Extracted[Decimal]:
    """Ищет итоговую стоимость, исключая аванс и внутренний бюджет."""
    observations = [
        observation
        for line in lines(document)
        if _amount_line(line.text)
        for observation in _amount_observations(document, line)
    ]
    return combine_observations(
        observations, absent_reason="В загруженном тексте нет итоговой суммы договора."
    )


def _amount_line(text: str) -> bool:
    match = _AMOUNT_CONTEXT.search(text)
    if match is None:
        return False
    return not _AMOUNT_DISTRACTOR.search(
        text[: match.start()]
    ) and not _NON_CHANGE.search(text)


def _amount_observations(
    document: SourceDocument, line: TextLine
) -> list[Observation[Decimal]]:
    matches = list(_AMOUNT_VALUE.finditer(line.text))
    if not matches:
        return [_missing_amount(document, line)]
    return [_amount_match(document, line, match) for match in matches]


def _amount_match(
    document: SourceDocument, line: TextLine, match: re.Match[str]
) -> Observation[Decimal]:
    value = re.sub(r"\s", "", match.group("value")).replace(",", ".")
    return Observation(
        value=Decimal(value),
        state="confirmed",
        citation=cite(document, line.paragraph),
    )


def _missing_amount(document: SourceDocument, line: TextLine) -> Observation[Decimal]:
    if _AMOUNT_MISSING.search(line.text):
        return Observation(
            value=None,
            state="missing",
            citation=cite(document, line.paragraph),
            reason="Числовая сумма не указана в предоставленном тексте.",
        )
    return Observation(
        value=None,
        state="review",
        citation=cite(document, line.paragraph),
        reason="Пункт о стоимости найден, но сумму в рублях нельзя надежно извлечь.",
    )


def extract_delivery(document: SourceDocument) -> Extracted[date]:
    """Ищет срок поставки и целевую дату предложения о переносе."""
    observations = [
        observation
        for line in lines(document)
        if _delivery_line(line.text)
        for observation in _delivery_observations(document, line)
    ]
    return combine_observations(
        observations, absent_reason="В загруженном тексте нет срока поставки."
    )


def _delivery_line(text: str) -> bool:
    return bool(_DELIVERY_CONTEXT.search(text)) and not _NON_CHANGE.search(text)


def _delivery_observations(
    document: SourceDocument, line: TextLine
) -> list[Observation[date]]:
    matches = list(_DELIVERY_MOVE.finditer(line.text))
    matches = matches or list(_DELIVERY_VALUE.finditer(line.text))
    if not matches:
        return [_missing_delivery(document, line)]
    return [_delivery_match(document, line, match) for match in matches]


def _delivery_match(
    document: SourceDocument, line: TextLine, match: re.Match[str]
) -> Observation[date]:
    value = parse_date(match.group("value"))
    if value is None:
        return Observation(
            value=None,
            state="review",
            citation=cite(document, line.paragraph),
            reason="В пункте о поставке указана некорректная календарная дата.",
        )
    return Observation(
        value=value, state="confirmed", citation=cite(document, line.paragraph)
    )


def _missing_delivery(document: SourceDocument, line: TextLine) -> Observation[date]:
    if _DELIVERY_MISSING.search(line.text):
        return Observation(
            value=None,
            state="missing",
            citation=cite(document, line.paragraph),
            reason="Срок поставки не установлен в предоставленном тексте.",
        )
    return Observation(
        value=None,
        state="review",
        citation=cite(document, line.paragraph),
        reason="Срок поставки найден, но явную календарную дату извлечь не удалось.",
    )


def extract_penalty(document: SourceDocument) -> Extracted[str]:
    """Ищет ставку неустойки за просрочку поставки."""
    observations = [
        observation
        for line in lines(document)
        if _penalty_line(line.text)
        for observation in _penalty_observations(document, line)
    ]
    return combine_observations(
        observations,
        absent_reason="В загруженном тексте нет сведений о ставке неустойки.",
    )


def _penalty_line(text: str) -> bool:
    return bool(_PENALTY_CONTEXT.search(text)) and not _NON_CHANGE.search(text)


def _penalty_observations(
    document: SourceDocument, line: TextLine
) -> list[Observation[str]]:
    matches = list(_PENALTY_VALUE.finditer(line.text))
    if not matches:
        return [_missing_penalty(document, line)]
    return [_penalty_match(document, line, match) for match in matches]


def _penalty_match(
    document: SourceDocument, line: TextLine, match: re.Match[str]
) -> Observation[str]:
    rate = match.group("rate").strip()
    value = f"{rate} в день" if match.group("per_day") else rate
    return Observation(
        value=value, state="confirmed", citation=cite(document, line.paragraph)
    )


def _missing_penalty(document: SourceDocument, line: TextLine) -> Observation[str]:
    if _PENALTY_MISSING.search(line.text):
        return Observation(
            value=None,
            state="missing",
            citation=cite(document, line.paragraph),
            reason="Ставка неустойки не установлена в тексте договора.",
        )
    return Observation(
        value=None,
        state="review",
        citation=cite(document, line.paragraph),
        reason="Пункт о неустойке найден, но ставку извлечь не удалось.",
    )
