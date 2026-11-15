"""Запуск приложения на локальном интерфейсе."""

import uvicorn


def main() -> None:
    """Запустить сервер и завершить его по Ctrl+C."""
    uvicorn.run(
        "app.app_factory:create_app",
        factory=True,
        host="127.0.0.1",
        port=8000,
        access_log=False,
    )


if __name__ == "__main__":
    main()
