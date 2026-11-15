"""Интеграционные проверки пользовательской HTTP-границы."""

from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analysis import AnalysisResult
from app.app_factory import create_app
from app.web._errors import ErrorResponse
from app.web._uploads import MAX_FILE_BYTES

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "documents"
AS_OF = "2026-03-10"


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Создать независимое приложение без пользовательского хранилища."""
    with TestClient(create_app()) as test_client:
        yield test_client


def _files() -> list[tuple[str, tuple[str, bytes, str]]]:
    """Прочитать комплект, который проверяющий может загрузить вручную."""
    return [
        ("files", (path.name, path.read_bytes(), "text/plain"))
        for path in sorted(EXAMPLES.glob("*.txt"))
    ]


def test_uploaded_sources_and_demo_match(client: TestClient) -> None:
    """Демо и ручная загрузка используют одинаковый разбор реальных файлов."""
    uploaded = client.post("/api/analyze", data={"as_of": AS_OF}, files=_files())
    demo = client.get("/api/demo", params={"as_of": AS_OF})
    assert uploaded.status_code == 200
    assert demo.status_code == 200
    actual = AnalysisResult.model_validate(uploaded.json())
    expected = AnalysisResult.model_validate(demo.json())
    assert actual == expected
    assert actual.as_of == date(2026, 3, 10)
    assert len(actual.documents) == 6
    assert len(actual.contracts) == 3


def test_requests_do_not_share_uploaded_documents(client: TestClient) -> None:
    """Предыдущая загрузка не влияет на анализ другого комплекта."""
    client.post("/api/analyze", data={"as_of": AS_OF}, files=_files())
    response = client.post("/api/analyze", data={"as_of": AS_OF}, files=[_files()[0]])
    result = AnalysisResult.model_validate(response.json())
    assert len(result.documents) == 1
    assert len(result.contracts) == 1
    assert result.contracts[0].delivery_date.value == date(2026, 4, 15)


@pytest.mark.parametrize(
    ("name", "content", "expected_code"),
    [
        ("contract.pdf", b"plain text", "invalid_upload"),
        ("empty.txt", b" \r\n\t", "empty_file"),
        ("binary.txt", b"a\x00b", "invalid_upload"),
        ("broken.txt", b"\xff\xff\xfe", "invalid_encoding"),
    ],
)
def test_invalid_uploads_are_explained(
    client: TestClient, name: str, content: bytes, expected_code: str
) -> None:
    """Ошибки формата не превращаются в успешный пустой результат."""
    response = client.post(
        "/api/analyze",
        data={"as_of": AS_OF},
        files=[("files", (name, content, "text/plain"))],
    )
    assert response.status_code == 422
    error = ErrorResponse.model_validate(response.json())
    assert error.error.code == expected_code
    assert error.error.message


def test_large_file_is_rejected_before_analysis(client: TestClient) -> None:
    """Не читать и не анализировать файл за пределами лимита 1 МиБ."""
    response = client.post(
        "/api/analyze",
        data={"as_of": AS_OF},
        files=[("files", ("large.txt", b"a" * (MAX_FILE_BYTES + 1), "text/plain"))],
    )
    assert response.status_code == 413
    assert ErrorResponse.model_validate(response.json()).error.code == "file_too_large"


def test_too_many_files_are_rejected(client: TestClient) -> None:
    """Лимит числа документов действует независимо от их размера."""
    response = client.post(
        "/api/analyze",
        data={"as_of": AS_OF},
        files=[
            ("files", (f"{index}.txt", b"text", "text/plain")) for index in range(51)
        ],
    )
    assert response.status_code == 422
    assert ErrorResponse.model_validate(response.json()).error.code == "file_count"


def test_total_upload_limit_is_enforced(client: TestClient) -> None:
    """Много допустимых файлов не обходят общий лимит комплекта."""
    response = client.post(
        "/api/analyze",
        data={"as_of": AS_OF},
        files=[
            ("files", (f"{index}.txt", b"a" * MAX_FILE_BYTES, "text/plain"))
            for index in range(11)
        ],
    )
    assert response.status_code == 413
    assert ErrorResponse.model_validate(response.json()).error.code == "batch_too_large"


@pytest.mark.parametrize("invalid_date", ["2026-02-30", "10.03.2026", "", "tomorrow"])
def test_invalid_date_uses_safe_error_format(
    client: TestClient, invalid_date: str
) -> None:
    """API не возвращает загруженные документы в ошибке даты."""
    response = client.post("/api/analyze", data={"as_of": invalid_date}, files=_files())
    assert response.status_code == 422
    error = ErrorResponse.model_validate(response.json())
    assert error.error.code == "invalid_request"
    assert "СеверМет" not in response.text


def test_utf8_bom_and_uppercase_extension_are_supported(client: TestClient) -> None:
    """Обычный TXT из Windows не требует ручного удаления BOM."""
    content = b"\xef\xbb\xbf" + (EXAMPLES / "01_contract.txt").read_bytes()
    response = client.post(
        "/api/analyze",
        data={"as_of": AS_OF},
        files=[("files", ("CONTRACT.TXT", content, "text/plain"))],
    )
    assert response.status_code == 200
    result = AnalysisResult.model_validate(response.json())
    assert result.documents[0].name == "CONTRACT.TXT"
    assert result.contracts[0].number == "STN-101"


def test_uploaded_name_is_not_used_as_filesystem_path(client: TestClient) -> None:
    """Имя, присланное клиентом, остаётся только безопасной подписью источника."""
    response = client.post(
        "/api/analyze",
        data={"as_of": AS_OF},
        files=[("files", ("../../notice.txt", "Обычный текст".encode(), "text/plain"))],
    )
    assert response.status_code == 200
    assert (
        AnalysisResult.model_validate(response.json()).documents[0].name == "notice.txt"
    )


def test_missing_demo_files_have_actionable_error(tmp_path: Path) -> None:
    """Отсутствие учебного комплекта не скрывается за пустой таблицей."""
    with TestClient(create_app(examples_dir=tmp_path)) as isolated:
        response = isolated.get("/api/demo", params={"as_of": AS_OF})
    assert response.status_code == 503
    error = ErrorResponse.model_validate(response.json())
    assert error.error.code == "examples_unavailable"


def test_interface_is_served_with_local_assets(client: TestClient) -> None:
    """Для открытия интерфейса не требуется отдельный dev-сервер."""
    response = client.get("/")
    assert response.status_code == 200
    assert "TextNavigator" in response.text
    assert client.get("/static/app.js").status_code == 200


def test_openapi_describes_real_file_upload(client: TestClient) -> None:
    """API публикует воспроизводимый контракт с multipart-загрузкой."""
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    assert "multipart/form-data" in response.text
    assert "/api/analyze" in response.text


def test_security_headers_are_present(client: TestClient) -> None:
    """Ответы содержат строгие заголовки защиты от атак."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
