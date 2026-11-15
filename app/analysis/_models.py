"""Типизированные результаты анализа и проверяемые ссылки на исходный текст."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type DocumentKind = Literal["contract", "amendment", "draft", "letter", "unknown"]
type FactState = Literal["confirmed", "missing", "review"]
type RelationState = Literal[
    "base", "applied", "proposal", "future", "review", "ignored"
]


@dataclass(frozen=True, slots=True)
class InputDocument:
    """Переданный пользователем файл после проверки формата и кодировки."""

    name: str
    text: str


class AnalysisModel(BaseModel):
    """Общий контракт ответов API без неописанных полей."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class Paragraph(AnalysisModel):
    """Абзац с границами в исходной строке; end не включает последний символ."""

    id: int
    text: str
    start: int
    end: int


class Citation(AnalysisModel):
    """Точная цитата и адрес абзаца, который можно открыть в просмотрщике."""

    document_id: str
    filename: str
    paragraph_id: int
    quote: str
    start: int
    end: int


class SourceDocument(AnalysisModel):
    """Исходный текст и его распознанная роль в комплекте документов."""

    id: str
    name: str
    text: str
    kind: DocumentKind
    contract_number: str | None
    status: str
    paragraphs: list[Paragraph]


class Fact[T](AnalysisModel):
    """Значение поля либо явная причина отсутствия подтвержденного значения."""

    value: T | None = None
    state: FactState = "missing"
    citations: list[Citation] = Field(default_factory=list)
    reason: str | None = None
    amended: bool = False


class RelatedDocument(AnalysisModel):
    """Результат проверки применимости документа на выбранную дату."""

    document_id: str
    kind: DocumentKind
    state: RelationState
    explanation: str
    citations: list[Citation] = Field(default_factory=list)


class Proposal(AnalysisModel):
    """Предложенные условия, не заменяющие действующие условия договора."""

    document_id: str
    kind: DocumentKind
    amount: Fact[Decimal]
    delivery_date: Fact[date]
    penalty: Fact[str] = Field(default_factory=lambda: Fact[str]())
    reason: str
    status_citations: list[Citation] = Field(default_factory=list)


class ContractResult(AnalysisModel):
    """Сверенные условия одного договора и связанные с ними документы."""

    number: str
    supplier: str | None
    amount: Fact[Decimal]
    delivery_date: Fact[date]
    penalty: Fact[str]
    related_documents: list[RelatedDocument] = Field(default_factory=list)
    proposals: list[Proposal] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class AnalysisResult(AnalysisModel):
    """Полный результат одного независимого анализа без сохранения файлов."""

    as_of: date
    documents: list[SourceDocument]
    contracts: list[ContractResult]
    warnings: list[str] = Field(default_factory=list)
    unlinked_document_ids: list[str] = Field(default_factory=list)
