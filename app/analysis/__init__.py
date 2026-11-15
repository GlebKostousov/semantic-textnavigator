"""Извлечение условий и проверка применимости связанных документов."""

from ._models import AnalysisResult, InputDocument
from .main import analyze_documents

__all__ = ["AnalysisResult", "InputDocument", "analyze_documents"]
