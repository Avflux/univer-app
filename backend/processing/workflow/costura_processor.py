"""Processamento da aba COSTURA (iluminação, motores e distância fixa)."""

import networkx as nx
from openpyxl.worksheet.worksheet import Worksheet

from backend.core.logging.logger import get_logger
from backend.processing.constants import (
    DEFAULT_BAY_NAME,
    DISJUNTOR,
    PAINEL,
    Connection,
    DistanceMap,
)
from backend.processing.workbook.distance_manager import DistanceManager
from backend.processing.workbook.sheet_builder import finalize_sheet
from backend.processing.workflow.graph_utils import (
    filter_equipment_in_graph,
    rota_gulosa,
)
from backend.processing.workflow.measurement_rules import selected_equipment

log = get_logger(__name__)


def classify_template_rows(
    template_sheet: Worksheet, selected_equipment: set[str]
) -> tuple[list[int], list[int], list[int]]:
    """Classifica as linhas do template COSTURA em iluminação, motores e distância fixa."""
    linhas_ilum: list[int] = []
    linhas_motores: list[int] = []
    linhas_distancia_fixa: list[int] = []

    for row in range(2, template_sheet.max_row + 1):
        template_distance = template_sheet[f"F{row}"].value
        origem = template_sheet[f"D{row}"].value
        destino = template_sheet[f"E{row}"].value

        equipment_selected = bool(
            (origem and origem in selected_equipment)
            or (destino and destino in selected_equipment)
        )

        if (
            template_distance is not None
            and isinstance(template_distance, (int, float))
            and template_distance > 0
            and equipment_selected
        ):
            linhas_distancia_fixa.append(row)
            continue

        funcao = template_sheet[f"C{row}"].value
        if funcao and "motores" in str(funcao).lower():
            linhas_motores.append(row)
        else:
            linhas_ilum.append(row)

    return linhas_ilum, linhas_motores, linhas_distancia_fixa


def equipment_from_rows(template_sheet: Worksheet, rows: list[int]) -> list[str]:
    """Lista de equipamentos citados nas linhas informadas."""
    equipamentos: set[str] = set()
    for row in rows:
        origem = template_sheet[f"D{row}"].value
        destino = template_sheet[f"E{row}"].value
        if origem:
            equipamentos.add(origem)
        if destino:
            equipamentos.add(destino)
    return list(equipamentos)


def find_matching_row(
    source_rows: list[int], template_sheet: Worksheet, origem: str, destino: str
) -> int | None:
    """Retorna a primeira linha de source_rows cujo par origem/destino casa."""
    for row in source_rows:
        t_origem = template_sheet[f"D{row}"].value
        t_destino = template_sheet[f"E{row}"].value
        if {origem, destino} == {t_origem, t_destino}:
            return row
    return None


def write_route_pairs(
    processor,
    template_sheet: Worksheet,
    new_sheet: Worksheet,
    source_rows: list[int],
    rota: list[str],
    dist_dict: DistanceMap,
    valid_row: int,
    has_valid_data: bool,
    pares_escritos: set[tuple[str, str]],
    bay_name: str | None,
) -> tuple[int, bool]:
    """Itera sobre rota e escreve pares consecutivos nas linhas informadas."""
    for i in range(len(rota) - 1):
        origem, destino = rota[i], rota[i + 1]
        if (origem, destino) in pares_escritos or (destino, origem) in pares_escritos:
            continue
        row = find_matching_row(source_rows, template_sheet, origem, destino)
        if row is None:
            continue

        tag = template_sheet[f"A{row}"].value
        formacao = template_sheet[f"B{row}"].value
        funcao = template_sheet[f"C{row}"].value
        has_asterisk = template_sheet[f"H{row}"].value == "*"
        distance = DistanceManager.resolve_distance(dist_dict, origem, destino)
        if distance is None:
            log.warning("Distância não encontrada para %s-%s, pulando", origem, destino)
            continue

        new_b_values = processor.cable_resolver.process_cable_value(
            formacao, has_asterisk, funcao, new_sheet.title, origem, destino, bay_name
        )
        valid_row, has_valid_data = processor._write_formation_rows(
            new_sheet,
            new_b_values,
            tag,
            funcao,
            origem,
            destino,
            distance,
            valid_row,
            has_valid_data,
        )
        pares_escritos.add((origem, destino))
    return valid_row, has_valid_data


def process_motores_equipments(
    processor,
    template_sheet: Worksheet,
    new_sheet: Worksheet,
    G: nx.Graph,
    dist_dict: DistanceMap,
    linhas_motores: list[int],
    equipamentos: list[str],
    valid_row: int,
    has_valid_data: bool,
    pares_escritos_motores: set[tuple[str, str]],
    bay_name: str | None,
) -> tuple[int, bool]:
    """Conecta PAINEL->DISJUNTOR quando possível e gera a rota gulosa de motores."""
    has_painel_disjuntor = False

    if PAINEL in equipamentos and DISJUNTOR in equipamentos:
        has_painel_disjuntor = True
        log.debug("PAINEL e DISJUNTOR estão presentes, tentando conectar primeiro")

        origem, destino = PAINEL, DISJUNTOR

        if (origem, destino) not in pares_escritos_motores and (
            destino,
            origem,
        ) not in pares_escritos_motores:
            if G.has_edge(origem, destino) or G.has_edge(destino, origem):
                log.debug("Conexão %s-%s existe no grafo", origem, destino)
                for row in linhas_motores:
                    t_origem = template_sheet[f"D{row}"].value
                    t_destino = template_sheet[f"E{row}"].value
                    if {origem, destino} == {t_origem, t_destino}:
                        tag = template_sheet[f"A{row}"].value
                        formacao = template_sheet[f"B{row}"].value
                        funcao = template_sheet[f"C{row}"].value
                        has_asterisk = template_sheet[f"H{row}"].value == "*"
                        distance = DistanceManager.resolve_distance(
                            dist_dict, origem, destino
                        )
                        if distance is None:
                            has_painel_disjuntor = False
                            log.warning(
                                "Não encontrou distância para %s-%s, pulando",
                                origem,
                                destino,
                            )
                            continue

                        log.debug(
                            "Adicionando conexão %s-%s com distância %s",
                            origem,
                            destino,
                            distance,
                        )
                        new_b_values = processor.cable_resolver.process_cable_value(
                            formacao,
                            has_asterisk,
                            funcao,
                            new_sheet.title,
                            origem,
                            destino,
                            bay_name,
                        )
                        valid_row, has_valid_data = processor._write_formation_rows(
                            new_sheet,
                            new_b_values,
                            tag,
                            funcao,
                            origem,
                            destino,
                            distance,
                            valid_row,
                            has_valid_data,
                        )
                        pares_escritos_motores.add((origem, destino))
                        break
            else:
                has_painel_disjuntor = False
                log.debug("Conexão %s-%s NÃO existe no grafo", origem, destino)
        else:
            has_painel_disjuntor = False
            log.debug("Conexão %s-%s NÃO existe no grafo", origem, destino)

        if has_painel_disjuntor:
            equipamentos = [e for e in equipamentos if e != PAINEL]
            start = DISJUNTOR
            log.debug("Removendo PAINEL da lista, começando rota gulosa de %s", start)
        else:
            start = PAINEL if PAINEL in equipamentos else equipamentos[0]
            log.debug(
                "Não conseguiu conectar PAINEL->DISJUNTOR, usando %s como ponto de partida",
                start,
            )
    else:
        start = PAINEL if PAINEL in equipamentos else equipamentos[0]
        log.debug(
            "Não tem PAINEL e DISJUNTOR juntos, usando %s como ponto de partida", start
        )

    if equipamentos and start in equipamentos:
        log.debug(
            "Gerando rota gulosa a partir de %s para equipamentos: %s",
            start,
            equipamentos,
        )
        rota = rota_gulosa(G, equipamentos, start)
        log.debug("Rota gerada: %s", rota)

        valid_row, has_valid_data = write_route_pairs(
            processor,
            template_sheet,
            new_sheet,
            linhas_motores,
            rota,
            dist_dict,
            valid_row,
            has_valid_data,
            pares_escritos_motores,
            bay_name,
        )

    return valid_row, has_valid_data


def process_costura_sheet(
    processor,
    template_sheet: Worksheet,
    new_sheet: Worksheet,
    results_data: list[Connection],
    secc_number: int | None = None,
    merging_unit_enabled: bool = False,
    bay_name: str | None = None,
) -> bool:
    if bay_name is None:
        bay_name = DEFAULT_BAY_NAME
    log.debug("Processando COSTURA para bay: %s", bay_name)

    processor.sheet_builder.prepare_sheet(template_sheet, new_sheet)

    selected = selected_equipment(results_data)
    log.debug("Equipamentos selecionados: %s", sorted(selected))

    linhas_ilum, linhas_motores, linhas_distancia_fixa = classify_template_rows(
        template_sheet, selected
    )

    valid_row = 2
    has_valid_data = False

    G = nx.Graph()
    dist_dict = DistanceManager.build_distance_dict(results_data)
    for o, d, v in results_data:
        G.add_edge(o, d, weight=v)

    pares_escritos_ilum: set[tuple[str, str]] = set()
    if linhas_ilum:
        equipamentos = equipment_from_rows(template_sheet, linhas_ilum)
        equipamentos = filter_equipment_in_graph(equipamentos, G)

        if equipamentos:
            start = PAINEL if PAINEL in equipamentos else equipamentos[0]
            log.debug(
                "ILUM/AQUEC/TOM: Usando %s como ponto de partida para rota gulosa",
                start,
            )

            rota = rota_gulosa(G, equipamentos, start)
            log.debug("Rota gerada: %s", rota)

            valid_row, has_valid_data = write_route_pairs(
                processor,
                template_sheet,
                new_sheet,
                linhas_ilum,
                rota,
                dist_dict,
                valid_row,
                has_valid_data,
                pares_escritos_ilum,
                bay_name,
            )

    pares_escritos_motores: set[tuple[str, str]] = set()
    if linhas_motores:
        log.debug("Processando %s linhas de MOTORES", len(linhas_motores))
        equipamentos = equipment_from_rows(template_sheet, linhas_motores)
        log.debug("Equipamentos encontrados para MOTORES: %s", equipamentos)
        equipamentos = filter_equipment_in_graph(equipamentos, G)
        log.debug("Equipamentos após filtragem: %s", equipamentos)

        if equipamentos:
            valid_row, has_valid_data = process_motores_equipments(
                processor,
                template_sheet,
                new_sheet,
                G,
                dist_dict,
                linhas_motores,
                equipamentos,
                valid_row,
                has_valid_data,
                pares_escritos_motores,
                bay_name,
            )

    if linhas_distancia_fixa:
        for row in linhas_distancia_fixa:
            tag = template_sheet[f"A{row}"].value
            formacao = template_sheet[f"B{row}"].value
            funcao = template_sheet[f"C{row}"].value
            origem = template_sheet[f"D{row}"].value
            destino = template_sheet[f"E{row}"].value
            distance = template_sheet[f"F{row}"].value
            has_asterisk = template_sheet[f"H{row}"].value == "*"

            new_b_values = processor.cable_resolver.process_cable_value(
                formacao,
                has_asterisk,
                funcao,
                new_sheet.title,
                origem,
                destino,
                bay_name,
            )
            valid_row, has_valid_data = processor._write_formation_rows(
                new_sheet,
                new_b_values,
                tag,
                funcao,
                origem,
                destino,
                distance,
                valid_row,
                has_valid_data,
            )

    return finalize_sheet(new_sheet, valid_row, has_valid_data)
