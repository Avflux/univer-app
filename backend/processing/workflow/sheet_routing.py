"""Roteamento das abas especiais do workbook."""

from backend.processing.constants import (
    CAIXA_CA, CAIXA_TC, CAIXA_TP, COSTURA, MERGING_UNIT, PAINEL,
    SECCIONADORA, TC, TP,
)


def redirect_merging_unit(cell_d, cell_e, original_b_value, sheet_title, use_merging_unit):
    """Redireciona conexões com o PAINEL para a MERGING UNIT quando ativa."""
    if use_merging_unit:
        is_shielded = '(' in str(original_b_value) or '[' in str(original_b_value)
        if is_shielded and sheet_title not in (COSTURA, CAIXA_CA):
            if cell_d == PAINEL:
                cell_d = MERGING_UNIT
            if cell_e == PAINEL:
                cell_e = MERGING_UNIT
    return cell_d, cell_e


def special_sheet_kind(sheet_name: str, selected: set[str]) -> str | None:
    """Retorna ``tc``, ``tp``, ``seccionadora`` ou ``None``."""
    if sheet_name == SECCIONADORA:
        return "seccionadora"
    if sheet_name == TC and CAIXA_TC in selected:
        return "tc"
    if sheet_name == TP and CAIXA_TP in selected:
        return "tp"
    return None
