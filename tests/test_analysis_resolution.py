"""Проверь силу соглашений на дату проверки и отказ от неоднозначных выводов."""

from datetime import date
from decimal import Decimal
from typing import Final

import pytest

from app.analysis import analyze_documents

from .test_analysis_helpers import (
    assert_all_citations_match,
    changed_document,
    contract_for,
    sample_document,
)

CHECK_DATE: Final[date] = date(2026, 3, 10)


@pytest.mark.parametrize(
    ("as_of", "amount", "delivery", "amended"),
    [
        (date(2026, 2, 28), Decimal("1200000"), date(2026, 4, 15), False),
        (date(2026, 3, 1), Decimal("1380000"), date(2026, 4, 30), True),
        (date(2026, 3, 10), Decimal("1380000"), date(2026, 4, 30), True),
    ],
)
def test_signed_amendment_applies_from_its_effective_date_inclusively(
    as_of: date,
    amount: Decimal,
    delivery: date,
    *,
    amended: bool,
) -> None:
    """Учитывай соглашение с даты вступления в силу, включая сам этот день.

    Args:
        as_of: дата проверки документов.
        amount: ожидаемая действующая сумма.
        delivery: ожидаемый действующий срок.
        amended: должен ли результат ссылаться на изменение договора.
    """
    documents = [
        sample_document("01_contract.txt"),
        sample_document("02_amendment_signed.txt"),
    ]
    result = analyze_documents(documents, as_of=as_of)
    contract = contract_for(result, "STN-101")

    assert contract.amount.value == amount
    assert contract.delivery_date.value == delivery
    assert contract.amount.amended is amended
    assert contract.delivery_date.amended is amended
    assert_all_citations_match(result)


def test_signed_but_future_amendment_keeps_current_base_conditions() -> None:
    """Не применяй подписанное изменение до явно указанной даты его силы."""
    amendment = changed_document(
        "02_amendment_signed.txt",
        (("вступает в силу 01.03.2026", "вступает в силу 25.03.2026"),),
    )
    result = analyze_documents(
        [sample_document("01_contract.txt"), amendment], as_of=CHECK_DATE
    )
    contract = contract_for(result, "STN-101")

    assert contract.amount.value == Decimal("1200000")
    assert contract.delivery_date.value == date(2026, 4, 15)
    assert any(related.state == "future" for related in contract.related_documents)


def test_later_signature_cannot_change_conditions_before_signing() -> None:
    """Не считай соглашение подписанным раньше даты подписи из его текста."""
    amendment = changed_document(
        "02_amendment_signed.txt",
        (
            (
                "подписано обеими сторонами 01.03.2026",
                "подписано обеими сторонами 15.03.2026",
            ),
        ),
    )
    result = analyze_documents(
        [sample_document("01_contract.txt"), amendment], as_of=CHECK_DATE
    )
    contract = contract_for(result, "STN-101")

    assert not (
        contract.amount.value == Decimal("1380000")
        and contract.amount.state == "confirmed"
    )
    assert not (
        contract.delivery_date.value == date(2026, 4, 30)
        and contract.delivery_date.state == "confirmed"
    )
    assert all(related.state != "applied" for related in contract.related_documents)


@pytest.mark.parametrize(
    "status",
    [
        "не подписано ни одной стороной.",
        "подписано только поставщиком 01.03.2026.",
        "на согласовании.",
    ],
)
def test_unconfirmed_signature_does_not_apply_amendment(status: str) -> None:
    """Не применяй документ без подтверждения подписей обеих сторон.

    Args:
        status: неподписанный, односторонний или неизвестный статус.
    """
    amendment = changed_document(
        "02_amendment_signed.txt",
        (("подписано обеими сторонами 01.03.2026.", status),),
    )
    result = analyze_documents(
        [sample_document("01_contract.txt"), amendment], as_of=CHECK_DATE
    )
    contract = contract_for(result, "STN-101")

    assert not (
        contract.amount.value == Decimal("1380000")
        and contract.amount.state == "confirmed"
    )
    assert not (
        contract.delivery_date.value == date(2026, 4, 30)
        and contract.delivery_date.state == "confirmed"
    )
    assert all(related.state != "applied" for related in contract.related_documents)


def test_unknown_effective_date_requires_review_instead_of_using_header_date() -> None:
    """Не подставляй дату документа вместо неизвестной даты вступления в силу."""
    amendment = changed_document(
        "02_amendment_signed.txt",
        (
            (
                "вступает в силу 01.03.2026",
                "вступает в силу с согласованной сторонами даты",
            ),
        ),
    )
    result = analyze_documents(
        [sample_document("01_contract.txt"), amendment], as_of=CHECK_DATE
    )
    contract = contract_for(result, "STN-101")

    assert contract.amount.state == "review"
    assert contract.delivery_date.state == "review"
    assert contract.issues
    assert all(related.state != "applied" for related in contract.related_documents)


def test_two_effective_dates_in_same_amendment_require_review() -> None:
    """Не выбирай одну из противоречащих дат силы внутри соглашения."""
    amendment = changed_document(
        "02_amendment_signed.txt",
        (
            (
                "4. Настоящее соглашение вступает в силу 01.03.2026.",
                "4. Настоящее соглашение вступает в силу 01.03.2026.\n\n"
                "5. Настоящее соглашение вступает в силу 05.03.2026.",
            ),
        ),
    )
    result = analyze_documents(
        [sample_document("01_contract.txt"), amendment], as_of=CHECK_DATE
    )
    contract = contract_for(result, "STN-101")

    assert contract.amount.state == "review"
    assert contract.delivery_date.state == "review"
    assert contract.issues


def test_conflicting_amendments_effective_on_same_day_require_review() -> None:
    """Не назначай приоритет разным условиям с одной датой вступления в силу."""
    competing = changed_document(
        "02_amendment_signed.txt",
        (
            ("№ 1 К ДОГОВОРУ", "№ 2 К ДОГОВОРУ"),
            ("1 380 000", "1 500 000"),
            ("один миллион триста восемьдесят тысяч", "один миллион пятьсот тысяч"),
            ("30.04.2026", "20.05.2026"),
        ),
        name="competing_amendment.txt",
    )
    documents = [
        sample_document("01_contract.txt"),
        sample_document("02_amendment_signed.txt"),
        competing,
    ]
    result = analyze_documents(documents, as_of=CHECK_DATE)
    contract = contract_for(result, "STN-101")

    assert contract.amount.state == "review"
    assert contract.delivery_date.state == "review"
    assert contract.issues
    assert_all_citations_match(result)


@pytest.mark.parametrize("reverse", [False, True])
def test_later_effective_amendment_wins_without_upload_priority(
    *, reverse: bool
) -> None:
    """Применяй последовательные соглашения по датам силы независимо от порядка.

    Args:
        reverse: загружать ли документы в обратном порядке.
    """
    later = changed_document(
        "02_amendment_signed.txt",
        (
            ("№ 1 К ДОГОВОРУ", "№ 2 К ДОГОВОРУ"),
            ("01.03.2026", "05.03.2026"),
            ("1 380 000", "1 500 000"),
            ("один миллион триста восемьдесят тысяч", "один миллион пятьсот тысяч"),
            ("30.04.2026", "20.05.2026"),
        ),
        name="earlier_file_name.txt",
    )
    documents = [
        sample_document("01_contract.txt"),
        sample_document("02_amendment_signed.txt"),
        later,
    ]
    ordered = list(reversed(documents)) if reverse else documents
    result = analyze_documents(ordered, as_of=CHECK_DATE)
    contract = contract_for(result, "STN-101")

    assert contract.amount.value == Decimal("1500000")
    assert contract.amount.state == "confirmed"
    assert contract.delivery_date.value == date(2026, 5, 20)
    assert contract.delivery_date.state == "confirmed"
    assert_all_citations_match(result)


def test_two_conflicting_base_contracts_require_review() -> None:
    """Не выбирай произвольную редакцию базового договора с другой суммой."""
    competing = changed_document(
        "03_contract.txt",
        (("840 000", "900 000"), ("восемьсот сорок тысяч", "девятьсот тысяч")),
        name="another_contract_revision.txt",
    )
    result = analyze_documents(
        [sample_document("03_contract.txt"), competing], as_of=CHECK_DATE
    )
    contract = contract_for(result, "STN-102")

    assert contract.amount.state == "review"
    assert contract.issues
    assert_all_citations_match(result)


def test_amendment_changes_only_the_explicitly_replaced_field() -> None:
    """Сохрани исходную сумму, если соглашение меняет только срок поставки."""
    amendment = changed_document(
        "02_amendment_signed.txt",
        (
            (
                "1. Пункт 2.1 договора изложить в следующей редакции: "
                "«Общая стоимость поставки составляет "
                "1 380 000 (один миллион триста восемьдесят тысяч) рублей, "
                "включая НДС. "
                "Указанная сумма — итоговая стоимость договора».",
                "1. Общая стоимость поставки остаётся без изменений.",
            ),
        ),
    )
    result = analyze_documents(
        [sample_document("01_contract.txt"), amendment], as_of=CHECK_DATE
    )
    contract = contract_for(result, "STN-101")

    assert contract.amount.value == Decimal("1200000")
    assert not contract.amount.amended
    assert contract.delivery_date.value == date(2026, 4, 30)
    assert contract.delivery_date.amended
    assert_all_citations_match(result)


def test_invalid_calendar_date_is_not_confirmed_as_a_delivery_term() -> None:
    """Попроси проверку при календарно невозможной дате поставки."""
    document = changed_document("03_contract.txt", (("20.03.2026", "31.02.2026"),))
    result = analyze_documents([document], as_of=CHECK_DATE)
    fact = contract_for(result, "STN-102").delivery_date

    assert fact.value is None
    assert fact.state == "review"
    assert fact.reason


@pytest.mark.parametrize(
    "status", ["не подписан ни одной стороной.", "на согласовании."]
)
def test_unsigned_or_unknown_base_contract_is_not_reported_as_confirmed(
    status: str,
) -> None:
    """Не представляй неподтверждённую базовую редакцию как надёжные условия.

    Args:
        status: статус базового договора без подтверждения подписей.
    """
    document = changed_document(
        "03_contract.txt",
        (("подписан обеими сторонами 10.02.2026.", status),),
    )
    result = analyze_documents([document], as_of=CHECK_DATE)
    contract = contract_for(result, "STN-102")

    assert contract.amount.state != "confirmed"
    assert contract.delivery_date.state != "confirmed"
    assert contract.issues


@pytest.mark.parametrize(
    ("original", "replacement"),
    [
        ("Покупатель: ООО «СеверМет»", "Покупатель: ООО «Другой покупатель»"),
        ("Поставщик: ООО «Вектор Прибор»", "Поставщик: ООО «Другой поставщик»"),
    ],
    ids=["buyer", "supplier"],
)
def test_different_party_in_amendment_requires_review(
    original: str,
    replacement: str,
) -> None:
    """Не применяй соглашение с другим покупателем или поставщиком.

    Args:
        original: сторона из исходного договора и соглашения.
        replacement: противоречащая сторона в подписанном соглашении.
    """
    amendment = changed_document(
        "02_amendment_signed.txt",
        ((original, replacement),),
    )
    result = analyze_documents(
        [sample_document("01_contract.txt"), amendment], as_of=CHECK_DATE
    )
    contract = contract_for(result, "STN-101")

    assert contract.amount.state == "review"
    assert contract.delivery_date.state == "review"
    assert contract.issues
    assert all(related.state != "applied" for related in contract.related_documents)
    assert_all_citations_match(result)


def test_negated_effective_date_does_not_authorize_amendment() -> None:
    """Не превращай отрицание вступления в силу в подтверждённую дату действия."""
    amendment = changed_document(
        "02_amendment_signed.txt",
        (("вступает в силу 01.03.2026", "не вступает в силу 01.03.2026"),),
    )
    result = analyze_documents(
        [sample_document("01_contract.txt"), amendment], as_of=CHECK_DATE
    )
    contract = contract_for(result, "STN-101")

    assert contract.amount.state == "review"
    assert contract.delivery_date.state == "review"
    assert contract.issues
    assert all(related.state != "applied" for related in contract.related_documents)
    assert_all_citations_match(result)
