"""Orquestração do processamento de vários bays."""

from typing import Callable, Dict, List

from backend.processing.constants import BayData


def process_bays(
    bay_data: List[BayData],
    *,
    sync_cache: Callable[[], None],
    clear_cache: Callable[[], None],
    process_bay: Callable[[BayData], object],
    get_formations: Callable[[], Dict],
    aggregate_totals: Callable[[object], Dict],
    assemble_bay: Callable[[BayData, object], None],
    finalize: Callable[[List[BayData]], None],
    reset_results: Callable[[], None],
) -> None:
    """Processa cada bay e aplica a finalização consolidada.

    As callbacks mantêm no ``ExcelProcessor`` apenas o estado e as regras de
    um bay, enquanto este módulo cuida exclusivamente da sequência multi-bay.
    """
    if not bay_data:
        raise ValueError("No bay data provided")

    sync_cache()
    for bay in bay_data:
        clear_cache()
        workbook = process_bay(bay)
        bay["totals"] = aggregate_totals(workbook)
        bay["_workbook"] = workbook
        bay["_formations"] = get_formations()
        assemble_bay(bay, workbook)

    finalize(bay_data)
    reset_results()
