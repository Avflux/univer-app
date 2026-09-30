"""Serviço de adaptação para processamento das abas Seccionadora."""

from openpyxl.worksheet.worksheet import Worksheet

from backend.processing.constants import DISJUNTOR, SECCIONADORA


def has_other_seccionadora_connections(template_sheet: Worksheet) -> bool:
    """Indica se a aba SECCIONADORA possui conexões além de SECCIONADORA->SECCIONADORA."""
    for row in range(2, template_sheet.max_row + 1):
        cell_d = template_sheet[f'D{row}'].value
        cell_e = template_sheet[f'E{row}'].value
        if cell_d and cell_e and not (cell_d == SECCIONADORA and cell_e == SECCIONADORA):
            return True
    return False


def resolve_seccionadora_refs(cell_d, cell_e, secc_number, sheet_title):
    """Converte referências 'SECCIONADORA' de uma linha para o número do bay."""
    if sheet_title == DISJUNTOR:
        if cell_d == SECCIONADORA:
            cell_d = f"{SECCIONADORA}-1"
        if cell_e == SECCIONADORA:
            cell_e = f"{SECCIONADORA}-1"
    elif secc_number is not None:
        cell_d = cell_d.replace(SECCIONADORA, f"{SECCIONADORA}-{secc_number}")
        cell_e = cell_e.replace(SECCIONADORA, f"{SECCIONADORA}-{secc_number}")
    return cell_d, cell_e


def process_seccionadora(processor, template_sheet, new_sheet, results_data,
                          index, measurement_type, merging_unit_enabled, bay_name):
    """Processa uma instância de Seccionadora pelo writer compatível."""
    return processor._process_sheet(
        template_sheet, new_sheet, results_data, index, measurement_type,
        merging_unit_enabled, bay_name,
    )
