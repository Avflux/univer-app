"""Funções de serviço headless do Univer.

Cada função implementa a lógica de negócio de um comando ZMQ,
sem depender de interface gráfica.  Recebem e devolvem dicts simples
que são serializados como JSON no protocolo ZMQ.
"""

from __future__ import annotations

import os

from backend.core.bay.data_manager import DEFAULT_POINTS
from backend.core.bay.point_rename import seccionadora_sub_point_number
from backend.core.logging.logger import get_logger

log = get_logger(__name__)


# --- Projeto ---


def new_project() -> dict:
    """Cria um novo projeto vazio no sidecar."""
    from backend.sidecar.state import get_state

    state = get_state()
    result = state.new_project()
    log.info("Novo projeto criado")
    return {
        "status": "sucesso",
        "mensagem": "Novo projeto criado",
        **result,
    }


def get_project_data() -> dict:
    """Retorna os dados completos do projeto em memória."""
    from backend.sidecar.state import get_state

    state = get_state()
    return {
        "status": "sucesso",
        "project_path": state.project_path,
        "data": state.project_data,
    }


def set_project_data(data: dict) -> dict:
    """Atualiza os dados completos do projeto em memória.

    O payload recebido é a fonte de verdade: uma chave ``graph`` presente
    nele (ex.: restaurada de um .md recém-aberto) é mantida intacta, e um
    payload sem ``graph`` permanece sem grafo.
    """
    from backend.sidecar.state import get_state

    state = get_state()
    with state._lock:
        state.project_data = data
    log.info("Dados do projeto atualizados no sidecar")
    return {"status": "sucesso"}


def _order_bay_distances(bay: dict) -> None:
    """Reordena as ``distances`` salvas na ordem canônica dos pontos.

    A tabela "Distâncias" da UI é alimentada exclusivamente pela chave
    ``distances`` do .md — gerada por ``calcular_distancias_bay``
    ("Calcular Distâncias"). Nenhuma linha é derivada do ``cable_data``:
    bay sem distâncias calculadas/salvas permanece com a tabela vazia.
    Mutação in-place, sem travar — o chamador deve segurar ``state._lock``.
    """
    if not isinstance(bay, dict):
        return
    distances = bay.get("distances")
    if not (isinstance(distances, list) and distances):
        return
    from backend.core.bay.point_order import (
        default_names_from_points,
        sort_distance_rows,
    )

    points = bay.get("points")
    default_names = default_names_from_points(
        points if isinstance(points, dict) else {},
    )
    bay["distances"] = sort_distance_rows(distances, default_names)


def load_project(path: str) -> dict:
    """Carrega um projeto .md do disco.

    Após carregar, apenas reordena as ``distances`` já salvas de cada bay
    na ordem canônica dos pontos. A lista ``distances`` NÃO é derivada do
    ``cable_data``: ela só existe se tiver sido gerada por
    ``calcular_distancias_bay`` ("Calcular Distâncias") e salva.
    """
    from backend.sidecar.state import get_state

    state = get_state()
    result = state.load_project(path)
    if result.get("status") == "sucesso":
        with state._lock:
            bays = state.project_data.get("bays", {})
            if isinstance(bays, dict):
                for bay in bays.values():
                    if isinstance(bay, dict):
                        _order_bay_distances(bay)
    return result


def save_project(path: str) -> dict:
    """Salva o projeto no disco."""
    from backend.sidecar.state import get_state

    state = get_state()
    result = state.save_project(path)
    return result  # --- get_cabos_from_db ---


def get_cabos_from_db(bay_id: str) -> dict:
    """Busca a lista padrao de cabos no banco SQLite para um bay. Ver collect_cabos_from_db para filtros."""
    from backend.processing.cables.db_cable_fetcher import collect_cabos_from_db
    from backend.sidecar.state import get_state

    state = get_state()
    bays = state.project_data.get("bays", {})
    bay_data = bays.get(bay_id)

    if not bay_data or not isinstance(bay_data, dict):
        return {
            "status": "erro",
            "mensagem": f"Bay '{bay_id}' não encontrado no projeto.",
        }

    status, rows, _, mensagem = collect_cabos_from_db(bay_data, bay_id)
    return {
        "status": status,
        "bay_id": bay_id,
        "rows": rows,
        "total": len(rows),
        "mensagem": mensagem,
    }


# --- Operações de edição de domínio (cable_data / rename de pontos) ---


def _ensure_bay_entry(state, bay_id: str) -> dict:
    """Garante que o bay exista no projeto, criando o esqueleto se ausente."""
    bays = state.project_data.setdefault("bays", {})
    bay = bays.get(bay_id)
    if bay is None or not isinstance(bay, dict):
        bay = {
            "points": {},
            "cable_data": [],
            "point_aliases": {},
            "measurement_type": "",
            "bay_type": "",
            "voltage_level": "",
            "sincronizador_enabled": True,
            "additional": [],
            "distances": [],
        }
        bays[bay_id] = bay
    return bay


def _persist_open_project(state) -> tuple[str | None, str | None]:
    """Grava o .md do projeto aberto (write-through) e devolve ``(arquivo, erro)``.

    Sem projeto aberto (``project_path`` vazio), nada é gravado e o retorno é
    ``(None, None)``. Uma falha de gravação devolve ``(None, mensagem)`` — o
    estado em memória permanece íntegro, então o próximo save reescreve.
    """
    if not state.project_path:
        return None, None
    result = state.save_project("")
    if result.get("status") != "sucesso":
        return None, str(result.get("mensagem") or "falha ao gravar o projeto")
    return str(result.get("path") or state.project_path), None


def save_cable_data(bay_id: str, rows: list[dict] | None = None) -> dict:
    """Converte CableGaugeRow[] para o ``cable_data`` do .md e grava no bay.

    A conversão para o formato interno (com ``cache_key`` no padrão do
    ``CableResolver``) é responsabilidade do backend — o frontend envia
    apenas as linhas da tabela de bitolas (CableGaugeRow) e recebe o
    status. Além de atualizar o estado em memória, grava o .md do projeto
    aberto (write-through): disco e memória ficam iguais sem um passo separado
    de "salvar projeto". Grava exclusivamente ``cable_data``: a lista
    ``distances`` é gerada apenas por ``calcular_distancias_bay``.

    Args:
        bay_id: Chave do bay no projeto (.md).
        rows: Linhas no formato CableGaugeRow:
            [{ id, funcao, novaBitola, origem, destino }]

    Returns:
        {"status": "sucesso", "bay_id": ..., "total": N, "arquivo": path|None}.
        ``aviso`` é preenchido quando não há .md aberto ou a gravação falha.
    """
    from backend.core.bay.point_order import rows_to_cable_data
    from backend.sidecar.state import get_state

    state = get_state()
    rows = rows or []

    with state._lock:
        bay = _ensure_bay_entry(state, bay_id)
        cable_data = rows_to_cable_data(bay_id, rows)
        bay["cable_data"] = cable_data

    # Write-through: com um projeto .md aberto, as edições da grade vão para o
    # disco na mesma ação. Fora do ``state._lock`` — ``save_project`` adquire o
    # próprio lock.
    arquivo, erro = _persist_open_project(state)

    log.info(
        "save_cable_data: %s — %d cabos (arquivo=%s)", bay_id, len(cable_data), arquivo
    )

    response: dict = {
        "status": "sucesso",
        "bay_id": bay_id,
        "total": len(cable_data),
        "arquivo": arquivo,
    }
    if erro:
        response["aviso"] = f"Não foi possível gravar o .md: {erro}"
    elif arquivo is None:
        response["aviso"] = (
            "nenhum projeto .md aberto; as edições ficaram apenas em memória"
        )
    return response


def rename_points(
    bay_id: str,
    labels: dict[str, str] | None = None,
    defaults: dict[str, str] | None = None,
) -> dict:
    """Renomeia os pontos de um bay em cascata (points, additional,
    distances e cable_data) — regra de domínio que viveu no frontend
    (``renamePointsInBayData``) e agora roda no sidecar.

    A UI envia o mapa de ``labels`` (id canônico → novo nome; vazio
    restaura o canônico) e o mapa de ``defaults`` (nomes padrão a nível
    de projeto) e recebe o status; o projeto atualizado é lido de volta
    via ``get_project_data``.

    Args:
        bay_id: Chave do bay no projeto (.md).
        labels: Mapa ``id canônico → novo nome`` (point_aliases).
        defaults: Mapa ``id canônico → label padrão`` (point_aliases_default
            do projeto, v2.0).

    Returns:
        {"status": "sucesso", "bay_id": ...} ou erro.
    """
    from backend.core.bay.point_order import (
        default_names_from_points,
        sort_distance_rows,
    )
    from backend.core.bay.point_rename import rename_points_in_bay
    from backend.sidecar.state import get_state

    state = get_state()
    labels = labels or {}
    defaults = defaults or {}

    with state._lock:
        bay = _ensure_bay_entry(state, bay_id)
        rename_points_in_bay(bay, labels)
        # v2.0: defaults vivem a nível de projeto apenas.
        if defaults:
            state.project_data["point_aliases_default"] = defaults
        # Reordena distances na ordem canônica após a troca de nomes.
        points = bay.get("points")
        default_names = default_names_from_points(
            points if isinstance(points, dict) else {}
        )
        distances = bay.get("distances")
        if isinstance(distances, list) and distances:
            bay["distances"] = sort_distance_rows(distances, default_names)

    log.info("rename_points: %s — %d labels", bay_id, len(labels))
    return {
        "status": "sucesso",
        "bay_id": bay_id,
        "total": len(labels),
    }


# --- export_all_bays_sheet ---


def export_all_bays_sheet(output_path: str | None = None) -> dict:
    """Gera uma planilha Excel com todos os bays do projeto.

    Fluxo:
      1. Prepara o payload de cada bay (lista de cabos no banco SQLite
         ``nexus_costura.db``, distâncias salvas no .md, flags TC/TP e
         template) via ``build_export_payload`` (processing).
      2. Monta o workbook multi-bay (Sumário Geral → abas por bay → Total
         Geral) via ``ExcelProcessor.process_multiple_bays`` do módulo de
         processamento (backend processing).
      3. Salva no caminho escolhido pelo usuário (``output_path``); se
         ausente, no last_directory com nome padrão.

    Retorna:
      {
        "status": "sucesso",
        "arquivo": "J:\\...\\Planilha_Todos_Bays.xlsx",
        "bays": 3,
        "total": 42,
        "pulados": [{"bay": "Bay 2", "motivo": "..."}],
        "mensagem": "Planilha exportada: ...",
      }
    """
    from backend.core.utils.file_resolver import resolve_output_path
    from backend.processing.excel_processor import ExcelProcessor
    from backend.processing.workbook.multi_bay_payload import build_export_payload
    from backend.sidecar.state import get_state

    state = get_state()
    bays = state.project_data.get("bays", {})
    if not bays:
        return {"status": "erro", "mensagem": "Nenhum bay encontrado no projeto."}

    bay_data_list, skipped = build_export_payload(bays)

    if not bay_data_list:
        return {
            "status": "erro",
            "mensagem": "Nenhum bay com dados válidos para exportar.",
            "pulados": skipped,
        }

    processor = ExcelProcessor()
    try:
        final_wb = processor.process_multiple_bays(bay_data_list)
    except Exception as e:
        log.exception("Erro ao gerar planilha multi-bay")
        return {"status": "erro", "mensagem": str(e), "pulados": skipped}

    output_path = resolve_output_path("Planilha_Todos_Bays", ".xlsx", output_path)

    from backend.core.utils.file_lock_checker import is_file_locked

    if is_file_locked(str(output_path)):
        return {
            "status": "arquivo_aberto",
            "arquivo": str(output_path),
            "mensagem": (
                f"O arquivo '{output_path.name}' está aberto em outro programa. "
                "Feche-o e tente novamente."
            ),
            "pulados": skipped,
        }

    final_wb.save(str(output_path))

    total = sum(len(b["results"]) for b in bay_data_list)
    log.info(
        "export_all_bays_sheet: %d bays, %d conexões -> %s",
        len(bay_data_list),
        total,
        output_path,
    )
    return {
        "status": "sucesso",
        "arquivo": str(output_path),
        "bays": len(bay_data_list),
        "total": total,
        "pulados": skipped,
        "mensagem": (
            f"Planilha exportada: {output_path.name} ({len(bay_data_list)} bay(s), {total} conexões)"
        ),
    }


# --- export_all_bays_univer ---


def export_all_bays_univer() -> dict:
    """Gera a planilha multi-bay EM MEMÓRIA e devolve as abas para o Univer.

    Mesmo pipeline de ``export_all_bays_sheet`` (``build_export_payload`` +
    ``ExcelProcessor.process_multiple_bays``), mas sem gravar o ``.xlsx``: o
    destino é a tela do frontend, então o workbook é serializado por
    ``workbook_to_sheets`` (``processing/workbook/univer_snapshot.py``) — as
    abas saem com valores, mesclagens, larguras e visibilidade.

    Retorna:
      {
        "status": "sucesso",
        "bays": 3,
        "total": 42,
        "sheets": [{"name": "SUMÁRIO GERAL", "rows": [...], ...}],
        "pulados": [{"bay": "Bay 2", "motivo": "..."}],
        "mensagem": "Saída gerada: 3 bay(s), 42 conexões, 5 aba(s).",
      }
    """
    from backend.processing.excel_processor import ExcelProcessor
    from backend.processing.workbook.multi_bay_payload import build_export_payload
    from backend.processing.workbook.univer_snapshot import workbook_to_sheets
    from backend.sidecar.state import get_state

    bays = get_state().project_data.get("bays", {})
    if not bays:
        return {"status": "erro", "mensagem": "Nenhum bay encontrado no projeto."}

    bay_data_list, skipped = build_export_payload(bays)

    if not bay_data_list:
        return {
            "status": "erro",
            "mensagem": "Nenhum bay com dados válidos para exportar.",
            "pulados": skipped,
        }

    try:
        workbook = ExcelProcessor().process_multiple_bays(bay_data_list)
    except Exception as e:
        log.exception("Erro ao gerar planilha multi-bay (Univer)")
        return {"status": "erro", "mensagem": str(e), "pulados": skipped}

    sheets = workbook_to_sheets(workbook)
    total = sum(len(b["results"]) for b in bay_data_list)
    log.info(
        "export_all_bays_univer: %d bays, %d conexões, %d aba(s)",
        len(bay_data_list),
        total,
        len(sheets),
    )
    return {
        "status": "sucesso",
        "bays": len(bay_data_list),
        "total": total,
        "pulados": skipped,
        "sheets": sheets,
        "mensagem": (
            f"Saída gerada: {len(bay_data_list)} bay(s), {total} conexões, "
            f"{len(sheets)} aba(s)."
        ),
    }


# --- export_docx ---


def _resolve_docx_template(template_path: str | None = None) -> str | None:
    """Modelo .docx do relatório: caminho explícito → primeiro .docx de Modules/docs."""
    from backend.core.utils.paths import get_docs_dir

    if template_path and os.path.isfile(template_path):
        return template_path

    docs_dir = get_docs_dir()
    if not os.path.isdir(docs_dir):
        return None
    candidates = sorted(
        name for name in os.listdir(docs_dir) if name.lower().endswith(".docx")
    )
    return os.path.join(docs_dir, candidates[0]) if candidates else None


def export_docx(
    bay_id: str | None = None,
    template_path: str | None = None,
    output_path: str | None = None,
) -> dict:
    """Gera o relatório ``.docx`` com as tabelas de equipamento dos bays.

    Mesmo pipeline da exportação ``.xlsx`` (``build_export_payload`` +
    ``ExcelProcessor.process_multiple_bays``), mas o destino é um modelo Word
    de ``Modules/docs``: cada chave ``{{ ... }}`` do modelo recebe a tabela da
    aba homônima do workbook do bay (``processing/docx/docx_exporter``).

    Args:
        bay_id: Restringe o relatório a um bay (padrão: todos os bays).
        template_path: Modelo ``.docx`` com as chaves (padrão: primeiro
            ``.docx`` de ``Modules/docs``).
        output_path: Caminho do arquivo gerado (padrão: last_directory).

    Relatório pronto, o arquivo é aberto no aplicativo padrão do sistema (Word)
    — o backend roda na máquina do usuário. Se a abertura falhar, ``aberto``
    fica ``False`` e ``aviso`` traz o motivo; a exportação continua válida (o
    arquivo está no disco e baixável por ``GET /api/download``).

    Retorna:
      {
        "status": "sucesso",
        "arquivo": "J:\\...\\Relatorio_Equipamentos.docx",
        "bays": 3,
        "tabelas": 12,
        "aberto": True,
        "aviso": None,
        "chaves_inseridas": {"disjuntor": ["Bay 1", ...]},
        "chaves_sem_tabela": ["xxx"],
        "bays_sem_tabela": {"xxx": ["Bay 2"]},
        "pulados": [{"bay": ..., "motivo": ...}],
        "mensagem": "Relatório gerado: ...",
      }
    """
    from backend.core.utils.file_lock_checker import is_file_locked
    from backend.core.utils.file_opener import open_path
    from backend.core.utils.file_resolver import resolve_output_path
    from backend.core.utils.paths import get_docs_dir
    from backend.processing.docx import docx_exporter
    from backend.processing.excel_processor import ExcelProcessor
    from backend.processing.workbook.multi_bay_payload import build_export_payload
    from backend.sidecar.state import get_state

    if docx_exporter._Document is None:
        return {
            "status": "erro",
            "mensagem": (
                "python-docx não está instalado. "
                "Rode: pip install -r requirements.txt"
            ),
        }

    bays = get_state().project_data.get("bays", {})
    if not bays:
        return {"status": "erro", "mensagem": "Nenhum bay encontrado no projeto."}

    template = _resolve_docx_template(template_path)
    if not template:
        return {
            "status": "erro",
            "mensagem": (
                "Modelo .docx não encontrado. Coloque um arquivo .docx em "
                f"{get_docs_dir()} ou informe template_path."
            ),
        }

    bay_data_list, skipped = build_export_payload(bays)
    if bay_id:
        bay_data_list = [bay for bay in bay_data_list if bay.get("name") == bay_id]
        if not bay_data_list:
            return {
                "status": "erro",
                "mensagem": f"Bay '{bay_id}' não encontrado para exportar.",
                "pulados": skipped,
            }

    if not bay_data_list:
        return {
            "status": "erro",
            "mensagem": "Nenhum bay com dados válidos para exportar.",
            "pulados": skipped,
        }

    try:
        ExcelProcessor().process_multiple_bays(bay_data_list)
    except Exception as e:  # noqa: BLE001 - a API não pode derrubar com traceback
        log.exception("Erro ao gerar os workbooks para o .docx")
        return {"status": "erro", "mensagem": str(e), "pulados": skipped}

    bay_workbooks = [
        (bay["name"], bay["_workbook"])
        for bay in bay_data_list
        if "_workbook" in bay
    ]
    if not bay_workbooks:
        return {
            "status": "erro",
            "mensagem": "Nenhum bay pôde ser processado.",
            "pulados": skipped,
        }

    output = resolve_output_path("Relatorio_Equipamentos", ".docx", output_path)
    if is_file_locked(str(output)):
        return {
            "status": "arquivo_aberto",
            "arquivo": str(output),
            "mensagem": (
                f"O arquivo '{output.name}' está aberto em outro programa. "
                "Feche-o e tente novamente."
            ),
            "pulados": skipped,
        }

    try:
        stats = docx_exporter.build_docx(template, str(output), bay_workbooks)
    except Exception as e:  # noqa: BLE001 - erro do python-docx/modelo
        log.exception("Erro ao gerar o relatório .docx")
        return {"status": "erro", "mensagem": str(e), "pulados": skipped}

    # O relatório abre sozinho assim que fica pronto. A abertura é best-effort:
    # uma máquina sem aplicativo padrão não invalida a exportação.
    aberto = False
    aviso = None
    try:
        open_path(output)
        aberto = True
    except Exception as exc:  # noqa: BLE001 - o arquivo já está no disco
        aviso = f"Não foi possível abrir o relatório: {exc}"
        log.warning("export_docx: falha ao abrir %s: %s", output, exc)

    total = stats["tabelas"]
    mensagem = (
        f"Relatório gerado: {output.name} "
        f"({len(bay_workbooks)} bay(s), {total} tabela(s)"
    )
    if stats["chaves_sem_tabela"]:
        mensagem += (
            f"; sem tabela: {', '.join(stats['chaves_sem_tabela'])}"
        )
    mensagem += ")"
    if aberto:
        mensagem += " — aberto no aplicativo padrão."
    elif aviso:
        mensagem += f" — {aviso}"

    log.info(
        "export_docx: %d bays, %d tabelas -> %s",
        len(bay_workbooks),
        total,
        output,
    )
    return {
        "status": "sucesso",
        "arquivo": str(output),
        "bays": len(bay_workbooks),
        "tabelas": total,
        "aberto": aberto,
        "aviso": aviso,
        "chaves_inseridas": stats["chaves_inseridas"],
        "chaves_sem_tabela": stats["chaves_sem_tabela"],
        "bays_sem_tabela": stats["bays_sem_tabela"],
        "pulados": skipped,
        "mensagem": mensagem,
    }


def export_docx_univer(
    bay_id: str | None = None,
    template_path: str | None = None,
) -> dict:
    """Gera o relatório do modelo Word EM MEMÓRIA para o Univer Doc.

    Mesmo pipeline de ``export_docx`` (``build_export_payload`` +
    ``ExcelProcessor.process_multiple_bays``), mas sem gravar o arquivo ``.docx``
    no disco nem abrir no Word. Os elementos do documento (parágrafos do modelo,
    títulos de bay e tabelas dos equipamentos com estilos, alinhamentos, bordas
    e cores) são devolvidos prontos para montagem direta no Univer Doc pelo
    frontend.
    """
    from backend.core.utils.paths import get_docs_dir
    from backend.processing.docx import docx_exporter
    from backend.processing.excel_processor import ExcelProcessor
    from backend.processing.workbook.multi_bay_payload import build_export_payload
    from backend.sidecar.state import get_state

    if docx_exporter._Document is None:
        return {
            "status": "erro",
            "mensagem": (
                "python-docx não está instalado. "
                "Rode: pip install -r requirements.txt"
            ),
        }

    bays = get_state().project_data.get("bays", {})
    if not bays:
        return {"status": "erro", "mensagem": "Nenhum bay encontrado no projeto."}

    template = _resolve_docx_template(template_path)
    if not template:
        return {
            "status": "erro",
            "mensagem": (
                "Modelo .docx não encontrado. Coloque um arquivo .docx em "
                f"{get_docs_dir()} ou informe template_path."
            ),
        }

    bay_data_list, skipped = build_export_payload(bays)
    if bay_id:
        bay_data_list = [bay for bay in bay_data_list if bay.get("name") == bay_id]
        if not bay_data_list:
            return {
                "status": "erro",
                "mensagem": f"Bay '{bay_id}' não encontrado para exportar.",
                "pulados": skipped,
            }

    if not bay_data_list:
        return {
            "status": "erro",
            "mensagem": "Nenhum bay com dados válidos para exportar.",
            "pulados": skipped,
        }

    try:
        ExcelProcessor().process_multiple_bays(bay_data_list)
    except Exception as e:  # noqa: BLE001
        log.exception("Erro ao gerar os workbooks para o Univer Doc")
        return {"status": "erro", "mensagem": str(e), "pulados": skipped}

    bay_workbooks = [
        (bay["name"], bay["_workbook"])
        for bay in bay_data_list
        if "_workbook" in bay
    ]
    if not bay_workbooks:
        return {
            "status": "erro",
            "mensagem": "Nenhum bay pôde ser processado.",
            "pulados": skipped,
        }

    try:
        data = docx_exporter.docx_to_univer(template, bay_workbooks)
    except Exception as e:  # noqa: BLE001
        log.exception("Erro ao montar o documento Univer a partir do modelo")
        return {"status": "erro", "mensagem": str(e), "pulados": skipped}

    total = data.get("tabelas", 0)
    sem_tabela = data.get("chaves_sem_tabela", [])
    mensagem = (
        f"Documento montado do modelo '{data.get('template', 'doc')}': "
        f"{len(bay_workbooks)} bay(s), {total} tabela(s)"
    )
    if sem_tabela:
        mensagem += f" (sem tabela: {', '.join(sem_tabela)})"
    mensagem += " — carregado no Univer Doc."

    log.info(
        "export_docx_univer: %d bays, %d tabelas, %d elementos",
        len(bay_workbooks),
        total,
        len(data.get("elements", [])),
    )

    data.update({
        "bays": len(bay_workbooks),
        "pulados": skipped,
        "mensagem": mensagem,
    })
    return data


# --- get_pontos ---


def get_pontos(bay_id: str, bay_data: dict | None = None) -> dict:
    """Retorna os pontos do bay (de bay_data se fornecido, senao DEFAULT_POINTS)."""
    if bay_data and "points" in bay_data:
        pontos = []
        for name, info in bay_data["points"].items():
            if isinstance(info, dict):
                pontos.append(
                    {
                        "nome": name,
                        "selecionado": info.get("selected", False),
                        "fases": info.get("phases", 1),
                        "coordenadas": info.get("coordinates"),
                        "distancia_extra": info.get("extra_distance", 0.0),
                    }
                )
        return {
            "status": "sucesso",
            "bay_id": bay_id,
            "pontos": pontos,
            "total": len(pontos),
        }

    # Fallback: pontos padrão
    pontos = []
    for name, info in DEFAULT_POINTS.items():
        pontos.append(
            {
                "nome": name,
                "selecionado": False,
                "fases": info.get("phases", 1),
                "coordenadas": info.get("point"),
                "distancia_extra": info.get("extra_distance", 0.0),
            }
        )
    return {
        "status": "sucesso",
        "bay_id": bay_id,
        "pontos": pontos,
        "total": len(pontos),
        "fonte": "padrao",
    }  # --- duplicar_bay ---


def duplicar_bay(bay_id: str, new_label: str, bay_data: dict | None = None) -> dict:
    """Duplica um bay (usa bay_data se fornecido, senao busca do estado)."""
    from backend.sidecar.state import get_state

    state = get_state()

    if bay_data:
        source_data = bay_data
    else:
        source_data = state.get_bay(bay_id) or {}

    if not source_data:
        return {
            "status": "erro",
            "mensagem": f"Bay '{bay_id}' não encontrado e nenhum dado fornecido",
        }

    result = state.duplicate_bay(bay_id, new_label)
    return result


# --- update_last_directory ---
def update_last_directory(path: str) -> dict:
    """Registra o diretorio de ``path`` no config.json do NEXUS."""
    from backend.core.config import set_last_directory

    saved = set_last_directory(path)
    if saved:
        return {
            "status": "sucesso",
            "last_directory": saved,
            "mensagem": "Diretório registrado com sucesso",
        }
    return {
        "status": "erro",
        "mensagem": f"Não foi possível registrar o diretório de '{path}'.",
    }


# --- export_distances_sheet ---
def export_distances_sheet(
    bay_id: str,
    distances: list[dict] | None = None,
    output_path: str | None = None,
) -> dict:
    """Gera uma planilha Excel com a aba "Distâncias" do bay.

    Recebe o array de distâncias serializado pelo frontend:
      [{ "id": "dist-1", "origem": "PAINEL", "destino": "DISJUNTOR", "distancia": "12.5" }, ...]

    As linhas são reordenadas na ordem canônica dos pontos (a planilha é
    o consumidor final da ordenação — não depende do sort do frontend).

    Args:
        bay_id: ID do bay.
        distances: Distâncias no formato [{id, origem, destino, distancia}].
        output_path: Caminho completo do arquivo .xlsx escolhido pelo
            usuário no diálogo "Salvar como". Se ausente, salva no
            last_directory com o nome do bay.

    Retorna:
      {
        "status": "sucesso",
        "arquivo": "J:\\...\\Bay 3.xlsx",
        "total": 5,
      }
    """
    distances = distances or []

    from backend.core.bay.point_order import (
        default_names_from_points,
        sort_distance_rows,
    )
    from backend.core.utils.file_resolver import resolve_output_path
    from backend.processing.workbook.distances_sheet import build_distances_workbook
    from backend.sidecar.state import get_state

    # Ordena as linhas na ordem canônica dos pontos: o backend é o
    # consumidor final da planilha, então a ordem do arquivo não depende
    # do sort do frontend (default_name no point resolve pontos renomeados).
    bay_data = get_state().get_bay(bay_id)
    points = bay_data.get("points") if isinstance(bay_data, dict) else {}
    default_names = default_names_from_points(
        points if isinstance(points, dict) else {},
    )
    distances = sort_distance_rows(distances, default_names)

    # Resolve o diretório/nome final (output_path explícito ou last_directory)
    # e monta o workbook (estilos/linhas) em processing/workbook/distances_sheet.
    output_path = resolve_output_path(bay_id or "bay", ".xlsx", output_path)

    from backend.core.utils.file_lock_checker import is_file_locked

    if is_file_locked(str(output_path)):
        return {
            "status": "arquivo_aberto",
            "arquivo": str(output_path),
            "mensagem": (
                f"O arquivo '{output_path.name}' está aberto em outro programa. "
                "Feche-o e tente novamente."
            ),
        }

    wb = build_distances_workbook(distances)
    wb.save(str(output_path))

    return {
        "status": "sucesso",
        "arquivo": str(output_path),
        "total": len(distances),
        "mensagem": f"Planilha exportada: {output_path.name} ({len(distances)} distâncias)",
    }

