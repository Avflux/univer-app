"""Processamento genérico de abas e despacho para os processadores especiais."""

from typing import List, Optional

from openpyxl.worksheet.worksheet import Worksheet

from backend.core.logging.logger import get_logger
from backend.processing.constants import (
    CAIXA_CA,
    COSTURA,
    DISJUNTOR,
    MEASUREMENT_CAIXA,
    MEASUREMENT_COSTURA,
    MERGING_UNIT,
    SECCIONADORA,
    Connection,
)
from backend.processing.workflow.caixa_ca_processor import process_caixa_ca_sheet
from backend.processing.workflow.costura_processor import process_costura_sheet
from backend.processing.workflow.measurement_rules import selected_equipment
from backend.processing.workflow.seccionadora_processor import resolve_seccionadora_refs
from backend.processing.workflow.sheet_routing import redirect_merging_unit
from backend.processing.workbook.distance_manager import DistanceManager
from backend.processing.workbook.sheet_builder import finalize_sheet

log = get_logger(__name__)


def process_sheet(processor, template_sheet: Worksheet, new_sheet: Worksheet, results_data: List[Connection],
                  secc_number: Optional[int] = None, measurement_type: str = MEASUREMENT_COSTURA,
                  merging_unit_enabled: bool = False, bay_name: Optional[str] = None) -> bool:
    if new_sheet.title == COSTURA and measurement_type == MEASUREMENT_COSTURA:
        return process_costura_sheet(processor, template_sheet, new_sheet, results_data, secc_number, merging_unit_enabled, bay_name)

    if new_sheet.title == CAIXA_CA and measurement_type == MEASUREMENT_CAIXA:
        return process_caixa_ca_sheet(processor, template_sheet, new_sheet, results_data, secc_number, merging_unit_enabled, bay_name)

    processor.sheet_builder.prepare_sheet(template_sheet, new_sheet)

    selected = selected_equipment(results_data)

    valid_row = 2
    has_valid_data = False

    use_merging_unit = merging_unit_enabled and MERGING_UNIT in selected and new_sheet.title != MERGING_UNIT

    for row in range(2, template_sheet.max_row + 1):
        has_asterisk = template_sheet[f'H{row}'].value == '*'

        if measurement_type == MEASUREMENT_CAIXA:
            g_value = template_sheet[f'G{row}'].value
            if g_value and str(g_value).strip() == '*':
                continue

        cell_d = template_sheet[f'D{row}'].value
        cell_e = template_sheet[f'E{row}'].value

        template_distance = template_sheet[f'F{row}'].value

        equipment_selected = bool((cell_d and cell_d in selected) or (cell_e and cell_e in selected))

        if template_distance is not None and isinstance(template_distance, (int, float)) and template_distance > 0 and equipment_selected:
            use_predefined_distance = True
            distance_value = template_distance
        else:
            use_predefined_distance = False
            distance_value = None

        if (not cell_d or not cell_e) and not use_predefined_distance:
            continue

        if (secc_number is not None and
                cell_d == SECCIONADORA and
                cell_e == SECCIONADORA):

            next_secc = secc_number + 1
            current_secc = f"{SECCIONADORA}-{secc_number}"
            next_secc_name = f"{SECCIONADORA}-{next_secc}"

            if not use_predefined_distance:
                distance_value = DistanceManager.find_distance(results_data, current_secc, next_secc_name)
                if distance_value is None:
                    continue
            else:
                distance_value = template_distance

            original_b_value = template_sheet[f'B{row}'].value
            description = template_sheet[f'C{row}'].value

            new_b_values = processor.cable_resolver.process_cable_value(
                original_b_value,
                has_asterisk,
                description,
                new_sheet.title,
                current_secc,
                next_secc_name,
                bay_name
            )
            valid_row, has_valid_data = processor._write_formation_rows(
                new_sheet, new_b_values, template_sheet[f'A{row}'].value, description,
                current_secc, next_secc_name, distance_value, valid_row, has_valid_data
            )
            continue

        cell_d, cell_e = resolve_seccionadora_refs(cell_d, cell_e, secc_number, new_sheet.title)
        cell_d, cell_e = redirect_merging_unit(cell_d, cell_e, template_sheet[f'B{row}'].value, new_sheet.title, use_merging_unit)

        # Itens com destino DISJUNTOR pertencem apenas às abas SECCIONADORA-1
        # e SECCIONADORA-2. A partir da SECCIONADORA-3 esses cabos não devem
        # ser duplicados (via de mão única: já foram lançados nas primeiras).
        if secc_number is not None and secc_number > 2 and DISJUNTOR in (cell_d, cell_e):
            continue

        if not use_predefined_distance:
            distance_value = DistanceManager.find_distance(results_data, cell_d, cell_e)
            if distance_value is None:
                continue

        original_b_value = template_sheet[f'B{row}'].value
        description = template_sheet[f'C{row}'].value

        new_b_values = processor.cable_resolver.process_cable_value(
            original_b_value, has_asterisk, description, new_sheet.title, cell_d, cell_e, bay_name
        )
        valid_row, has_valid_data = processor._write_formation_rows(
            new_sheet, new_b_values, template_sheet[f'A{row}'].value, description,
            cell_d, cell_e, distance_value, valid_row, has_valid_data
        )

    return finalize_sheet(new_sheet, valid_row, has_valid_data)
