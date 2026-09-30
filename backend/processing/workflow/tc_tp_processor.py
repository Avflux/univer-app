"""Serviço de adaptação para processamento das abas TC e TP."""

from typing import List, Optional

from openpyxl.worksheet.worksheet import Worksheet

from backend.core.logging.logger import get_logger
from backend.processing.constants import (
    CAIXA_TC,
    CAIXA_TP,
    MERGING_UNIT,
    PAINEL,
    TC,
    WINDING_MAX_PHASES,
    WINDING_PREFIX_TC,
    WINDING_PREFIX_TP,
    Connection,
)
from backend.processing.workbook.distance_manager import DistanceManager
from backend.processing.workbook.sheet_builder import finalize_sheet

log = get_logger(__name__)


import re


def parse_winding_number(cell_d, winding_prefix):
    """Extrai o número do enrolamento (1-6) do nome do ponto, ex.: TC-1S-ØA -> 1."""
    if not cell_d:
        return None
    if not any(f"-{i}{winding_prefix}-" in cell_d for i in range(1, WINDING_MAX_PHASES + 1)):
        return None
    try:
        for part in cell_d.split("-"):
            if part.endswith(winding_prefix):
                return int(part[0])
    except Exception:
        pass
    return None


def parse_description_winding(cell_c: object, winding_prefix: str) -> Optional[int]:
    """Extrai o requisito de enrolamento da descrição (cell_c).

    - Para '(1a/2a)' -> 1 (requer ao menos 1 fase).
    - Para '(3a)', '(1S)', etc. -> número da fase/enrolamento.
    - Para descrições genéricas sem sufixo de enrolamento -> None (sempre válido).
    """
    if not cell_c:
        return None
    c_str = str(cell_c)
    m_range = re.search(rf'\((\d+){winding_prefix}/(\d+){winding_prefix}\)', c_str, re.IGNORECASE)
    if m_range:
        return int(m_range.group(1))
    m_single = re.search(rf'\((\d+){winding_prefix}\)', c_str, re.IGNORECASE)
    if m_single:
        return int(m_single.group(1))
    return None


def process_tc_tp_sheet(processor, template_sheet: Worksheet, new_sheet: Worksheet,
                        results_data: List[Connection], equipment_type: str, num_phases: int,
                        merging_unit_enabled: bool = False, bay_name: Optional[str] = None) -> bool:
    """Processa as abas TC e TP conforme o número de fases/enrolamentos."""
    if num_phases < 1 or num_phases > WINDING_MAX_PHASES:
        log.warning("Número de fases inválido para %s: %s", equipment_type, num_phases)
        return False

    if equipment_type == TC:
        winding_prefix = WINDING_PREFIX_TC
        caixa_name = CAIXA_TC
    else:
        winding_prefix = WINDING_PREFIX_TP
        caixa_name = CAIXA_TP

    processor.sheet_builder.prepare_sheet(template_sheet, new_sheet)

    distances = DistanceManager.build_distance_dict(results_data)
    for origin, dest, distance in results_data:
        if caixa_name in (origin, dest):
            distances[(caixa_name, origin if dest == caixa_name else dest)] = distance

    caixa_painel_distance = distances.get((caixa_name, PAINEL), None)

    valid_row = 2
    has_valid_data = False

    for row in range(2, template_sheet.max_row + 1):
        cell_a = template_sheet[f'A{row}'].value
        cell_b = template_sheet[f'B{row}'].value
        cell_c = template_sheet[f'C{row}'].value
        cell_d = template_sheet[f'D{row}'].value
        cell_e = template_sheet[f'E{row}'].value
        template_distance = template_sheet[f'F{row}'].value
        has_asterisk = template_sheet[f'H{row}'].value == '*'

        winding_match = cell_d is not None and any(
            f"-{i}{winding_prefix}-" in cell_d for i in range(1, WINDING_MAX_PHASES + 1)
        )
        if winding_match:
            winding_number = parse_winding_number(cell_d, winding_prefix)

            if winding_number is not None and winding_number <= num_phases:
                if template_distance is not None and isinstance(template_distance, (int, float)) and template_distance > 0:
                    distance_value = template_distance
                else:
                    distance_value = distances.get((cell_d, cell_e))
                    if distance_value is None:
                        distance_value = distances.get((cell_e, cell_d))
                    if distance_value is None:
                        continue

                new_b_values = processor.cable_resolver.resolve_tc_tp_cable_value(
                    cell_b, cell_c, cell_d, cell_e, new_sheet.title, has_asterisk, bay_name
                )
                valid_row, has_valid_data = processor._write_formation_rows(
                    new_sheet, new_b_values, cell_a, cell_c, cell_d, cell_e, distance_value, valid_row, has_valid_data
                )

        elif cell_d == caixa_name and cell_e == PAINEL:
            req_winding = parse_description_winding(cell_c, winding_prefix)
            if req_winding is not None and req_winding > num_phases:
                continue

            redirected_destination = cell_e
            merging_unit_selected = merging_unit_enabled and any(
                MERGING_UNIT in (origin, dest) for origin, dest, _ in results_data
            )

            is_shielded = '(' in str(cell_b) or '[' in str(cell_b)
            if is_shielded and merging_unit_selected:
                redirected_destination = MERGING_UNIT

            if redirected_destination == MERGING_UNIT:
                distance_value = distances.get((caixa_name, MERGING_UNIT))
            else:
                distance_value = caixa_painel_distance

            if distance_value is None:
                if template_distance is not None and isinstance(template_distance, (int, float)) and template_distance > 0:
                    distance_value = template_distance
                else:
                    continue

            new_b_values = processor.cable_resolver.resolve_tc_tp_cable_value(
                cell_b, cell_c, cell_d, redirected_destination, new_sheet.title, has_asterisk, bay_name
            )
            valid_row, has_valid_data = processor._write_formation_rows(
                new_sheet, new_b_values, cell_a, cell_c, cell_d, redirected_destination, distance_value, valid_row, has_valid_data
            )

        elif ((cell_c is not None and "Sinalização" in str(cell_c)) or
              (not any(f"-{i}{winding_prefix}-" in str(cell_d or "") for i in range(1, WINDING_MAX_PHASES + 1)))):
            req_winding = parse_description_winding(cell_c, winding_prefix)
            if req_winding is not None and req_winding > num_phases:
                continue

            if cell_d == caixa_name and cell_e == PAINEL and caixa_painel_distance is not None:
                distance_value = caixa_painel_distance
            elif template_distance is not None and isinstance(template_distance, (int, float)) and template_distance > 0:
                distance_value = template_distance
            else:
                distance_value = distances.get((cell_d, cell_e))
                if distance_value is None:
                    distance_value = distances.get((cell_e, cell_d))
                if distance_value is None:
                    continue

            new_b_values = processor.cable_resolver.process_cable_value(
                cell_b, has_asterisk, cell_c, new_sheet.title, cell_d, cell_e, bay_name
            )
            valid_row, has_valid_data = processor._write_formation_rows(
                new_sheet, new_b_values, cell_a, cell_c, cell_d, cell_e, distance_value, valid_row, has_valid_data
            )

    return finalize_sheet(new_sheet, valid_row, has_valid_data)


def process_tc_tp(processor, template_sheet, new_sheet, results_data,
                  equipment_type, phases, merging_unit_enabled, bay_name):
    """Processa uma aba TC/TP através do writer compatível atual."""
    return processor._process_tc_tp_sheet(
        template_sheet, new_sheet, results_data, equipment_type, phases,
        merging_unit_enabled, bay_name,
    )
