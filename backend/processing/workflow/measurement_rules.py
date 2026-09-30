"""Regras puras de seleção de equipamentos para um bay."""

from typing import Set

from backend.processing.constants import (
    CAIXA_CA, CABANA, CASA_DE_COMANDO, COSTURA,
    MEASUREMENT_CAIXA, MEASUREMENT_COSTURA, MEASUREMENT_NONE, PAINEL,
    SINCRONIZADOR, TOTAL,
)


def selected_equipment(results_data) -> Set[str]:
    selected = set()
    for origin, destination, _ in results_data:
        selected.update((origin, destination))
    return selected


def base_equipment(measurement_type: str) -> Set[str]:
    equipment = {TOTAL, SINCRONIZADOR}
    if measurement_type == MEASUREMENT_COSTURA:
        equipment.add(COSTURA)
    elif measurement_type == MEASUREMENT_CAIXA:
        equipment.add(CAIXA_CA)
    return equipment


def should_process_sheet(sheet_name: str, measurement_type: str,
                         selected: Set[str], sincronizador_enabled: bool) -> bool:
    if sheet_name == SINCRONIZADOR and not sincronizador_enabled:
        return False
    if measurement_type == MEASUREMENT_NONE and sheet_name in (COSTURA, CAIXA_CA):
        return False
    if measurement_type == MEASUREMENT_CAIXA and sheet_name == COSTURA:
        return False
    if measurement_type == MEASUREMENT_COSTURA and sheet_name == CAIXA_CA:
        return False
    allowed = base_equipment(measurement_type)
    return (
        sheet_name in allowed or sheet_name in selected
        or any(sheet_name in item for item in selected)
        or (PAINEL in selected and sheet_name in (CASA_DE_COMANDO, CABANA))
    )
