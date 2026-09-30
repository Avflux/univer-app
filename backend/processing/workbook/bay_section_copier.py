"""Cópia de seções e totais entre planilhas para a aba final do bay."""

from typing import Iterable, Tuple

from openpyxl.styles import Alignment, Font
from openpyxl.styles.numbers import FORMAT_NUMBER_00
from openpyxl.workbook.workbook import Workbook
from openpyxl.worksheet.worksheet import Worksheet


BAY_HEADER_ROWS = 7  # primeiras 7 linhas (1..6) são o cabeçalho do bay
DATA_COLUMN_WIDTHS = {'A': 8, 'B': 40, 'C': 30, 'D': 20, 'E': 20, 'F': 15}


def write_bay_header(bay_sheet: Worksheet, bay: dict, data_columns: Tuple[str, ...], styles: dict) -> None:
    """Preenche cabeçalho do bay (linhas 1..6) com merge nas colunas de dados."""
    fields = [
        f"Bay: {bay['name']}",
        f"Tipo: {bay['type']}",
        f"Tensão: {bay['voltage']}",
        f"Tipo de Medição: {bay['measurement_type']}",
        f"Sincronizador: {'Sim' if bay['sincronizador_enabled'] else 'Não'}",
        f"Merging Unit: {'Sim' if bay.get('merging_unit_enabled', False) else 'Não'}",
    ]
    for row, text in enumerate(fields, start=1):
        bay_sheet[f'A{row}'] = text
        cell = bay_sheet[f'A{row}']
        cell.font = Font(bold=True)
        cell.fill = styles['HEADER_FILL']
        bay_sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(data_columns))
        cell.alignment = Alignment(horizontal='left', vertical='center')


def _set_data_cell(new_cell, cell) -> None:
    """Aplica formatação da célula de dado copiada."""
    if cell.column == 1:
        new_cell.alignment = Alignment(horizontal='center', vertical='center')
    elif cell.column in (2, 3):
        new_cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
    elif cell.column in (4, 5):
        new_cell.alignment = Alignment(horizontal='center', vertical='center')
    elif cell.column == 6:
        new_cell.alignment = Alignment(horizontal='center', vertical='center')
        new_cell.number_format = FORMAT_NUMBER_00


def copy_section(bay_sheet: Worksheet, source: Worksheet, section_name: str,
                 start_row: int, styles: dict, data_columns: Iterable[str]) -> int:
    """Copia ``source`` para ``bay_sheet`` a partir de ``start_row``. Retorna a próxima linha livre."""
    current_row = start_row

    section_title = bay_sheet.cell(row=current_row, column=1)
    section_title.value = section_name
    section_title.font = Font(bold=True, size=12)
    section_title.fill = styles['TITLE_FILL']
    bay_sheet.merge_cells(start_row=current_row, start_column=1,
                          end_row=current_row, end_column=len(list(data_columns)))
    section_title.alignment = styles['CENTER_ALIGNMENT']
    for col in data_columns:
        bay_sheet[f'{col}{current_row}'].border = styles['THIN_BORDER']
    current_row += 1

    for cell in next(source.iter_rows()):
        new_cell = bay_sheet.cell(row=current_row, column=cell.column)
        new_cell.value = cell.value
        new_cell.font = Font(bold=True)
        new_cell.fill = styles['HEADER_FILL']
        new_cell.border = styles['THIN_BORDER']
        new_cell.alignment = styles['CENTER_ALIGNMENT']
    current_row += 1

    start_data_row = current_row
    for row in source.iter_rows(min_row=2):
        for cell in row:
            new_cell = bay_sheet.cell(row=current_row, column=cell.column)
            new_cell.value = cell.value
            _set_data_cell(new_cell, cell)
            new_cell.border = styles['THIN_BORDER']
        current_row += 1

    for row in range(start_data_row, current_row):
        max_height = 0
        for col_idx in range(1, 7):
            cell = bay_sheet.cell(row=row, column=col_idx)
            if cell.value:
                text = str(cell.value)
                lines = text.count('\n') + 1
                height = max(15, lines * 15)
                max_height = max(max_height, height)
        bay_sheet.row_dimensions[row].height = max_height

    for col, width in DATA_COLUMN_WIDTHS.items():
        bay_sheet.column_dimensions[col].width = width

    return current_row + 2


def copy_total(bay_sheet: Worksheet, total_source: Worksheet, styles: dict) -> None:
    """Copia a seção de totais (colunas I/J) do ``total_source`` para ``bay_sheet``."""
    total_title = bay_sheet.cell(row=BAY_HEADER_ROWS + 1, column=9)
    total_title.value = "TOTAIS DO BAY"
    total_title.font = Font(bold=True, size=12)
    total_title.fill = styles['TITLE_FILL']
    bay_sheet.merge_cells(start_row=BAY_HEADER_ROWS + 1, start_column=9,
                          end_row=BAY_HEADER_ROWS + 1, end_column=10)
    total_title.alignment = styles['CENTER_ALIGNMENT']
    for col in ('I', 'J'):
        bay_sheet[f'{col}{BAY_HEADER_ROWS + 1}'].border = styles['THIN_BORDER']

    for col, header in (('I', "Formação"), ('J', "Distância Total (m)")):
        cell = bay_sheet.cell(row=BAY_HEADER_ROWS + 2,
                              column=ord(col) - ord('A') + 1)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = styles['HEADER_FILL']
        cell.border = styles['THIN_BORDER']
        cell.alignment = styles['CENTER_ALIGNMENT']

    current_row = BAY_HEADER_ROWS + 3
    for row in total_source.iter_rows(min_row=2):
        for col_offset, cell in enumerate(row):
            new_cell = bay_sheet.cell(row=current_row, column=9 + col_offset)
            new_cell.value = cell.value
            if col_offset == 0:
                new_cell.alignment = Alignment(horizontal='left', vertical='center', wrap_text=True)
            else:
                new_cell.alignment = styles['CENTER_ALIGNMENT']
                new_cell.number_format = FORMAT_NUMBER_00
            new_cell.border = styles['THIN_BORDER']
        current_row += 1

    bay_sheet.column_dimensions['I'].width = 20
    bay_sheet.column_dimensions['J'].width = 20

    for row in range(BAY_HEADER_ROWS + 3, current_row):
        cell = bay_sheet.cell(row=row, column=9)
        if cell.value:
            text = str(cell.value)
            lines = text.count('\n') + 1
            height = max(15, lines * 15)
            bay_sheet.row_dimensions[row].height = height


def assemble_bay_sheet(final_wb: Workbook, bay_wb: Workbook, bay: dict,
                       total_label: str, styles: dict,
                       data_columns: Tuple[str, ...]) -> None:
    """Cria a aba do bay em ``final_wb`` mesclando todas as seções de ``bay_wb``."""
    bay_sheet = final_wb.create_sheet(title=bay['name'])
    write_bay_header(bay_sheet, bay, data_columns, styles)

    current_row = BAY_HEADER_ROWS + 1
    for sheet_name in bay_wb.sheetnames:
        if sheet_name == total_label:
            continue
        source = bay_wb[sheet_name]
        current_row = copy_section(bay_sheet, source, sheet_name, current_row,
                                   styles, data_columns)

    if total_label in bay_wb.sheetnames:
        copy_total(bay_sheet, bay_wb[total_label], styles)
