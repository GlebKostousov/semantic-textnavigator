"""Ограничения и декодирование файлов перед анализом."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from fastapi import UploadFile, status

from app.analysis import InputDocument

from ._errors import NavigatorError

MAX_FILES = 50
MAX_FILE_BYTES = 1_048_576
MAX_TOTAL_BYTES = 10_485_760


@dataclass(frozen=True, slots=True)
class _ReadUpload:
    """Прочитанный документ и размер перед декодированием."""

    document: InputDocument
    size_bytes: int


def _validate_name(filename: str | None) -> str:
    """Оставить имя файла для отображения, не используя его как путь."""
    name = PurePosixPath((filename or "").replace("\\", "/")).name
    if not name.lower().endswith(".txt"):
        raise NavigatorError("Можно загрузить только файлы с расширением .txt.")
    if len(name) > 200:
        raise NavigatorError("Имя файла должно содержать не более 200 символов.")
    return name


def _decode_text(content: bytes, *, filename: str) -> str:
    """Проверить кодировку и не принимать пустой или бинарный файл."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise NavigatorError(
            f"Сохраните «{filename}» в кодировке UTF-8 и загрузите повторно.",
            code="invalid_encoding",
        ) from error
    _validate_text(text, filename=filename)
    return text


def _validate_text(text: str, *, filename: str) -> None:
    """Отделить пустой документ от непохожего на текст содержимого."""
    if not text.strip():
        raise NavigatorError(f"Файл «{filename}» пуст.", code="empty_file")
    if "\x00" in text:
        raise NavigatorError(f"Файл «{filename}» содержит бинарные данные.")


async def _read_upload(upload: UploadFile) -> _ReadUpload:
    """Прочитать один файл с верхней границей размера."""
    name = _validate_name(upload.filename)
    content = await upload.read(MAX_FILE_BYTES + 1)
    if len(content) > MAX_FILE_BYTES:
        raise NavigatorError(
            f"Файл «{name}» больше 1 МиБ.",
            code="file_too_large",
            http_status=status.HTTP_413_CONTENT_TOO_LARGE,
        )
    text = _decode_text(content, filename=name)
    return _ReadUpload(InputDocument(name=name, text=text), len(content))


def _check_batch_size(files: int, size_bytes: int) -> None:
    """Проверить ограничения всего комплекта документов."""
    if not 1 <= files <= MAX_FILES:
        raise NavigatorError("Выберите от 1 до 50 TXT-файлов.", code="file_count")
    if size_bytes > MAX_TOTAL_BYTES:
        raise NavigatorError(
            "Общий размер файлов больше 10 МиБ.",
            code="batch_too_large",
            http_status=status.HTTP_413_CONTENT_TOO_LARGE,
        )


async def read_uploads(uploads: Sequence[UploadFile]) -> list[InputDocument]:
    """Прочитать комплект и закрыть файлы даже при ошибке в одном из них.

    Args:
        uploads: Файлы из multipart-запроса.

    Returns:
        Тексты, готовые для анализа.

    Raises:
        NavigatorError: Файлы не соответствуют ограничениям загрузки.
    """
    try:
        return await _read_batch(uploads)
    finally:
        for upload in uploads:
            await upload.close()


async def _read_batch(uploads: Sequence[UploadFile]) -> list[InputDocument]:
    """Проверять суммарный размер по мере чтения комплекта."""
    _check_batch_size(len(uploads), 0)
    documents: list[InputDocument] = []
    size_bytes = 0
    for upload in uploads:
        item = await _read_upload(upload)
        size_bytes += item.size_bytes
        _check_batch_size(len(uploads), size_bytes)
        documents.append(item.document)
    return documents
