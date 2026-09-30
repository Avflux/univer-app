"""Constantes compartilhadas pelo módulo de processamento de planilhas.

Centraliza nomes de abas/equipamentos, colunas e tipos usados no fluxo de
geração de workbooks, evitando literais mágicos espalhados pelo código.
"""

from typing import Dict, List, NotRequired, Tuple, TypedDict

# --- Colunas padrão das abas de dados --------------------------------
DATA_COLUMNS: Tuple[str, ...] = ("A", "B", "C", "D", "E", "F")
SUMMARY_COLUMNS: Tuple[str, ...] = ("A", "B")

# --- Equipamentos / abas especiais -----------------------------------
PAINEL = "PAINEL"
DISJUNTOR = "DISJUNTOR"
SECCIONADORA = "SECCIONADORA"
SINCRONIZADOR = "SINCRONIZADOR"
MERGING_UNIT = "MERGING UNIT"
COSTURA = "COSTURA"
CAIXA_CA = "CAIXA CA"
CAIXA_DISTRIBUICAO_CA = "CAIXA DE DISTRIBUIÇÃO CA"
CAIXA_TC = "CAIXA TC"
CAIXA_TP = "CAIXA TP"
CASA_DE_COMANDO = "CASA DE COMANDO"
CABANA = "CABANA"

# --- Abas de resumo --------------------------------------------------
TOTAL = "TOTAL"
SUMARIO_GERAL = "Sumário Geral"
TOTAL_GERAL = "Total Geral"
SHEET_DISTANCIAS = "Distâncias"

# --- Tipos de medição ------------------------------------------------
MEASUREMENT_COSTURA = "Costura"
MEASUREMENT_CAIXA = "Caixa"
# Sem alimentação CA: não inclui as abas COSTURA nem CAIXA CA no workbook final.
MEASUREMENT_NONE = "Sem Alim."

# --- TC/TP -----------------------------------------------------------
TC = "TC"
TP = "TP"
WINDING_PREFIX_TC = "S"
WINDING_PREFIX_TP = "a"
WINDING_MAX_PHASES = 6

# --- Diversos --------------------------------------------------------
DEFAULT_BAY_NAME = "Desconhecido"

# --- Tipos de dados --------------------------------------------------
Connection = Tuple[str, str, float]
DistanceMap = Dict[Tuple[str, str], float]


class BayData(TypedDict):
    """Dados de um bay para processamento múltiplo (process_multiple_bays)."""

    name: str
    type: str
    voltage: str
    measurement_type: str
    seccionadora_count: int
    template_path: str
    sincronizador_enabled: bool
    results: List[Connection]
    tc_phases: int
    tp_phases: int
    merging_unit_enabled: bool
    # Aliases editáveis na aba DistCad (canonical -> nome customizado).
    point_aliases: NotRequired[Dict[str, str]]
    # Populado durante o processamento (process_multiple_bays)
    totals: NotRequired[Dict[str, float]]