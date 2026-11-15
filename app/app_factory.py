"""Сборка локального приложения и его HTTP-границ."""

from pathlib import Path

from fastapi import FastAPI
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
    app.exception_handler(NavigatorError)(handle_navigator_error)
    app.exception_handler(RequestValidationError)(handle_validation_error)
    app.include_router(
        build_router(examples_dir=examples_dir or app_dir.parent / "examples/documents")
    )
    app.mount("/static", StaticFiles(directory=app_dir / "static"), name="static")
    app.mount("/", StaticFiles(directory=app_dir / "static", html=True), name="ui")
    return app
