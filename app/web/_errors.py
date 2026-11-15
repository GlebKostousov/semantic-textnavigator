"""Безопасные сообщения об ошибках на HTTP-границе."""

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict


class NavigatorError(Exception):
    """Ожидаемая ошибка пользовательского сценария."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_upload",
        http_status: int = status.HTTP_422_UNPROCESSABLE_CONTENT,
    ) -> None:
        self.message = message
        self.code = code
        self.http_status = http_status
        super().__init__(message)


class ErrorDetail(BaseModel):
    """Публичная ошибка без исходного текста документа."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    code: str
    message: str


class ErrorResponse(BaseModel):
    """Единый формат ожидаемых ошибок API."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    error: ErrorDetail


async def handle_navigator_error(
    _request: Request, error: NavigatorError
) -> JSONResponse:
    """Преобразовать прикладную ошибку в понятный ответ API."""
    payload = ErrorResponse(error=ErrorDetail(code=error.code, message=error.message))
    return JSONResponse(payload.model_dump(), status_code=error.http_status)


async def handle_validation_error(
    _request: Request, _error: RequestValidationError
) -> JSONResponse:
    """Не включать загруженные данные в сообщение об ошибке валидации."""
    payload = ErrorResponse(
        error=ErrorDetail(
            code="invalid_request",
            message="Укажите корректную дату проверки и выберите TXT-файлы.",
        )
    )
    return JSONResponse(
        payload.model_dump(), status_code=status.HTTP_422_UNPROCESSABLE_CONTENT
    )
