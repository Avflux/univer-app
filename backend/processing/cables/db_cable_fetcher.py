"""Busca da lista padrão de cabos de um bay no banco SQLite.

Isola o acesso a dados (SQLite) e as regras de negócio de coleta da
camada de transporte (handlers ZMQ). A reconstrução da cadeia de
costura fica em ``backend.processing.workflow.costura_chain``.

A lógica é compartilhada entre ``get_cabos_from_db`` (lista de cabos da
UI) e ``export_all_bays_sheet`` (exportação multi-bay).
"""

from __future__ import annotations

import os
import re
import sqlite3

from backend.core.db import get_db_path
from backend.core.logging.logger import get_logger
from backend.core.utils.point_utils import get_canonical_name
from backend.processing.workflow.costura_chain import build_costura_chain

log = get_logger(__name__)


def _get_db_path() -> str:
    """Retorna o caminho do banco de dados nexus_costura.db.

    O banco fica no diretório gravável do usuário
    (``%LOCALAPPDATA%\\NEXUS``), semeado do bundle e migrado no startup —
    ver :mod:`backend.core.db`.
    """
    return get_db_path()


def _normalizar(valor) -> str:
    """Normaliza um nome para comparação (maiúsculas, sem espaços nas pontas)."""
    return str(valor or "").strip().upper()


def default_distance_key(
    tipo_conexao,
    origem,
    destino,
    funcao,
) -> tuple[str, str, str, str]:
    """Chave canônica de um padrão de distância do banco.

    A identidade de um padrão é ``(tipo_conexao, origem, destino, funcao)`` —
    **não** o ``id`` de ``ponto_costura``: o id é posicional (muda quando as
    planilhas são reprocessadas), então projetos ``.md`` antigos guardam ids
    que já não apontam para o mesmo padrão. Aliases de ponto (``CASA DE
    COMANDO``/``CABANA`` → ``PAINEL``) são resolvidos aqui.
    """
    return (
        _normalizar(tipo_conexao),
        _normalizar(get_canonical_name(_normalizar(origem))),
        _normalizar(get_canonical_name(_normalizar(destino))),
        _normalizar(funcao),
    )


def get_db_default_distances_by_pair() -> dict[tuple[str, str, str, str], float]:
    """Retorna o mapa {chave: distancia} dos padrões com distância definida.

    Indexado por :func:`default_distance_key`. Nas planilhas atuais não há duas
    linhas com a mesma chave e distâncias diferentes, então a chave identifica
    um valor único.
    """
    db_path = _get_db_path()
    if not os.path.isfile(db_path):
        return {}
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT tc.nome, od_origem.nome, od_destino.nome, fu.nome, pc.distancia
            FROM ponto_costura pc
            JOIN tipo_conexao tc ON pc.tipo_conexao = tc.id
            JOIN origem_destino od_origem ON pc.origem = od_origem.id
            JOIN origem_destino od_destino ON pc.destino = od_destino.id
            JOIN funcao fu ON pc.funcao = fu.id
            WHERE pc.distancia IS NOT NULL AND pc.distancia > 0
        """).fetchall()
        conn.close()
    except Exception as e:
        log.warning("Erro ao ler distâncias padrão por par do banco: %s", e)
        return {}

    distancias: dict[tuple[str, str, str, str], float] = {}
    for tipo_conexao, origem, destino, funcao, distancia in rows:
        if distancia is None:
            continue
        chave = default_distance_key(tipo_conexao, origem, destino, funcao)
        distancias[chave] = float(distancia)
    return distancias


def _resolve_selected_points(
    bay_data: dict,
    sincronizador_enabled: bool,
) -> tuple[set[str], list[int]]:
    """Coleta os nomes canônicos dos points selecionados no bay.

    O banco conhece os pontos pelo nome canônico (default_name) e pelos
    sub-pontos de seccionadora "SECCIONADORA-N"; aqui resolvemos:
      - CASA DE COMANDO/CABANA → PAINEL (alias, via get_canonical_name)
      - sub-ponto de seccionadora (chave renomeada "xxx-N" ou
        "SECCIONADORA-N") → "SECCIONADORA-N" (canônico que o banco conhece)
    """
    points = bay_data.get("points", {})
    selected_point_names: set[str] = set()
    # Números das instâncias de seccionadora selecionadas (1, 2, ...)
    seccionadora_numbers: list[int] = []
    for pname, pinfo in points.items():
        if not isinstance(pinfo, dict) or not pinfo.get("selected", False):
            continue
        default_name = pinfo.get("default_name")
        if not isinstance(default_name, str) or not default_name:
            default_name = pname
        canonical = get_canonical_name(default_name)
        selected_point_names.add(canonical)
        # Sub-ponto de seccionadora: banco conhece "SECCIONADORA-N"
        if canonical == "SECCIONADORA" and isinstance(
            pinfo.get("instance_number"), int
        ):
            num = int(pinfo["instance_number"])
            selected_point_names.add(f"SECCIONADORA-{num}")
            seccionadora_numbers.append(num)
        elif canonical == "SECCIONADORA" and re.search(r"-(\d+)$", pname):
            num = int(re.search(r"-(\d+)$", pname).group(1))
            selected_point_names.add(f"SECCIONADORA-{num}")
            seccionadora_numbers.append(num)
    seccionadora_numbers = sorted(set(seccionadora_numbers))
    # Sincronizador é controlado por flag, não por point selecionado
    if sincronizador_enabled:
        selected_point_names.add("SINCRONIZADOR")
    return selected_point_names, seccionadora_numbers


def _expand_seccionadora_instances(
    rows: list[tuple],
    seccionadora_numbers: list[int],
) -> list[tuple]:
    """Expande a linha-base "SECCIONADORA" do banco para cada instância.

    O banco tem apenas UMA linha por tipo_conexao usando o nome base
    "SECCIONADORA" (sem sufixo) — a aba SECCIONADORA, 'Circ. Comando
    (Alim. 125 Vcc)': SECCIONADORA → PAINEL. Se o bay tem mais de uma
    seccionadora selecionada (SECCIONADORA-1, SECCIONADORA-2, ...),
    essa mesma linha do banco precisa ser repetida para cada instância.
    """
    if not rows or not seccionadora_numbers:
        return rows
    expanded_rows: list[tuple] = []
    for row in rows:
        origem_db, destino_db = row[4], row[5]
        if origem_db == "SECCIONADORA" and destino_db == "SECCIONADORA":
            # Ambas as pontas são a base: um cabo por par de instâncias
            for i, n1 in enumerate(seccionadora_numbers):
                for n2 in seccionadora_numbers[i + 1 :]:
                    expanded_rows.append(
                        row[:4] + (f"SECCIONADORA-{n1}", f"SECCIONADORA-{n2}") + row[6:]
                    )
        elif origem_db == "SECCIONADORA":
            expanded_rows.extend(
                row[:4] + (f"SECCIONADORA-{n}", destino_db) + row[6:]
                for n in seccionadora_numbers
            )
        elif destino_db == "SECCIONADORA":
            expanded_rows.extend(
                row[:4] + (origem_db, f"SECCIONADORA-{n}") + row[6:]
                for n in seccionadora_numbers
            )
        else:
            expanded_rows.append(row)
    return expanded_rows


def collect_cabos_from_db(
    bay_data: dict,
    bay_id: str,
) -> tuple[str, list[dict], list[int], str]:
    """Coleta a lista padrão de cabos de um bay no banco SQLite.

    O filtro é derivado do projeto .md do bay:
      - ``measurement_type``: filtra as abas incluídas — ``Costura`` exclui
        CAIXA CA, ``Caixa`` exclui COSTURA, ``Sem Alim.`` exclui ambas
        (COSTURA e CAIXA CA) mas mantém os demais cabos do bay
      - ``tipo_conexao``: montado de ``bay_type`` + ``voltage_level`` do bay
        (ex: ``LT - 230kV``); sem essas configs, retorna lista vazia
      - ``bitola = 1``: apenas registros marcados para bitola
      - ``origem`` E ``destino``: ambos os pontos devem estar ``selected: true``
        nos points do bay (resolvendo aliases PAINEL e sub-pontos
        ``SECCIONADORA-N``; SINCRONIZADOR entra conforme ``sincronizador_enabled``)
      - seccionadora: a linha única da aba SECCIONADORA que usa o nome base
        ``SECCIONADORA`` (ex.: ``SECCIONADORA → PAINEL``, 'Circ. Comando
        (Alim. 125 Vcc)') é replicada para cada instância selecionada
        (``SECCIONADORA-1``, ``SECCIONADORA-2``, ...) — todas recebem o
        mesmo item do banco
      - costura (aba COSTURA, ``measurement_type == 'Costura'``): a aba é um
        grafo completo de pares entre todos os equipamentos; em vez de
        devolver todos os pares, a costura é reconstruída como a cadeia dos
        pontos selecionados na ordem canônica (ex.: ``PAINEL→CAIXA TC→
        CAIXA TP→DISJUNTOR→SECCIONADORA-1→...``), uma linha por par
        consecutivo e por função (94 ``Ilum./Aquec./Tom.`` e 98 ``Motores
        dos Equipamentos``), usando a formação que o banco define para cada
        par. Cada função monta a própria cadeia apenas com os pontos que
        possuem linhas de costura DAQUELA função no banco (ex.: função 98
        só tem PAINEL/DISJUNTOR/SECCIONADORA-N — sem CAIXA TC/TP —, então
        gera ``PAINEL→DISJUNTOR``, ``DISJUNTOR→SECCIONADORA-1``, ...); itens
        de outras funções nunca entram na lista. Pontos sem linhas de
        costura no banco (ex.: TRANSFORMADOR) são ignorados na cadeia

    Returns:
        (status, rows, seccionadora_numbers, mensagem)

        - ``status``: ``"sucesso"`` ou ``"erro"``
        - ``rows``: lista no formato CableGaugeRow (vazia em caso de erro)
        - ``seccionadora_numbers``: números das instâncias SECCIONADORA-N
          selecionadas (usado pela exportação multi-bay)
        - ``mensagem``: motivo (configuração ausente, banco indisponível, …)
    """
    # Tipo de conexão do bay (ex: "LT - 230kV")
    bay_type = (bay_data.get("bay_type") or "").strip()
    voltage_level = (bay_data.get("voltage_level") or "").strip()
    measurement_type = (bay_data.get("measurement_type") or "Costura").strip()
    sincronizador_enabled = bay_data.get("sincronizador_enabled", True)

    # A busca depende de bay_type + voltage_level para montar o tipo_conexao
    # (ex: "LT - 230kV", "TRAFO - 500kV"). Sem eles não há como filtrar.
    if not bay_type or not voltage_level:
        return (
            "sucesso",
            [],
            [],
            "Bay sem bay_type/voltage_level configurados — impossível buscar a lista padrão.",
        )
    tipo_conexao_nome = f"{bay_type} - {voltage_level}"

    selected_point_names, seccionadora_numbers = _resolve_selected_points(
        bay_data,
        sincronizador_enabled,
    )

    db_path = _get_db_path()
    if not os.path.isfile(db_path):
        return "erro", [], [], f"Banco de dados não encontrado: {db_path}"

    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")

        # Query base: junta todas as tabelas de lookup
        query = """
            SELECT
                pc.id,
                ta.nome AS tipo_aparelho,
                f.nome AS formacao,
                fu.nome AS funcao,
                od1.nome AS origem,
                od2.nome AS destino,
                pc.distancia,
                pc.bitola,
                tc.nome AS tipo_conexao,
                tc.kvs
            FROM ponto_costura pc
            JOIN tipo_aparelho ta ON pc.tipo = ta.id
            JOIN formacao f ON pc.formacao = f.id
            JOIN funcao fu ON pc.funcao = fu.id
            JOIN origem_destino od1 ON pc.origem = od1.id
            JOIN origem_destino od2 ON pc.destino = od2.id
            JOIN tipo_conexao tc ON pc.tipo_conexao = tc.id
            WHERE pc.bitola = 1
        """
        params: list = []

        # Filtra por tipo_conexao se disponível
        if tipo_conexao_nome:
            query += " AND UPPER(tc.nome) = UPPER(?)"
            params.append(tipo_conexao_nome)

        # Filtra por measurement_type (exclui abas conforme medição)
        # Costura: exclui CAIXA CA; Caixa: exclui COSTURA; Sem Alim.:
        # exclui ambas (COSTURA e CAIXA CA), mantendo os demais cabos
        # (comandos) do bay — o bay NÃO é ignorado na exportação.
        if measurement_type == "Costura":
            query += " AND UPPER(ta.nome) NOT IN ('CAIXA CA')"
        elif measurement_type == "Caixa":
            query += " AND UPPER(ta.nome) NOT IN ('COSTURA')"
        elif measurement_type == "Sem Alim.":
            query += " AND UPPER(ta.nome) NOT IN ('COSTURA', 'CAIXA CA')"

        # Exclui SINCRONIZADOR se desabilitado
        if not sincronizador_enabled:
            query += " AND UPPER(ta.nome) != 'SINCRONIZADOR'"

        rows = conn.execute(query, params).fetchall()
        conn.close()

        # Separa as linhas de COSTURA (tipo=9) das demais (comandos, etc.).
        costura_rows = [r for r in rows if (r[1] or "").upper() == "COSTURA"]
        other_rows = [r for r in rows if (r[1] or "").upper() != "COSTURA"]

        # Filtra por points selecionados: mantém apenas linhas onde AMBOS
        # origem e destino são pontos presentes no bay (selecionados).
        if selected_point_names:
            other_rows = [
                r
                for r in other_rows
                if r[4] in selected_point_names and r[5] in selected_point_names
            ]
        else:
            other_rows = []

        # Expande a linha-base SECCIONADORA para cada instância selecionada.
        other_rows = _expand_seccionadora_instances(other_rows, seccionadora_numbers)

        # Costura: reconstrói a cadeia a partir dos pontos selecionados na
        # ordem canônica (DEFAULT_POINTS + instâncias SECCIONADORA-N ao final).
        chain_rows: list[tuple] = []
        if measurement_type == "Costura" and costura_rows:
            chain_rows = build_costura_chain(
                costura_rows,
                selected_point_names,
                seccionadora_numbers,
            )

        rows = other_rows + chain_rows

        # Monta a resposta no formato CableGaugeRow
        result_rows = []
        for i, row in enumerate(rows):
            (
                _id,
                tipo_aparelho,
                formacao,
                funcao,
                origem,
                destino,
                distancia,
                bitola,
                tipo_conexao,
                kvs,
            ) = row

            # A "bitola original" é a formação do cabo (ex: (4x4), [2x16])
            bitola_str = formacao if formacao else ""

            result_rows.append(
                {
                    "id": _id,
                    "funcao": funcao or "",
                    "bitolaOriginal": bitola_str,
                    "novaBitola": bitola_str,
                    "origem": origem or "",
                    "destino": destino or "",
                    "formacao": formacao or "",
                    "distancia": distancia,
                    "tipo_aparelho": tipo_aparelho or "",
                    "tipo_conexao": tipo_conexao or "",
                }
            )

        log.info(
            "get_cabos_from_db: bay=%s, tipo_conexao=%s, total=%d rows (from %d in DB)",
            bay_id,
            tipo_conexao_nome,
            len(result_rows),
            len(rows),
        )

        return "sucesso", result_rows, seccionadora_numbers, ""

    except Exception as e:
        log.exception("Erro ao buscar cabos do banco para %s", bay_id)
        return "erro", [], [], str(e)
