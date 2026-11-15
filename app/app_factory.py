"""Сборка локального приложения и его HTTP-границ."""

from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from app.web._errors import (
    NavigatorError,
    handle_navigator_error,
    handle_validation_error,
)
from app.web.routes import build_router


def create_app(*, examples_dir: Path | None = None) -> FastAPI:
    """Собрать API и интерфейс, не создавая хранилища пользовательских данных.

    Args:
        examples_dir: Источник учебных TXT; подменяется в интеграционных тестах.

    Returns:
        Приложение для запуска Uvicorn или тестового клиента.
    """
    app_dir = Path(__file__).resolve().parent
    app = FastAPI(
        title="Semantic TextNavigator",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.middleware("http")
    async def add_security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Применить строгие заголовки безопасности ко всем ответам."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), camera=(), microphone=(), payment=()"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "img-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        return response

    app.exception_handler(NavigatorError)(handle_navigator_error)
    app.exception_handler(RequestValidationError)(handle_validation_error)
    app.include_router(
        build_router(examples_dir=examples_dir or app_dir.parent / "examples/documents")
    )
    app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
    app.mount("/", StaticFiles(directory=app_dir / "static", html=True), name="ui")
    return app
