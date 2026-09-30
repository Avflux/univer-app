"""Reconstrução da cadeia de costura de um bay (lógica de domínio pura).

A aba COSTURA do banco é um grafo completo de pares entre todos os
equipamentos (PAINEL↔CAIXA TC, PAINEL↔DISJUNTOR, ...). Para um bay real a
costura é a cadeia dos pontos selecionados na ordem canônica
(ex.: PAINEL→CAIXA TC→CAIXA TP→DISJUNTOR→SECCIONADORA-1→...), uma linha
por par consecutivo e por função (94/98).

Este módulo contém apenas a regra de negócio da reconstrução da cadeia,
sem acesso a banco — recebe as linhas de COSTURA já carregadas e devolve
as linhas da cadeia.
"""

from __future__ import annotations

from backend.core.bay.data_manager import DEFAULT_POINTS
from backend.core.utils.point_utils import get_canonical_name

# Funções que participam da costura (abas Ilum./Aquec./Tom. e Motores).
FUNCOES_COSTURA = ("Ilum./Aquec./Tom.", "Motores dos Equipamentos")


def build_costura_chain(
    costura_rows: list[tuple],
    selected_point_names: set[str],
    seccionadora_numbers: list[int],
) -> list[tuple]:
    """Reconstrói a cadeia de costura a partir dos pontos selecionados.

    Os pontos entram na ordem canônica (``DEFAULT_POINTS`` + instâncias
    ``SECCIONADORA-N`` ao final). Pontos sem linhas de costura no banco
    (ex.: TRANSFORMADOR) são ignorados — a cadeia conecta apenas
    equipamentos com cabos de costura.

    Cada função monta a própria cadeia apenas com os pontos que possuem
    linhas de costura DAQUELA função no banco (ex.: função 98 não tem
    CAIXA TC/TP — só PAINEL/DISJUNTOR/SECCIONADORA-N —, então o par
    PAINEL→DISJUNTOR é gerado direto). Itens de outras funções nunca
    entram na lista: um par só é emitido se existir linha da função
    atual no banco.

    Args:
        costura_rows: Linhas do banco cujo ``tipo_aparelho`` é COSTURA,
            no formato bruto da query (id, tipo_aparelho, formacao,
            funcao, origem, destino, distancia, bitola, ...).
        selected_point_names: Nomes canônicos dos pontos selecionados no bay.
        seccionadora_numbers: Números das instâncias SECCIONADORA-N
            selecionadas (1, 2, ...).

    Returns:
        Lista de linhas da cadeia no mesmo formato de ``costura_rows``,
        com origem/destino substituídos pelos pontos consecutivos da
        cadeia. Vazia se não houver linhas de costura.
    """
    chain_rows: list[tuple] = []
    if not costura_rows:
        return chain_rows

    ordered_selected: list[str] = []
    for pid in DEFAULT_POINTS:
        if pid == "SECCIONADORA":
            continue  # instâncias SECCIONADORA-N tratadas abaixo
        canonical = get_canonical_name(pid)
        if canonical in selected_point_names and canonical not in ordered_selected:
            ordered_selected.append(canonical)
    for n in seccionadora_numbers:
        ordered_selected.append(f"SECCIONADORA-{n}")

    # Índice (funcao, par não-orientado) → linha do banco e pontos que
    # participam da costura em cada função.
    costura_by_pair: dict[tuple[str, frozenset], tuple] = {}
    endpoints_por_funcao: dict[str, set[str]] = {}
    for r in costura_rows:
        costura_by_pair[(r[3], frozenset((r[4], r[5])))] = r
        endpoints_por_funcao.setdefault(r[3], set()).update((r[4], r[5]))

    # Uma linha por par consecutivo e por função (94/98), na ordem de
    # seleção (origem = ponto anterior da cadeia).
    for funcao in FUNCOES_COSTURA:
        endpoints = endpoints_por_funcao.get(funcao, set())
        chain = [p for p in ordered_selected if p in endpoints]
        for a, b in zip(chain, chain[1:]):
            row = costura_by_pair.get((funcao, frozenset((a, b))))
            if row is not None:
                chain_rows.append(row[:3] + (funcao,) + (a, b) + row[6:])

    return chain_rows
