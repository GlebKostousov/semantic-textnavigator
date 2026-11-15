"""Публичный сценарий проверки условий договоров по загруженному тексту."""

from collections.abc import Sequence
from datetime import date

from ._models import AnalysisResult, InputDocument
from ._parse import ParsedDocument, parse_document
from ._resolution import resolve_contract


def analyze_documents(
    documents: Sequence[InputDocument], *, as_of: date
) -> AnalysisResult:
    """Извлекает условия и проверяет, какие документы действуют на выбранную дату.

    Args:
        documents: проверенные входные TXT-файлы без изменения исходного текста.
        as_of: дата, на которую нужно установить действующие условия.

    Returns:
        Договоры, отдельные предложения и точные основания для каждого поля.
    """
    parsed = sorted(
        (parse_document(document) for document in documents),
        key=lambda item: (item.source.name.casefold(), item.source.id),
    )
    numbers = _base_numbers(parsed)
    unlinked = [item for item in parsed if item.source.contract_number not in numbers]
    return AnalysisResult(
        as_of=as_of,
        documents=[item.source for item in parsed],
        contracts=[
            resolve_contract(number, _for_contract(parsed, number), as_of=as_of)
            for number in sorted(numbers)
        ],
        warnings=[_unlinked_warning(item) for item in unlinked],
        unlinked_document_ids=[item.source.id for item in unlinked],
    )


def _base_numbers(documents: list[ParsedDocument]) -> set[str]:
    return {
        item.source.contract_number
        for item in documents
        if item.source.kind == "contract" and item.source.contract_number is not None
    }


def _for_contract(documents: list[ParsedDocument], number: str) -> list[ParsedDocument]:
    return [item for item in documents if item.source.contract_number == number]


def _unlinked_warning(document: ParsedDocument) -> str:
    if document.source.contract_number is None:
        return f"{document.source.name}: номер договора не определен однозначно."
    return (
        f"{document.source.name}: базовый договор отсутствует в загруженном комплекте."
    )
