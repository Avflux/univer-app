"""Formatação das seções de cabos para a aba TOTAL GERAL."""

from typing import Dict

from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.styles.numbers import FORMAT_NUMBER_00
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


SHIELD_FILL_PATTERN = "solid"
TITLE_FONT = Font(bold=True, size=12)
HEADER_FONT = Font(bold=True)
EVEN_ROW_COLOR = "F2F2F2"
ODD_ROW_COLOR = "FFFFFF"


def standardize_formation(cable_type: str) -> str:
    """Converte [x] -> (x) para normalizar formações com blindagem."""
    if '[' in cable_type and ']' in cable_type:
        content = cable_type[cable_type.index('[') + 1:cable_type.index(']')]
        return f"({content})"
    return cable_type


def is_shielded(cable_type: str) -> bool:
    """Retorna True se a formação contém [..] ou (..)."""
    return '[' in cable_type or '(' in cable_type


def _header_cell(sheet: Worksheet, row: int, column: int, header_text: str,
                  fill, thin_border, center_alignment) -> None:
    cell = sheet.cell(row=row, column=column)
    cell.value = header_text
    cell.font = HEADER_FONT
    cell.fill = fill
    cell.border = thin_border
    cell.alignment = center_alignment


def write_cable_section(sheet: Worksheet, title: str, cables_dict: Dict, start_row: int,
                        title_fill, header_fill, thin_border, center_alignment) -> int:
    """Escreve seção de cabos (título + cabeçalho + linhas) em A-C.

    Returns next free row.
    """
    row = start_row
    title_cell = sheet.cell(row=row, column=1)
    title_cell.value = title
    title_cell.font = TITLE_FONT
    title_cell.fill = title_fill
    sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
    title_cell.alignment = center_alignment
    for col in ('A', 'B', 'C'):
        sheet[f'{col}{row}'].border = thin_border
    row += 1

    for col_idx, header_text in enumerate(["Formação", "Distância Total (m)", "Bays"], start=1):
        _header_cell(sheet, row, col_idx, header_text, header_fill, thin_border, center_alignment)
    row += 1

    for i, (normalized_type, data) in enumerate(sorted(cables_dict.items()), 1):
        standardized_types = {standardize_formation(t) for t in data['original_types']}
        cable_description = " / ".join(sorted(set(standardized_types)))
        sheet[f'A{row}'].value = cable_description
        sheet[f'B{row}'].value = data['total']
        sheet[f'C{row}'].value = ", ".join(sorted(data['bays']))
        fill_color = ODD_ROW_COLOR if i % 2 == 1 else EVEN_ROW_COLOR
        fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type=SHIELD_FILL_PATTERN)
        for col in ('A', 'B', 'C'):
            cell = sheet[f'{col}{row}']
            cell.fill = fill
            cell.border = thin_border
            cell.alignment = Alignment(
                horizontal='center' if col != 'C' else 'left',
                vertical='center', wrap_text=True,
            )
        sheet[f'B{row}'].number_format = FORMAT_NUMBER_00
        row += 1
    return row + 1


def write_adjusted_section(sheet: Worksheet, title: str, cables_dict: Dict, start_row: int,
                           title_fill, header_fill, thin_border, center_alignment) -> int:
    """Escreve seção ajustada (+10%) em E-F. Returns next free row."""
    row = start_row
    title_cell = sheet.cell(row=row, column=5)
    title_cell.value = title
    title_cell.font = TITLE_FONT
    title_cell.fill = title_fill
    sheet.merge_cells(start_row=row, start_column=5, end_row=row, end_column=6)
    title_cell.alignment = center_alignment
    for col in ('E', 'F'):
        sheet[f'{col}{row}'].border = thin_border
    row += 1

    for col_idx, header_text in zip([5, 6], ["Formação", "Distância Total (m)"]):
        _header_cell(sheet, row, col_idx, header_text, header_fill, thin_border, center_alignment)
    row += 1

    for i, (cable_type, data) in enumerate(sorted(cables_dict.items()), 1):
        original_type = next(iter(data['original_types']))
        distancia_ajustada = round(data['total'] * 1.1)
        sheet[f'E{row}'] = original_type
        sheet[f'F{row}'] = distancia_ajustada
        fill_color = ODD_ROW_COLOR if i % 2 == 1 else EVEN_ROW_COLOR
        fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type=SHIELD_FILL_PATTERN)
        for col in ('E', 'F'):
            cell = sheet[f'{col}{row}']
            cell.fill = fill
            cell.border = thin_border
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        sheet[f'F{row}'].number_format = FORMAT_NUMBER_00
        row += 1
    return row


def auto_fit_columns(sheet: Worksheet, columns: tuple, min_width: int = 15) -> None:
    """Ajusta largura automática das colunas informadas."""
    for col in columns:
        max_length = 0
        for cell in sheet[col]:
            try:
                if cell.value is not None and len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except Exception:
                pass
        sheet.column_dimensions[get_column_letter(col)].width = max(max_length + 2, min_width)
