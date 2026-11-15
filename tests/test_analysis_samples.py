"""Проверь ответы закупщику, изменённые входы и привязку к исходным абзацам."""

from datetime import date
from decimal import Decimal
from typing import Final

import pytest

from app.analysis import InputDocument, analyze_documents

from .test_analysis_helpers import (
    assert_all_citations_match,
    changed_document,
    contract_for,
    sample_document,
    sample_documents,
)

CHECK_DATE: Final[date] = date(2026, 3, 10)


def test_sample_contracts_have_the_agreed_amounts_and_delivery_dates() -> None:
    """Покажи три договора с учётом подписанного соглашения на дату проверки."""
    result = analyze_documents(sample_documents(), as_of=CHECK_DATE)

    assert result.as_of == CHECK_DATE
    assert {contract.number for contract in result.contracts} == {
        "STN-101",
        "STN-102",
        "STN-103",
    }
    first = contract_for(result, "STN-101")
    assert first.supplier == "ООО «Вектор Прибор»"
    assert first.amount.value == Decimal("1380000")
    assert first.amount.state == "confirmed"
    assert first.delivery_date.value == date(2026, 4, 30)
    assert first.delivery_date.state == "confirmed"
    assert first.penalty.value == "0,1% в день"
    assert first.penalty.state == "confirmed"
    assert first.amount.amended
    assert first.delivery_date.amended
    second = contract_for(result, "STN-102")
    assert second.supplier == "ООО «Контур Электро»"
    assert second.amount.value == Decimal("840000")
    assert second.delivery_date.value == date(2026, 3, 20)
    assert second.penalty.value == "0,05% в день"
    assert second.penalty.state == "confirmed"
    assert not second.amount.amended
    assert not second.delivery_date.amended
    third = contract_for(result, "STN-103")
    assert third.supplier == "ООО «ПромСнаб Сервис»"
    assert third.delivery_date.value == date(2026, 4, 30)
    assert third.penalty.state == "missing"
    assert third.penalty.value is None


def test_unsigned_draft_retains_its_values_separately_from_current_terms() -> None:
    """Сохрани проект с новой ценой и датой отдельно от действующих условий."""
    result = analyze_documents(sample_documents(), as_of=CHECK_DATE)
    contract = contract_for(result, "STN-101")

    assert len(contract.proposals) == 1
    proposal = contract.proposals[0]
    assert proposal.kind == "draft"
    assert proposal.amount.value == Decimal("1450000")
    assert proposal.delivery_date.value == date(2026, 5, 10)
    assert proposal.amount.citations
    assert proposal.delivery_date.citations
    assert proposal.status_citations
    assert proposal.reason
    assert contract.amount.value != proposal.amount.value
    assert contract.delivery_date.value != proposal.delivery_date.value


def test_supplier_letter_keeps_proposed_and_agreed_dates_separate() -> None:
    """Покажи просьбу о переносе на 27 марта при действующем сроке 20 марта."""
    result = analyze_documents(sample_documents(), as_of=CHECK_DATE)
    contract = contract_for(result, "STN-102")

    assert len(contract.proposals) == 1
    proposal = contract.proposals[0]
    assert proposal.kind == "letter"
    assert proposal.delivery_date.value == date(2026, 3, 27)
    assert proposal.delivery_date.citations
    assert contract.delivery_date.value == date(2026, 3, 20)
    relations = {item.document_id: item for item in contract.related_documents}
    assert relations[proposal.document_id].state == "proposal"


def test_missing_specification_does_not_turn_budget_into_contract_price() -> None:
    """Объясни отсутствие суммы ссылкой на отсутствующую спецификацию."""
    result = analyze_documents(sample_documents(), as_of=CHECK_DATE)
    fact = contract_for(result, "STN-103").amount

    assert fact.value is None
    assert fact.state == "missing"
    assert fact.reason
    assert fact.citations
    assert any(
        "Приложение № 1" in citation.quote
        or "Числовое значение стоимости" in citation.quote
        for citation in fact.citations
    )


def test_delivery_before_april_includes_the_unagreed_supplier_request() -> None:
    """Ответь на вопрос о ранних поставках по действующим срокам."""
    result = analyze_documents(sample_documents(), as_of=CHECK_DATE)
    early = [
        contract
        for contract in result.contracts
        if contract.delivery_date.state == "confirmed"
        and contract.delivery_date.value is not None
        and contract.delivery_date.value < date(2026, 4, 1)
    ]

    assert [contract.number for contract in early] == ["STN-102"]
    assert early[0].proposals[0].delivery_date.value == date(2026, 3, 27)


def test_all_sample_citations_point_to_exact_original_paragraphs() -> None:
    """Проверь каждую цитату, включая основания статуса и отсутствия суммы."""
    documents = sample_documents()
    result = analyze_documents(documents, as_of=CHECK_DATE)

    assert {source.name: source.text for source in result.documents} == {
        document.name: document.text for document in documents
    }
    assert_all_citations_match(result)
    amended = contract_for(result, "STN-101")
    assert any(
        citation.filename == "02_amendment_signed.txt"
        for citation in amended.amount.citations
    )
    assert any(
        citation.filename == "02_amendment_signed.txt"
        for citation in amended.delivery_date.citations
    )


@pytest.mark.parametrize(
    "order", [(0, 1, 2, 3, 4, 5), (5, 4, 3, 2, 1, 0), (2, 5, 0, 4, 3, 1)]
)
def test_file_names_and_upload_order_do_not_determine_conditions(
    order: tuple[int, ...],
) -> None:
    """Выбери условия по тексту при переименовании и перестановке файлов.

    Args:
        order: порядок загрузки шести исходных текстов.
    """
    documents = sample_documents()
    renamed = [
        InputDocument(name=f"2099-12-{31 - index}_upload.txt", text=document.text)
        for index, document in enumerate(documents)
    ]
    result = analyze_documents([renamed[index] for index in order], as_of=CHECK_DATE)

    assert contract_for(result, "STN-101").amount.value == Decimal("1380000")
    assert contract_for(result, "STN-101").delivery_date.value == date(2026, 4, 30)
    assert contract_for(result, "STN-102").delivery_date.value == date(2026, 3, 20)
    assert contract_for(result, "STN-103").amount.value is None
    assert_all_citations_match(result)


def test_new_contract_and_modified_fields_are_read_from_uploaded_text() -> None:
    """Извлеки неизвестный номер, поставщика, сумму и срок того же формата."""
    document = changed_document(
        "03_contract.txt",
        (
            ("STN-102", "NEW-2048"),
            ("Контур Электро", "Тестовые приборы"),
            ("840 000", "963 500"),
            ("восемьсот сорок тысяч", "девятьсот шестьдесят три тысячи пятьсот"),
            ("20.03.2026", "18.05.2026"),
        ),
        name="new_document.txt",
    )
    result = analyze_documents([document], as_of=CHECK_DATE)
    contract = contract_for(result, "NEW-2048")

    assert len(result.contracts) == 1
    assert contract.supplier == "ООО «Тестовые приборы»"
    assert contract.amount.value == Decimal("963500")
    assert contract.delivery_date.value == date(2026, 5, 18)
    assert_all_citations_match(result)


def test_advance_and_payment_deadline_are_not_total_and_delivery_date() -> None:
    """Не подмени договорную сумму авансом, а поставку сроком оплаты."""
    document = changed_document(
        "03_contract.txt",
        (("252 000", "9 999 999"), ("10.04.2026", "01.01.2020")),
    )
    result = analyze_documents([document], as_of=CHECK_DATE)
    contract = contract_for(result, "STN-102")

    assert contract.amount.value == Decimal("840000")
    assert contract.delivery_date.value == date(2026, 3, 20)
    assert_all_citations_match(result)


def test_missing_total_cannot_be_replaced_with_advance() -> None:
    """Оставь сумму неизвестной, если в тексте остался только аванс."""
    document = changed_document(
        "03_contract.txt",
        (
            (
                "2.1. Общая стоимость поставки составляет "
                "840 000 (восемьсот сорок тысяч) "
                "рублей, включая НДС. Указанная сумма — итоговая стоимость договора.",
                "2.1. Сумма договора в представленном тексте не указана.",
            ),
        ),
    )
    result = analyze_documents([document], as_of=CHECK_DATE)
    fact = contract_for(result, "STN-102").amount

    assert fact.value is None
    assert fact.state == "missing"
    assert fact.reason


def test_missing_delivery_clause_cannot_be_replaced_with_payment_date() -> None:
    """Оставь срок поставки неизвестным при наличии только даты оплаты."""
    document = changed_document(
        "03_contract.txt",
        (
            (
                "3.1. Поставщик обязуется поставить комплектующие "
                "не позднее 20.03.2026.",
                "3.1. Срок поставки в представленном тексте не установлен.",
            ),
        ),
    )
    result = analyze_documents([document], as_of=CHECK_DATE)
    fact = contract_for(result, "STN-102").delivery_date

    assert fact.value is None
    assert fact.state == "missing"
    assert fact.reason


def test_same_filenames_keep_distinct_sources_and_correct_citations() -> None:
    """Не смешивай договор и соглашение при совпадении загруженных имён."""
    original = [
        sample_document("01_contract.txt"),
        sample_document("02_amendment_signed.txt"),
    ]
    documents = [
        InputDocument(name="document.txt", text=item.text) for item in original
    ]
    result = analyze_documents(documents, as_of=CHECK_DATE)

    assert len({document.id for document in result.documents}) == 2
    assert contract_for(result, "STN-101").amount.value == Decimal("1380000")
    assert_all_citations_match(result)


def test_windows_line_endings_preserve_quotes_and_character_offsets() -> None:
    """Сохрани точные смещения при Windows-переносах и кириллице."""
    original = sample_document("03_contract.txt")
    document = InputDocument(
        name="windows.txt", text=original.text.replace("\n", "\r\n")
    )
    result = analyze_documents([document], as_of=CHECK_DATE)

    assert result.documents[0].text == document.text
    assert contract_for(result, "STN-102").amount.value == Decimal("840000")
    assert_all_citations_match(result)


def test_letter_without_its_contract_is_reported_as_unlinked() -> None:
    """Не превращай письмо без базового договора в подтверждённые условия."""
    document = changed_document("05_supplier_email.txt", (("STN-102", "STN-404"),))
    result = analyze_documents([document], as_of=CHECK_DATE)

    assert not result.contracts
    assert result.unlinked_document_ids == [result.documents[0].id]
    assert result.warnings


def test_penalty_rate_extracted_and_linked_to_citation() -> None:
    """Извлеки ставку неустойки с точной цитатой и сохрани отсутствие условий."""
    result = analyze_documents(sample_documents(), as_of=CHECK_DATE)
    stn_101 = contract_for(result, "STN-101")
    assert stn_101.penalty.value == "0,1% в день"
    assert stn_101.penalty.state == "confirmed"
    assert stn_101.penalty.citations
    assert "0,1%" in stn_101.penalty.citations[0].quote

    stn_103 = contract_for(result, "STN-103")
    assert stn_103.penalty.value is None
    assert stn_103.penalty.state == "missing"
    assert stn_103.penalty.citations
    assert "не установлена" in stn_103.penalty.citations[0].quote
