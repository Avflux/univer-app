"""Utilitários mínimos para criação e finalização de abas a partir de templates."""

from typing import Callable

from openpyxl.worksheet.worksheet import Worksheet

from backend.processing.workbook.sheet_styles import apply_styles


def finalize_sheet(new_sheet: Worksheet, valid_row: int, has_valid_data: bool) -> bool:
    """Remove linhas vazias restantes, aplica estilos e reporta se houve dados."""
    if not has_valid_data:
        return False
    if valid_row <= new_sheet.max_row:
        new_sheet.delete_rows(valid_row, new_sheet.max_row - valid_row + 1)
    apply_styles(new_sheet)
    return True


class SheetBuilder:
    """Copia cabeçalhos de uma aba-template para uma aba nova."""

    def __init__(self, copy_headers: Callable[[Worksheet, Worksheet], None]):
        self._copy_headers = copy_headers

    def prepare_sheet(self, template_sheet: Worksheet, new_sheet: Worksheet) -> Worksheet:
        self._copy_headers(template_sheet, new_sheet)
        return new_sheet
