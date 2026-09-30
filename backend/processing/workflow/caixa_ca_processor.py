"""Processamento da aba CAIXA CA (caixa de distribuição)."""

from typing import List, Optional, Set, Tuple

from openpyxl.worksheet.worksheet import Worksheet

from backend.core.logging.logger import get_logger
from backend.processing.constants import (
    CAIXA_DISTRIBUICAO_CA,
    SECCIONADORA,
    Connection,
    DistanceMap,
)
from backend.processing.workflow.measurement_rules import selected_equipment
from backend.processing.workbook.distance_manager import DistanceManager
from backend.processing.workbook.sheet_builder import finalize_sheet

log = get_logger(__name__)


def _seccionadora_count(selected_equipment: Set[str]) -> int:
    """Maior número de seccionadora presente nos equipamentos selecionados."""
    count = 0
    for equip in selected_equipment:
        if f"{SECCIONADORA}-" in equip:
            try:
                num = int(equip.split("-")[1])
                count = max(count, num)
            except (ValueError, IndexError):
                pass
    return count


def process_caixa_seccionadora_row(processor, template_sheet: Worksheet, new_sheet: Worksheet, row: int,
                                   has_asterisk: bool, selected: Set[str], distances_dict: DistanceMap,
                                   seccionadora_count: int, valid_row: int, has_valid_data: bool,
                                   bay_name: Optional[str]) -> Tuple[int, bool]:
    """Processa uma linha CAIXA DE DISTRIBUIÇÃO CA -> SECCIONADORA-N (todas as N)."""
    original_b_value = template_sheet[f'B{row}'].value
    description = template_sheet[f'C{row}'].value

    for secc_num in range(1, seccionadora_count + 1):
        seccionadora_name = f"{SECCIONADORA}-{secc_num}"

        if seccionadora_name not in selected:
            continue

        distance_value = DistanceManager.resolve_distance(distances_dict, CAIXA_DISTRIBUICAO_CA, seccionadora_name)

        if distance_value is None:
            template_distance = template_sheet[f'F{row}'].value
            if template_distance is not None and isinstance(template_distance, (int, float)) and template_distance > 0:
                distance_value = template_distance
                log.debug("Usando distância do template para CAIXA DE DISTRIBUIÇÃO CA -> %s: %s", seccionadora_name, distance_value)
            else:
                log.warning("Aviso: Distância não encontrada para CAIXA DE DISTRIBUIÇÃO CA -> %s", seccionadora_name)
                continue

        new_b_values = processor.cable_resolver.process_cable_value(
            original_b_value, has_asterisk, description, new_sheet.title,
            CAIXA_DISTRIBUICAO_CA, seccionadora_name, bay_name
        )
        valid_row, has_valid_data = processor._write_formation_rows(
            new_sheet, new_b_values, template_sheet[f'A{row}'].value, description,
            CAIXA_DISTRIBUICAO_CA, seccionadora_name, distance_value, valid_row, has_valid_data
        )

    return valid_row, has_valid_data


def process_caixa_equipment_row(processor, template_sheet: Worksheet, new_sheet: Worksheet, row: int,
                                has_asterisk: bool, distances_dict: DistanceMap, cell_e: str,
                                valid_row: int, has_valid_data: bool, bay_name: Optional[str]) -> Tuple[int, bool]:
    """Processa uma linha CAIXA DE DISTRIBUIÇÃO CA -> equipamento."""
    original_b_value = template_sheet[f'B{row}'].value
    description = template_sheet[f'C{row}'].value

    distance_value = DistanceManager.resolve_distance(distances_dict, CAIXA_DISTRIBUICAO_CA, cell_e)

    if distance_value is None:
        template_distance = template_sheet[f'F{row}'].value
        if template_distance is not None and isinstance(template_distance, (int, float)) and template_distance > 0:
            distance_value = template_distance
            log.debug("Usando distância do template para CAIXA DE DISTRIBUIÇÃO CA -> %s: %s", cell_e, distance_value)
        else:
            log.warning("Aviso: Distância não encontrada para CAIXA DE DISTRIBUIÇÃO CA -> %s", cell_e)
            return valid_row, has_valid_data

    new_b_values = processor.cable_resolver.process_cable_value(
        original_b_value, has_asterisk, description, new_sheet.title,
        CAIXA_DISTRIBUICAO_CA, cell_e, bay_name
    )
    return processor._write_formation_rows(
        new_sheet, new_b_values, template_sheet[f'A{row}'].value, description,
        CAIXA_DISTRIBUICAO_CA, cell_e, distance_value, valid_row, has_valid_data
    )


def process_caixa_ca_sheet(processor, template_sheet: Worksheet, new_sheet: Worksheet, results_data: List[Connection],
                           secc_number: Optional[int] = None, merging_unit_enabled: bool = False,
                           bay_name: Optional[str] = None) -> bool:
    processor.sheet_builder.prepare_sheet(template_sheet, new_sheet)

    selected = selected_equipment(results_data)
    distances_dict = DistanceManager.build_distance_dict(results_data)

    count = _seccionadora_count(selected)

    valid_row = 2
    has_valid_data = False

    for row in range(2, template_sheet.max_row + 1):
        has_asterisk = template_sheet[f'H{row}'].value == '*'

        g_value = template_sheet[f'G{row}'].value
        if g_value and str(g_value).strip() == '*':
            continue

        cell_d = template_sheet[f'D{row}'].value
        cell_e = template_sheet[f'E{row}'].value

        if cell_d != CAIXA_DISTRIBUICAO_CA:
            continue

        if cell_e == SECCIONADORA:
            if count > 0:
                valid_row, has_valid_data = process_caixa_seccionadora_row(
                    processor, template_sheet, new_sheet, row, has_asterisk, selected,
                    distances_dict, count, valid_row, has_valid_data, bay_name
                )
        elif cell_e in selected:
            valid_row, has_valid_data = process_caixa_equipment_row(
                processor, template_sheet, new_sheet, row, has_asterisk, distances_dict,
                cell_e, valid_row, has_valid_data, bay_name
            )

    return finalize_sheet(new_sheet, valid_row, has_valid_data)
