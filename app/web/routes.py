"""Загрузка документов и запуск независимого от HTTP анализатора."""

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.analysis import AnalysisResult, InputDocument, analyze_documents

from ._errors import NavigatorError
from ._uploads import read_uploads


class _AnalysisApi:
    """HTTP-операции с явно переданным источником учебных документов."""

    def __init__(self, *, examples_dir: Path) -> None:
        self._examples_dir = examples_dir

    async def analyze(
        self,
        files: Annotated[list[UploadFile], File()],
        as_of: Annotated[date, Form()],
    ) -> AnalysisResult:
        """Проанализировать загруженные тексты на указанную дату."""
        documents = await read_uploads(files)
        return await run_in_threadpool(analyze_documents, documents, as_of=as_of)

    async def demo(self, as_of: Annotated[date, Query()]) -> AnalysisResult:
        """Прочитать учебные TXT и пропустить их через обычный анализатор."""
        documents = await run_in_threadpool(self._read_examples)
        return await run_in_threadpool(analyze_documents, documents, as_of=as_of)

    def _read_examples(self) -> list[InputDocument]:
        """Загружать примеры с диска, не хранить заранее рассчитанные ответы."""
        paths = sorted(self._examples_dir.glob("*.txt"))
        if not paths:
            raise NavigatorError(
                "Учебный комплект не найден. Загрузите файлы через интерфейс.",
                code="examples_unavailable",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return [_read_example(path) for path in paths]


def _read_example(path: Path) -> InputDocument:
    """Перевести ошибку чтения учебного комплекта в безопасное сообщение."""
    try:
        return InputDocument(name=path.name, text=path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError) as error:
        raise NavigatorError(
            "Не удалось прочитать учебный комплект. Загрузите свои TXT-файлы.",
            code="examples_unavailable",
            http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from error


def build_router(*, examples_dir: Path) -> APIRouter:
    """Собрать маршруты без глобального состояния пользовательских документов."""
    api = _AnalysisApi(examples_dir=examples_dir)
    router = APIRouter(prefix="/api")
    router.add_api_route(
        "/analyze", api.analyze, methods=["POST"], response_model=AnalysisResult
    )
    router.add_api_route(
        "/demo", api.demo, methods=["GET"], response_model=AnalysisResult
    )
    return router
