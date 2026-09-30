"""Montagem do ``bay_data_list`` usado na exportação multi-bay.

Separa a transformação de dados (domínio) da persistência/I/O: esta
função recebe os bays do projeto e devolve a lista de payloads pronta
para ``ExcelProcessor.process_multiple_bays``, sem tocar em arquivos.

```python
bay_data_list, skipped = build_export_payload(bays)
```
"""

from __future__ import annotations

import re

from backend.core.logging.logger import get_logger
from backend.core.bay.point_rename import seccionadora_sub_point_number
from backend.core.utils.point_utils import get_canonical_name
from backend.processing.cables.db_cable_fetcher import (
    _resolve_selected_points,
    collect_cabos_from_db,
    default_distance_key,
    get_db_default_distances_by_pair,
)
from backend.processing.templates.template_utils import resolve_template

log = get_logger(__name__)


def _canonical_export_point_name(name: object, bay_data: dict) -> str:
    """Resolve um nome salvo (canônico ou alias) para a chave de exportação.

    A renomeação em cascata grava o alias nas distâncias e em ``cable_data``.
    Antes de montar a planilha, recuperamos o ``default_name`` para que o
    ``DistanceManager`` possa aplicar o alias novamente somente nas células
    exibidas. PAINEL continua sendo o alias canônico especial.
    """
    text = str(name or "").strip()
    if not text:
        return text

    points = bay_data.get("points") or {}
    if isinstance(points, dict):
        direct_info = points.get(text)
        if isinstance(direct_info, dict):
            default_name = direct_info.get("default_name") or text
            if default_name == "SECCIONADORA" and text != "SECCIONADORA":
                n = seccionadora_sub_point_number(text, direct_info)
                if n is not None:
                    return f"SECCIONADORA-{n}"
                # sem número na chave nem em instance_number:
                # cai para a resolução por point_aliases mais abaixo
            else:
                return get_canonical_name(default_name)

        for point_name, point_info in points.items():
            if not isinstance(point_info, dict):
                continue
            default_name = point_info.get("default_name") or point_name
            if text == default_name:
                if default_name == "SECCIONADORA" and text != "SECCIONADORA":
                    n = seccionadora_sub_point_number(text, point_info)
                    if n is not None:
                        return f"SECCIONADORA-{n}"
                    # sem número na chave nem em instance_number:
                    # cai para a resolução por point_aliases mais abaixo
                else:
                    return get_canonical_name(default_name)

    aliases = bay_data.get("point_aliases") or {}
    if isinstance(aliases, dict):
        for canonical, alias in aliases.items():
            alias_text = str(alias or "").strip()
            if text == alias_text:
                if re.fullmatch(r"SECCIONADORA-\d+", str(canonical)):
                    return str(canonical)
                match = re.match(r"^(.+)-(\d+)$", text)
                if canonical == "SECCIONADORA" and match:
                    return f"SECCIONADORA-{match.group(2)}"
                return get_canonical_name(canonical)
            if canonical == "SECCIONADORA" and alias_text:
                match = re.match(rf"^{re.escape(alias_text)}-(\d+)$", text)
                if match:
                    return f"SECCIONADORA-{match.group(1)}"

    return get_canonical_name(text)


def _canonicalize_cable_data(cable_data: list[dict], bay_data: dict) -> list[dict]:
    """Copia ``cable_data`` com origem/destino canônicos para o exportador."""
    normalized: list[dict] = []
    for cable in cable_data:
        if not isinstance(cable, dict):
            continue
        copied = dict(cable)
        origin_key = "origin" if cable.get("origin") is not None else "origem"
        destination_key = (
            "destination" if cable.get("destination") is not None else "destino"
        )
        copied[origin_key] = _canonical_export_point_name(
            cable.get(origin_key), bay_data
        )
        copied[destination_key] = _canonical_export_point_name(
            cable.get(destination_key), bay_data
        )
        normalized.append(copied)
    return normalized


def bay_equipment_flags(bay_data: dict) -> tuple[int, int, bool]:
    """Extrai fases TC/TP e o estado da Merging Unit dos points do bay."""
    tc_phases = 1
    tp_phases = 1
    merging_unit_enabled = False
    points = bay_data.get("points", {}) or {}
    for pname, pinfo in points.items():
        if not isinstance(pinfo, dict):
            continue
        default_name = pinfo.get("default_name")
        if not isinstance(default_name, str) or not default_name:
            default_name = pname
        canonical = get_canonical_name(default_name)
        if canonical == "CAIXA TC":
            tc_phases = int(pinfo.get("phases") or 1)
        elif canonical == "CAIXA TP":
            tp_phases = int(pinfo.get("phases") or 1)
        elif canonical == "MERGING UNIT" and pinfo.get("selected", False):
            merging_unit_enabled = True
    return tc_phases, tp_phases, merging_unit_enabled


def bay_distance_map(bay_data: dict) -> dict[frozenset, float]:
    """Mapa de distâncias do bay salvo no .md (``bay['distances']``).

    Chave: ``frozenset({origem, destino})`` (par não-orientado); valor:
    distância em metros. Linhas vazias ou sem distância são ignoradas.
    """
    dist_map: dict[frozenset, float] = {}
    for entry in bay_data.get("distances") or []:
        if not isinstance(entry, dict):
            continue
        origem = _canonical_export_point_name(entry.get("origem"), bay_data)
        destino = _canonical_export_point_name(entry.get("destino"), bay_data)
        raw = entry.get("distancia")
        if not origem or not destino or raw is None or raw == "":
            continue
        try:
            dist = float(str(raw).replace(",", "."))
        except (ValueError, TypeError):
            continue
        if dist >= 0:
            dist_map[frozenset((origem, destino))] = dist
    return dist_map


def build_export_payload(bays: dict) -> tuple[list[dict], list[dict]]:
    """Prepara o ``bay_data_list`` para a exportação multi-bay.

    Fluxo, para cada bay do projeto (.md):
      1. Se ``bay['cable_data']`` existir, utiliza diretamente a lista de
         cabos editada pelo usuário no projeto (suportando IDs duplicados,
         bitolas customizadas e distâncias padrão). Caso contrário, coleta
         a lista padrão no banco SQLite ``nexus_costura.db``
         (``collect_cabos_from_db``).
      2. As distâncias de cada cabo vêm do próprio cabo, das distâncias
         salvas do bay no .md (``bay['distances']``) ou da distância padrão
         do banco de dados.
      3. Monta a entrada do bay (BayData) consumida por
         ``ExcelProcessor.process_multiple_bays``.

    Args:
        bays: Dict ``{bay_id: bay_data}`` do projeto (.md).

    Returns:
        (bay_data_list, skipped)

        - ``bay_data_list``: lista de payloads por bay, pronta para o
          processamento multi-bay.
        - ``skipped``: lista de bays ignorados com o motivo, ex.:
          ``[{"bay": "Bay 2", "motivo": "..."}]``.
    """
    bay_data_list = []
    skipped: list[dict] = []
    # Distâncias padrão do banco indexadas por (tipo_conexao, origem, destino,
    # funcao) — a chave estável do padrão. Não use o ``id`` de ponto_costura:
    # ele é posicional e muda quando as planilhas são reprocessadas.
    db_defaults = get_db_default_distances_by_pair()

    for bay_id, bay_data in bays.items():
        if not isinstance(bay_data, dict):
            continue

        bay_type = (bay_data.get("bay_type") or "").strip()
        voltage_level = (bay_data.get("voltage_level") or "").strip()
        measurement_type = (bay_data.get("measurement_type") or "Costura").strip()
        # Tipo de conexão do bay (ex.: "LT - 230kV") — usado como chave do
        # padrão de distância do banco.
        tipo_conexao_nome = (
            f"{bay_type} - {voltage_level}" if bay_type and voltage_level else ""
        )

        custom_cable_data = bay_data.get("cable_data")
        if isinstance(custom_cable_data, list) and len(custom_cable_data) > 0:
            custom_cable_data = _canonicalize_cable_data(custom_cable_data, bay_data)
            # cable_data é a fonte primária (mais atualizado que o DB).
            # Aplica o filtro selected:true para manter apenas pares onde
            # AMBOS os pontos estão selecionados no bay.
            selected_names, sel_secc_numbers = _resolve_selected_points(
                bay_data,
                bay_data.get("sincronizador_enabled", True),
            )

            # Verifica se o bay tem points reais configurados com
            # selected:true — o filtro só se aplica quando existem
            # pontos selecionados além do SINCRONIZADOR.
            points = bay_data.get("points") or {}
            has_real_selection = any(
                isinstance(p, dict) and p.get("selected", False)
                for p in points.values()
            )

            rows = []
            secc_set: set[int] = set()
            for cable in custom_cable_data:
                if not isinstance(cable, dict):
                    continue
                c_id = cable.get("id")
                origem = _canonical_export_point_name(
                    cable.get("origin") or cable.get("origem"),
                    bay_data,
                )
                destino = _canonical_export_point_name(
                    cable.get("destination") or cable.get("destino"),
                    bay_data,
                )
                bitola = str(cable.get("bitola") or cable.get("novaBitola") or "")
                funcao = str(cable.get("funcao") or "").strip()
                dist = cable.get("distancia")
                if dist is None or dist == "":
                    # Padrão do banco pelo par (tipo_conexao, origem, destino,
                    # funcao). O ``id`` do registro NÃO participa: ele é
                    # posicional e muda quando as planilhas são reprocessadas.
                    dist = db_defaults.get(
                        default_distance_key(
                            tipo_conexao_nome,
                            origem,
                            destino,
                            funcao,
                        )
                    )

                # Filtro selected:true: mantém apenas cabos onde AMBOS os
                # pontos (origem e destino) estão selecionados no bay.
                # Resolve nomes canônicos para bater com os nomes do banco
                # e do template (ex.: PAINEL = CASA DE COMANDO/CABANA).
                # O filtro só se aplica quando o bay tem points reais
                # configurados — sem points selecionados, todos os cabos
                # do cable_data são mantidos.
                if has_real_selection and selected_names:
                    origem_canon = get_canonical_name(origem)
                    destino_canon = get_canonical_name(destino)
                    # Sub-pontos de seccionadora (SECCIONADORA-N) também
                    # são aceitos diretamente (banco usa SECCIONADORA-N).
                    if not (origem_canon in selected_names or origem in selected_names):
                        continue
                    if not (
                        destino_canon in selected_names or destino in selected_names
                    ):
                        continue

                rows.append(
                    {
                        "id": c_id,
                        "origem": origem,
                        "destino": destino,
                        "bitola": bitola,
                        "funcao": funcao,
                        "distancia": dist,
                    }
                )
                for endpoint in (origem, destino):
                    m = re.search(r"SECCIONADORA-(\d+)$", endpoint, re.IGNORECASE)
                    if m:
                        secc_set.add(int(m.group(1)))

            # Números de seccionadora: usa do cable_data se encontrado,
            # senão usa os resolvidos dos points selecionados.
            seccionadora_numbers = sorted(secc_set) if secc_set else sel_secc_numbers
        else:
            status, rows, seccionadora_numbers, mensagem = collect_cabos_from_db(
                bay_data, bay_id
            )
            if status != "sucesso":
                skipped.append({"bay": bay_id, "motivo": mensagem})
                continue
            if not rows:
                skipped.append(
                    {
                        "bay": bay_id,
                        "motivo": mensagem
                        or "Nenhum cabo encontrado no banco para o bay.",
                    }
                )
                continue

        # Distâncias do bay salvas no .md (par não-orientado → distância)
        dist_map = bay_distance_map(bay_data)

        # Monta as conexões (origem, destino, distância) a partir das linhas
        # coletadas. Sem distância resolvida a linha não pode ser exportada.
        results = []
        for row in rows:
            origem = row.get("origem") or ""
            destino = row.get("destino") or ""
            if not origem or not destino:
                continue
            dist = None
            if row.get("distancia") is not None and row.get("distancia") != "":
                try:
                    dist = float(str(row["distancia"]).replace(",", "."))
                except (ValueError, TypeError):
                    dist = None
            if dist is None or dist < 0:
                dist = dist_map.get(frozenset((origem, destino)))
            if dist is None or dist < 0:
                # Mesmo fallback por par do banco (nunca pelo id do registro).
                dist = db_defaults.get(
                    default_distance_key(
                        tipo_conexao_nome,
                        origem,
                        destino,
                        row.get("funcao"),
                    )
                )
            if dist is None or dist < 0:
                continue
            results.append((origem, destino, dist))

        # As abas do template (DISJUNTOR, SECCIONADORA-N, TC/TP, ...) referenciam
        # pares entre quaisquer pontos selecionados (ex.: CAIXA TP→PAINEL,
        # CAIXA TC→DISJUNTOR, SECCIONADORA-2→DISJUNTOR, com redirect
        # PAINEL→MERGING UNIT e SECCIONADORA→SECCIONADORA-N); sem os pares
        # completos a busca de distância falha e as abas dos equipamentos
        # selecionados perdem funções ou somem.
        # Inclui todos os pares com distância salva no bay — o conjunto
        # "selecionado" da planilha passa a refletir todos os points marcados
        # (point_aliases/selected), não apenas os pares da cadeia de costura.
        present = {frozenset((o, d)) for o, d, _ in results}
        for pair, dist in dist_map.items():
            if pair not in present:
                origem_p, destino_p = tuple(pair)
                results.append((origem_p, destino_p, dist))

        if not results:
            skipped.append(
                {
                    "bay": bay_id,
                    "motivo": "Nenhuma distância encontrada para o bay — calcule as distâncias no projeto.",
                }
            )
            continue

        tc_phases, tp_phases, merging_unit_enabled = bay_equipment_flags(bay_data)

        template_path = resolve_template(None, bay_id, bay_type, voltage_level)
        if template_path is None:
            log.warning(
                "export_all_bays_sheet: template não encontrado para %s (type=%s, vt=%s) — usando fallback",
                bay_id,
                bay_type,
                voltage_level,
            )

        bay_data_list.append(
            {
                "name": bay_id,
                "type": bay_type,
                "voltage": voltage_level,
                "measurement_type": measurement_type,
                "seccionadora_count": len(seccionadora_numbers),
                "template_path": template_path,
                "sincronizador_enabled": bay_data.get("sincronizador_enabled", True),
                "results": results,
                "tc_phases": tc_phases,
                "tp_phases": tp_phases,
                "merging_unit_enabled": merging_unit_enabled,
                "point_aliases": bay_data.get("point_aliases") or {},
                "cable_data": custom_cable_data
                if isinstance(custom_cable_data, list) and custom_cable_data
                else None,
            }
        )

    return bay_data_list, skipped
