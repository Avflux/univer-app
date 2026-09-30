"""Ordem canônica dos pontos e conversões de cable_data (regras puras).

Espelha as constantes e regras do frontend (``POINTS`` em
baySettingsModel / distanceSort) para que o backend assuma a ordenação
canônica das linhas de "Distâncias" — a planilha é o consumidor final, e
a ordem não deve depender do frontend.

Também centraliza as conversões entre o formato CableGaugeRow (UI) e o
formato interno do .md (``cable_data``).
"""

from __future__ import annotations

import re

# IDs dos pontos na ordem canônica de exibição (mesma do POINTS do frontend).
POINT_IDS: tuple[str, ...] = (
    "CASA DE COMANDO",
    "CABANA",
    "CAIXA TC",
    "CAIXA TP",
    "TRANSFORMADOR",
    "REATOR",
    "CAPACITOR",
    "CAIXA DE DISTRIBUIÇÃO CA",
    "DISJUNTOR",
    "MERGING UNIT",
    "SECCIONADORA",
)

# Lookup id → índice da ordem canônica.
_POINT_INDEX: dict[str, int] = {pid: i for i, pid in enumerate(POINT_IDS)}

# Labels padrão (humanos) exibidos no dialog "Trocar Nomes" — usados na
# resolução de nomes renomeados para o id canônico.
POINT_LABELS: dict[str, str] = {
    "CASA DE COMANDO": "Casa de Comando",
    "CABANA": "Cabana",
    "CAIXA TC": "Caixa TC",
    "CAIXA TP": "Caixa TP",
    "TRANSFORMADOR": "Transformador",
    "REATOR": "Reator",
    "CAPACITOR": "Capacitor",
    "CAIXA DE DISTRIBUIÇÃO CA": "Caixa de Distribuição CA",
    "DISJUNTOR": "Disjuntor",
    "MERGING UNIT": "Merging Unit",
    "SECCIONADORA": "Seccionadora",
}

_SUBPOINT_RE = re.compile(r"^(.+)-(\d+)$")


def default_names_from_points(points: dict) -> dict[str, str]:
    """Mapa ``nome_exibido → default_name (canônico)`` dos points de um bay.

    Usado para ordenar linhas mesmo quando o ponto foi renomeado: o
    ``default_name`` permanece o canônico.
    """
    if not isinstance(points, dict):
        return {}
    result: dict[str, str] = {}
    for name, info in points.items():
        if not isinstance(info, dict):
            continue
        result[str(name)] = str(info.get("default_name") or name)
    return result


def point_sort_index(
    name: str | None,
    default_names: dict[str, str] | None = None,
) -> float:
    """Chave numérica de ordenação de um nome de ponto.

    Mesma semântica de ``getPointSortIndex`` do frontend: pontos na ordem
    do ``POINTS``; PAINEL (alias de CASA DE COMANDO) ordena no índice 0;
    nomes renomeados resolvem de volta ao ``default_name`` canônico;
    sub-pontos de seccionadora (``SECCIONADORA-N`` ou ``xxx-N``) agrupam
    logo após a base.
    """
    if name is None:
        name = ""
    idx = _POINT_INDEX.get(name)
    if idx is not None:
        return float(idx)
    # PAINEL é alias de CASA DE COMANDO (index 0)
    if name == "PAINEL":
        return 0.0

    # Ponto renomeado: usa o default_name canônico para achar a posição
    default_names = default_names or {}
    default_name = default_names.get(name, name)

    # Sub-pontos de seccionadora ficam logo após a base (a base pode estar
    # renomeada ou ser o canônico).
    m = _SUBPOINT_RE.match(name)
    if m:
        base_name = m.group(1) or ""
        base_default = default_names.get(base_name, base_name)
        base_idx = _POINT_INDEX.get(base_default)
        if base_idx is None:
            base_idx = _POINT_INDEX.get(base_name)
        if base_idx is not None:
            try:
                n = int(m.group(2))
            except ValueError:
                n = 0
            return base_idx + n * 0.1

    default_idx = _POINT_INDEX.get(default_name)
    if default_idx is not None:
        return float(default_idx)
    return float(len(POINT_IDS))


def sort_distance_rows(
    rows: list[dict],
    default_names: dict[str, str] | None = None,
) -> list[dict]:
    """Ordena linhas de distâncias na ordem canônica dos pontos.

    1. Normaliza a orientação de cada par — o ponto que vem primeiro na
       ordem canônica fica na coluna "origem".
    2. Ordena por origem e, em seguida, destino.

    Mantém os demais campos da linha (id, distancia) e a ordem relativa
    de linhas com a mesma chave de ordenação.
    """
    default_names = default_names or {}

    def _index(name: object) -> float:
        return point_sort_index(str(name or ""), default_names)

    normalized = []
    for row in rows:
        origem = str(row.get("origem") or "")
        destino = str(row.get("destino") or "")
        if origem and destino and _index(origem) > _index(destino):
            swapped = dict(row)
            swapped["origem"] = destino
            swapped["destino"] = origem
            normalized.append(swapped)
        else:
            normalized.append(row)

    return sorted(
        normalized, key=lambda r: (_index(r.get("origem")), _index(r.get("destino")))
    )


# --- CableGaugeRow → cable_data (.md) ---------------------------------------


def rows_to_cable_data(bay_id: str, rows: list[dict]) -> list[dict]:
    """Converte CableGaugeRow[] (UI) para o formato interno do .md.

    Cada row recebe a estrutura que o ``CableResolver`` do backend usa
    como chave de cache:

      { id, bitola, funcao, origin, destination, cache_key, (opcional: distancia) }

    ``cache_key`` segue a convenção ``bitola|funcao|origem|destino|bay``
    (mesma de ``CableResolver.get_formation_key``).

    Args:
        bay_id: Chave do bay no projeto (.md).
        rows: Linhas no formato CableGaugeRow:
            [{ id, funcao, novaBitola, origem, destino, (distancia) }]
    """
    result: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        nova_bitola = str(row.get("novaBitola") or row.get("bitola") or "")
        funcao = str(row.get("funcao") or "")
        origem = str(row.get("origem") or row.get("origin") or "")
        destino = str(row.get("destino") or row.get("destination") or "")
        entry: dict = {
            "id": row_id,
            "bitola": nova_bitola,
            "funcao": funcao,
            "origin": origem,
            "destination": destino,
            "cache_key": f"{nova_bitola}|{funcao}|{origem}|{destino}|{bay_id}",
        }
        distancia = row.get("distancia")
        if distancia is not None and str(distancia).strip() != "":
            try:
                entry["distancia"] = float(str(distancia).replace(",", "."))
            except (ValueError, TypeError):
                entry["distancia"] = distancia

        result.append(entry)
    return result
