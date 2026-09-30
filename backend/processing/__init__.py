"""Processamento de planilhas Excel (backend headless, sem UI)."""

from backend.processing.excel_processor import ExcelProcessor
from backend.processing.templates.template_utils import get_template_connections

__all__ = [
    "ExcelProcessor",
    "get_template_connections",
]