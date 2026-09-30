"""Agregação das distâncias por tipo de cabo nas abas de um workbook."""

from typing import Dict

from openpyxl.workbook.workbook import Workbook


def aggregate_cable_totals(workbook: Workbook) -> Dict[str, float]:
    """Soma distâncias por formação (coluna B) em todas as abas, exceto 'TOTAL'.

    Aceita ``workbook`` como objeto worksheet (compatível com
    ``ExcelProcessor._aggregate_cable_totals``).
    """
    totals: Dict[str, float] = {}
    for sheet_name in workbook.sheetnames:
        if sheet_name == "TOTAL":
            continue
        sheet = workbook[sheet_name]
        for row in range(2, sheet.max_row + 1):
            cable_type = sheet[f'B{row}'].value
            distance = sheet[f'F{row}'].value
            if cable_type and distance:
                try:
                    distance = float(str(distance).replace(',', '.'))
                    totals[cable_type] = totals.get(cable_type, 0) + distance
                except (ValueError, TypeError):
                    continue
    return totals
