"""Подготовь исходные тексты и проверь цитаты без зависимости от правил разбора."""

from pathlib import Path
from typing import Final

from app.analysis import AnalysisResult, InputDocument
from app.analysis._models import Citation, ContractResult, SourceDocument

SAMPLE_DIRECTORY: Final[Path] = (
    Path(__file__).resolve().parents[1] / "examples" / "documents"
)


def sample_document(filename: str) -> InputDocument:
    """Прочитай неизменённый учебный документ.

    Args:
        filename: имя файла в комплекте примеров.

    Returns:
        Имя и полный текст документа.
    """
    return InputDocument(
        name=filename,
        text=(SAMPLE_DIRECTORY / filename).read_text(encoding="utf-8"),
    )


def sample_documents() -> list[InputDocument]:
    """Прочитай весь учебный комплект в воспроизводимом порядке.

    Returns:
        Шесть исходных документов.
    """
    return [
        sample_document(path.name) for path in sorted(SAMPLE_DIRECTORY.glob("*.txt"))
    ]


def changed_document(
    filename: str,
    replacements: tuple[tuple[str, str], ...],
    *,
    name: str | None = None,
) -> InputDocument:
    """Измени поля примера и отклони незаметно не сработавшую замену.

    Args:
        filename: исходный учебный файл.
        replacements: последовательность пар старого и нового текста.
        name: новое имя файла, если оно нужно для сценария.

    Returns:
        Документ с изменённым содержимым.
    """
    original = sample_document(filename)
    text = original.text
    for old, new in replacements:
        assert old in text, f"В {filename} не найден изменяемый фрагмент {old!r}"
        text = text.replace(old, new)
    return InputDocument(name=name or filename, text=text)


def contract_for(result: AnalysisResult, number: str) -> ContractResult:
    """Найди ровно один результат указанного договора.

    Args:
        result: ответ анализатора.
        number: номер из содержимого документов.

    Returns:
        Единственная строка договора.
    """
    matches = [contract for contract in result.contracts if contract.number == number]
    assert len(matches) == 1, (
        f"Для {number} ожидался один договор, получено {len(matches)}"
    )
    return matches[0]


def citations_for(contract: ContractResult) -> list[Citation]:
    """Собери основания значений, статусов и предложений договора.

    Args:
        contract: результат сверки одного договора.

    Returns:
        Все доступные пользователю ссылки на исходные абзацы.
    """
    citations = [*contract.amount.citations, *contract.delivery_date.citations]
    for related in contract.related_documents:
        citations.extend(related.citations)
    for proposal in contract.proposals:
        citations.extend(proposal.amount.citations)
        citations.extend(proposal.delivery_date.citations)
        citations.extend(proposal.status_citations)
    return citations


def assert_citation_matches_source(
    citation: Citation,
    documents: dict[str, SourceDocument],
) -> None:
    """Проверь буквальную цитату и адрес её абзаца в исходном тексте.

    Args:
        citation: опубликованное основание результата.
        documents: исходные документы по идентификаторам.
    """
    assert citation.document_id in documents
    source = documents[citation.document_id]
    assert citation.filename == source.name
    assert 0 <= citation.start < citation.end <= len(source.text)
    assert source.text[citation.start : citation.end] == citation.quote
    paragraphs = {paragraph.id: paragraph for paragraph in source.paragraphs}
    assert citation.paragraph_id in paragraphs
    paragraph = paragraphs[citation.paragraph_id]
    assert source.text[paragraph.start : paragraph.end] == paragraph.text
    assert paragraph.start <= citation.start < citation.end <= paragraph.end


def assert_all_citations_match(result: AnalysisResult) -> None:
    """Проверь уникальность источников и каждую опубликованную цитату.

    Args:
        result: полный результат анализа.
    """
    documents = {document.id: document for document in result.documents}
    assert len(documents) == len(result.documents)
    citations = [
        citation
        for contract in result.contracts
        for citation in citations_for(contract)
    ]
    assert citations, "Результат не содержит проверяемых оснований"
    for citation in citations:
        assert_citation_matches_source(citation, documents)
