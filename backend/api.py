"""API HTTP local do Univer — ponte para o núcleo headless do sidecar.

Este módulo expõe o núcleo headless (``backend.sidecar.service``) via
HTTP + JSON, para que o frontend React/Vite (http://localhost:5173) leia o
projeto e monte a planilha na tela.

Uso::

    python -m backend.api            # a partir da raiz do app (univer-app/)
    python api.py                    # a partir de backend/

Variáveis de ambiente::

    UNIVER_API_HOST   (default: 127.0.0.1)
    UNIVER_API_PORT   (default: 8000)

Endpoints::

    GET  /api/health                 estado + modo (backend | demo)
    GET  /api/project                projeto em memória
    POST /api/project/new            cria um projeto vazio
    POST /api/project/load           carrega um .md do disco
    POST /api/project/pick           abre o diálogo "Abrir arquivo" e devolve o caminho
    POST /api/project/save           salva o projeto no disco
    GET  /api/sheet/preview          linhas da planilha, um bloco por bay
    POST /api/bays/{bay}/cables      grava as edições da grade e o .md (write-through)
    POST /api/export/all-bays        gera o .xlsx (templates + openpyxl)
    POST /api/export/all-bays/univer gera o .xlsx em memória e devolve as abas
    POST /api/export/docx            gera o relatório .docx e abre no aplicativo padrão
    POST /api/export/distances       gera o .xlsx da aba Distâncias
    GET  /api/download?path=...      baixa um arquivo gerado pelo backend

Modo demo
---------
Quando o núcleo headless não puder ser importado, a API sobe em **modo demo**, servindo
um projeto de exemplo em memória — suficiente para desenvolver e ver o
frontend, mas sem gravar planilhas reais.
"""

from __future__ import annotations

import os
import sys
from typing import Any

# Garante a raiz do app (o diretório pai de ``backend``) e o próprio diretório
# no sys.path — o mesmo arranjo de ``main.py``.
_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_UNIVER_ROOT = os.path.dirname(_BACKEND_DIR)
for _path in (_UNIVER_ROOT, _BACKEND_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

try:
    from fastapi import FastAPI, HTTPException, Query
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse
    from pydantic import BaseModel, Field
except ImportError as exc:  # pragma: no cover - depende do ambiente
    raise SystemExit(
        "FastAPI/uvicorn não instalados. Rode: pip install -r requirements.txt"
    ) from exc

API_VERSION = "1.0.0"
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# --- Núcleo headless (lazy) ------------------------------------------------

_SERVICE: dict[str, Any] = {"loaded": False, "service": None, "error": None}


def get_service() -> tuple[Any | None, str | None]:
    """Importa ``backend.sidecar.service`` uma única vez (tolerante a falhas).

    Returns:
        ``(service, error)`` — ``service`` é ``None`` quando o núcleo não
        está disponível e ``error`` descreve o motivo.
    """
    if not _SERVICE["loaded"]:
        try:
            from backend.sidecar import service as _service

            _SERVICE.update(loaded=True, service=_service, error=None)
        except Exception as exc:  # noqa: BLE001 - qualquer falha cai no demo
            _SERVICE.update(
                loaded=True,
                service=None,
                error=f"{type(exc).__name__}: {exc}",
            )
    return _SERVICE["service"], _SERVICE["error"]


# --- Projeto de exemplo (modo demo) ----------------------------------------

_DEMO_PROJECT: dict[str, Any] = {
    "version": "2.0",
    "created_at": "2026-01-01T00:00:00+00:00",
    "last_modified": None,
    "point_aliases_default": {},
    "bays": {
        "LT - 230kV": {
            "bay_type": "LT",
            "voltage_level": "230kV",
            "measurement_type": "Costura",
            "sincronizador_enabled": True,
            "point_aliases": {},
            "points": {
                "PAINEL": {"selected": True, "phases": 1, "default_name": "PAINEL"},
                "CAIXA TC": {"selected": True, "phases": 3, "default_name": "CAIXA TC"},
                "CAIXA TP": {"selected": True, "phases": 3, "default_name": "CAIXA TP"},
                "DISJUNTOR": {"selected": True, "phases": 1, "default_name": "DISJUNTOR"},
                "SECCIONADORA-1": {
                    "selected": True,
                    "phases": 1,
                    "default_name": "SECCIONADORA",
                },
            },
            "cable_data": [
                {
                    "id": "1",
                    "funcao": "Circ. Comando (Alim. 125 Vcc)",
                    "bitola": "2,5 mm²",
                    "origem": "PAINEL",
                    "destino": "CAIXA TC",
                    "distancia": "12.5",
                },
                {
                    "id": "2",
                    "funcao": "Circ. Comando (Alim. 125 Vcc)",
                    "bitola": "2,5 mm²",
                    "origem": "CAIXA TC",
                    "destino": "DISJUNTOR",
                    "distancia": "8.3",
                },
                {
                    "id": "3",
                    "funcao": "Ilum./Aquec./Tom.",
                    "bitola": "4 mm²",
                    "origem": "PAINEL",
                    "destino": "DISJUNTOR",
                    "distancia": "14.2",
                },
                {
                    "id": "4",
                    "funcao": "Motores dos Equipamentos",
                    "bitola": "6 mm²",
                    "origem": "DISJUNTOR",
                    "destino": "SECCIONADORA-1",
                    "distancia": "3.4",
                },
            ],
            "distances": [
                {"id": "dist-1", "origem": "PAINEL", "destino": "CAIXA TC", "distancia": "12.5"},
                {"id": "dist-2", "origem": "CAIXA TC", "destino": "DISJUNTOR", "distancia": "8.3"},
                {"id": "dist-3", "origem": "PAINEL", "destino": "DISJUNTOR", "distancia": "14.2"},
                {
                    "id": "dist-4",
                    "origem": "DISJUNTOR",
                    "destino": "SECCIONADORA-1",
                    "distancia": "3.4",
                },
            ],
        },
        "BARRA - 500kV": {
            "bay_type": "BARRA",
            "voltage_level": "500kV",
            "measurement_type": "Sem Alim.",
            "sincronizador_enabled": False,
            "point_aliases": {},
            "points": {
                "PAINEL": {"selected": True, "phases": 1, "default_name": "PAINEL"},
                "DISJUNTOR": {"selected": True, "phases": 1, "default_name": "DISJUNTOR"},
            },
            "cable_data": [
                {
                    "id": "1",
                    "funcao": "Circ. Comando (Alim. 125 Vcc)",
                    "bitola": "2,5 mm²",
                    "origem": "PAINEL",
                    "destino": "DISJUNTOR",
                    "distancia": "21.7",
                },
            ],
            "distances": [
                {"id": "dist-1", "origem": "PAINEL", "destino": "DISJUNTOR", "distancia": "21.7"},
            ],
        },
    },
}


def _demo_bay_payloads() -> list[dict[str, Any]]:
    """Converte o projeto de exemplo no formato aceito por ``_bay_to_grid``."""
    payloads: list[dict[str, Any]] = []
    for bay_id, bay in _DEMO_PROJECT["bays"].items():
        payloads.append(
            {
                "name": bay_id,
                "type": bay.get("bay_type", ""),
                "voltage": bay.get("voltage_level", ""),
                "measurement_type": bay.get("measurement_type", ""),
                "seccionadora_count": len(
                    [p for p in bay.get("points", {}) if str(p).startswith("SECCIONADORA")]
                ),
                "cable_data": bay.get("cable_data"),
                "results": [
                    (d.get("origem"), d.get("destino"), d.get("distancia"))
                    for d in bay.get("distances", [])
                ],
            }
        )
    return payloads


# --- Modelos de entrada ----------------------------------------------------


class RowsPayload(BaseModel):
    """Linhas da grade (CableGaugeRow) editadas no frontend."""

    rows: list[dict[str, Any]] = Field(default_factory=list)


class ExportPayload(BaseModel):
    output_path: str | None = None


class DistancesExportPayload(BaseModel):
    bay_id: str = ""
    distances: list[dict[str, Any]] = Field(default_factory=list)
    output_path: str | None = None


class DocxExportPayload(BaseModel):
    """Relatório .docx: modelo Word com as chaves ``{{ ... }}``."""

    bay_id: str | None = None
    template_path: str | None = None
    output_path: str | None = None


class DocxUniverPayload(BaseModel):
    """Parâmetros para carregar o modelo Word no Univer Doc."""

    bay_id: str | None = None
    template_path: str | None = None


class LoadProjectPayload(BaseModel):
    path: str


class SaveProjectPayload(BaseModel):
    path: str | None = None


# --- Helpers ---------------------------------------------------------------


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _cable_rows(cable_data: list[Any]) -> list[dict[str, str]]:
    """Linhas a partir do ``cable_data`` do bay (já editado pelo usuário)."""
    rows: list[dict[str, str]] = []
    for index, cable in enumerate(cable_data, 1):
        if not isinstance(cable, dict):
            continue
        rows.append(
            {
                "id": _text(cable.get("id") or index),
                "funcao": _text(cable.get("funcao")),
                "bitola": _text(cable.get("bitola") or cable.get("novaBitola")),
                "origem": _text(cable.get("origin") or cable.get("origem")),
                "destino": _text(cable.get("destination") or cable.get("destino")),
                "distancia": _text(cable.get("distancia")),
            }
        )
    return rows


def _db_rows(bay_id: str, bay_data: dict[str, Any]) -> list[dict[str, Any]]:
    """Linhas padrão do banco SQLite para o bay (trazem função e bitola).

    É o mesmo ``collect_cabos_from_db`` que ``build_export_payload`` usa, mas
    aqui preservamos id/função/bitola — sem isso a grade mostraria as colunas
    vazias e um "salvar" sobrescreveria o ``cable_data`` com dados incompletos.
    """
    try:
        from backend.processing.cables.db_cable_fetcher import collect_cabos_from_db

        status, rows, _, _ = collect_cabos_from_db(bay_data, bay_id)
    except Exception:  # noqa: BLE001 - preview não pode derrubar a chamada
        return []
    return rows if status == "sucesso" else []


def _distance_rows(bay_data: dict[str, Any] | None) -> list[dict[str, str]]:
    """Linhas da chave ``distances`` do ``.md`` (a tabela "Distâncias" do bay).

    A lista é apenas lida do arquivo: nada é derivado do ``cable_data`` — o
    mesmo contrato de ``_order_bay_distances`` no sidecar.
    """
    distances = (bay_data or {}).get("distances")
    if not isinstance(distances, list):
        return []

    rows: list[dict[str, str]] = []
    for index, item in enumerate(distances, 1):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": _text(item.get("id") or index),
                "origem": _text(item.get("origem") or item.get("origin")),
                "destino": _text(item.get("destino") or item.get("destination")),
                "distancia": _text(item.get("distancia")),
            }
        )
    return rows


def _distances_by_pair(bay_data: dict[str, Any]) -> dict[Any, float]:
    """Distâncias salvas no ``.md`` indexadas por par não-orientado."""
    try:
        from backend.processing.workbook.multi_bay_payload import bay_distance_map

        return bay_distance_map(bay_data)
    except Exception:  # noqa: BLE001
        return {}


def _bay_to_grid(bay: dict[str, Any], bay_data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Achata um payload de bay exportável no formato consumido pela grade.

    A ordem de preferência espelha a do exportador: ``cable_data`` do ``.md``
    quando existir; senão as linhas padrão do banco (que têm id/função/bitola)
    com a distância salva no bay; por último os pares crus de ``results``.
    """
    rows: list[dict[str, str]] = []
    cable_data = bay.get("cable_data")

    if isinstance(cable_data, list) and cable_data:
        rows = _cable_rows(cable_data)
    else:
        bay_data = bay_data or {}
        distances = _distances_by_pair(bay_data)
        present: set[frozenset] = set()

        for index, row in enumerate(_db_rows(_text(bay.get("name")), bay_data), 1):
            origem = _text(row.get("origem"))
            destino = _text(row.get("destino"))
            pair = frozenset((origem, destino))
            present.add(pair)
            distancia = row.get("distancia")
            if distancia is None or distancia == "":
                distancia = distances.get(pair)
            rows.append(
                {
                    "id": _text(row.get("id") or index),
                    "funcao": _text(row.get("funcao")),
                    "bitola": _text(row.get("novaBitola")),
                    "origem": origem,
                    "destino": destino,
                    "distancia": _text(distancia),
                }
            )

        # Pares que a exportação acrescenta (distâncias salvas sem linha no
        # banco) — sem função/bitola conhecidos. Mesma união de
        # ``build_export_payload``, para a grade refletir a planilha.
        for result in bay.get("results") or []:
            origem, destino, distancia = (list(result) + ["", "", ""])[:3]
            pair = frozenset((_text(origem), _text(destino)))
            if pair in present:
                continue
            present.add(pair)
            rows.append(
                {
                    "id": str(len(rows) + 1),
                    "funcao": "",
                    "bitola": "",
                    "origem": _text(origem),
                    "destino": _text(destino),
                    "distancia": _text(distancia),
                }
            )

    return {
        "bay_id": str(bay.get("name") or ""),
        "tipo": str(bay.get("type") or ""),
        "tensao": str(bay.get("voltage") or ""),
        "medicao": str(bay.get("measurement_type") or ""),
        "seccionadoras": int(bay.get("seccionadora_count") or 0),
        "linhas": rows,
        # Chave ``distances`` do ``.md`` do bay — independente do ``cable_data``.
        "distancias": _distance_rows(bay_data),
    }


def _demo_unavailable(service_error: str | None) -> dict[str, Any]:
    """Resposta padrão das ações que só existem com o backend completo."""
    return {
        "status": "erro",
        "modo": "demo",
        "mensagem": (
            "Ação indisponível no modo demo: o núcleo headless do backend não "
            "pôde ser importado (backend.core ausente)."
        ),
        "erro_backend": service_error,
    }


def _demo_project() -> dict[str, Any]:
    return _DEMO_PROJECT


def _project_data() -> tuple[dict[str, Any], str]:
    """Devolve ``(project_data, modo)``."""
    service, _ = get_service()
    if service is None:
        return _demo_project(), "demo"
    result = service.get_project_data()
    if result.get("status") != "sucesso":
        raise HTTPException(status_code=500, detail=result.get("mensagem", "Falha ao ler o projeto."))
    return result.get("data", {}), "backend"


# --- Aplicação -------------------------------------------------------------

app = FastAPI(title="Univer API", version=API_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Estado da ponte HTTP e modo de operação."""
    service, error = get_service()
    return {
        "status": "ok",
        "modo": "backend" if service else "demo",
        "erro_backend": error,
        "versao": API_VERSION,
    }


@app.get("/api/project")
def get_project() -> dict[str, Any]:
    """Projeto ativo (bays, points, cable_data, distâncias)."""
    data, modo = _project_data()
    return {"status": "sucesso", "modo": modo, "data": data}


@app.post("/api/project/new")
def new_project() -> dict[str, Any]:
    """Cria um projeto vazio."""
    service, error = get_service()
    if service is None:
        return _demo_unavailable(error)
    return service.new_project()


@app.post("/api/project/load")
def load_project(payload: LoadProjectPayload) -> dict[str, Any]:
    """Carrega um projeto ``.md`` do disco."""
    service, error = get_service()
    if service is None:
        return _demo_unavailable(error)
    return service.load_project(payload.path)


@app.post("/api/project/pick")
def pick_project() -> dict[str, Any]:
    """Abre o diálogo nativo "Abrir arquivo" e devolve o caminho escolhido.

    O backend roda na máquina do usuário, então o diálogo do sistema é a forma
    de escolher o projeto sem digitar o caminho. O caminho é registrado como
    ``last_directory`` (o próximo diálogo abre na mesma pasta) e é o que o
    frontend envia para ``POST /api/project/load``.

    Retorna ``{"status": "cancelado"}`` quando o usuário fecha o diálogo sem
    escolher, ou ``{"status": "erro"}`` quando o diálogo não está disponível.
    """
    from backend.core.config import get_last_directory, set_last_directory
    from backend.core.utils.file_resolver import pick_open_path

    try:
        path = pick_open_path(
            title="Abrir projeto Univer (.md)",
            initial_dir=get_last_directory() or None,
        )
    except RuntimeError as exc:
        return {"status": "erro", "mensagem": str(exc)}

    if not path:
        return {"status": "cancelado", "mensagem": "Nenhum arquivo selecionado."}

    set_last_directory(path)
    return {"status": "sucesso", "path": path}


@app.post("/api/project/save")
def save_project(payload: SaveProjectPayload) -> dict[str, Any]:
    """Salva o projeto no disco (caminho opcional)."""
    service, error = get_service()
    if service is None:
        return _demo_unavailable(error)
    return service.save_project(payload.path or "")


@app.get("/api/sheet/preview")
def sheet_preview() -> dict[str, Any]:
    """Conexões por bay, prontas para a grade do frontend.

    Cada bay devolve duas listas independentes do ``.md``: ``linhas`` (a chave
    ``cable_data``) e ``distancias`` (a chave ``distances``).

    Usa o MESMO ``build_export_payload`` da exportação ``.xlsx``: as conexões,
    as distâncias e os bays pulados (com motivo) são exatamente os da
    exportação.

    Atenção: a planilha ``.xlsx`` NÃO tem uma linha por conexão. As linhas vêm
    do template do bay (``Modules/Sheets/<TIPO> - <kV>.xlsx``, uma aba por
    equipamento) e as conexões só fornecem a distância de cada par. Por isso,
    para um mesmo par (ex.: ``DISJUNTOR → PAINEL``) o ``.xlsx`` traz todas as
    linhas de cabo do template, enquanto esta grade traz as conexões do
    banco/``.md``.

    Um par também pode aparecer várias vezes aqui — não é duplicata: a
    identidade de um cabo é ``(tipo_conexao, origem, destino, funcao)``.
    """
    service, error = get_service()
    if service is None:
        demo_bays = _demo_project().get("bays", {})
        grid = []
        for payload in _demo_bay_payloads():
            bay_data = demo_bays.get(payload.get("name"))
            grid.append(_bay_to_grid(payload, bay_data if isinstance(bay_data, dict) else None))
        return {
            "status": "sucesso",
            "modo": "demo",
            "erro_backend": error,
            "bays": grid,
            "ignorados": [],
        }

    data, _ = _project_data()
    bays = data.get("bays", {})
    if not bays:
        return {"status": "sucesso", "modo": "backend", "bays": [], "ignorados": []}

    from backend.processing.workbook.multi_bay_payload import build_export_payload

    bay_list, skipped = build_export_payload(bays)
    grid = []
    for bay in bay_list:
        bay_data = bays.get(bay.get("name"))
        grid.append(_bay_to_grid(bay, bay_data if isinstance(bay_data, dict) else None))

    return {
        "status": "sucesso",
        "modo": "backend",
        "bays": grid,
        "ignorados": skipped,
    }


@app.post("/api/bays/{bay_id}/cables")
def save_bay_cables(bay_id: str, payload: RowsPayload) -> dict[str, Any]:
    """Grava as linhas editadas na grade como ``cable_data`` do bay."""
    service, error = get_service()
    if service is None:
        bay = _DEMO_PROJECT["bays"].get(bay_id)
        if bay is None:
            return {"status": "erro", "mensagem": f"Bay '{bay_id}' não encontrado."}
        bay["cable_data"] = [
            {
                "id": str(row.get("id") or index),
                "funcao": str(row.get("funcao") or ""),
                "bitola": str(row.get("novaBitola") or row.get("bitola") or ""),
                "origem": str(row.get("origem") or ""),
                "destino": str(row.get("destino") or ""),
                "distancia": str(row.get("distancia") or ""),
            }
            for index, row in enumerate(payload.rows, 1)
        ]
        return {
            "status": "sucesso",
            "modo": "demo",
            "bay_id": bay_id,
            "total": len(bay["cable_data"]),
            "mensagem": "Salvo apenas em memória (modo demo).",
        }
    return service.save_cable_data(bay_id, payload.rows)


@app.post("/api/export/all-bays")
def export_all_bays(payload: ExportPayload) -> dict[str, Any]:
    """Gera o ``.xlsx`` de todos os bays e devolve o caminho do arquivo."""
    service, error = get_service()
    if service is None:
        return _demo_unavailable(error)
    return service.export_all_bays_sheet(payload.output_path)


@app.post("/api/export/all-bays/univer")
def export_all_bays_univer() -> dict[str, Any]:
    """Gera a planilha dos bays EM MEMÓRIA e devolve as abas para o Univer.

    O frontend usa este endpoint no botão "Carregar saída": em vez de baixar o
    ``.xlsx``, a saída da exportação (templates + openpyxl) é montada na tela.
    Cada aba sai com valores, mesclagens, larguras e visibilidade — ver
    ``processing/workbook/univer_snapshot.py``.
    """
    service, error = get_service()
    if service is None:
        return _demo_unavailable(error)
    return service.export_all_bays_univer()


@app.post("/api/export/docx")
def export_docx(payload: DocxExportPayload) -> dict[str, Any]:
    """Gera o relatório ``.docx`` com as tabelas de cada equipamento.

    Abre o modelo de ``Modules/docs`` e troca cada chave ``{{ ... }}`` pela
    tabela da aba correspondente do workbook do bay (``sidecar.service.
    export_docx`` → ``processing/docx/docx_exporter``). O arquivo sai no
    last_directory, é **aberto no aplicativo padrão do sistema** (Word) e
    continua baixável por ``GET /api/download``.
    """
    service, error = get_service()
    if service is None:
        return _demo_unavailable(error)
    return service.export_docx(
        bay_id=payload.bay_id,
        template_path=payload.template_path,
        output_path=payload.output_path,
    )


def _demo_docx_univer() -> dict[str, Any]:
    """Gera dados de exemplo para o Univer Doc no modo demo."""
    return {
        "status": "sucesso",
        "modo": "demo",
        "template": "modelo_teste.docx",
        "bays": 2,
        "tabelas": 2,
        "mensagem": "Documento de exemplo carregado no Univer Doc (modo demo).",
        "elements": [
            {
                "type": "heading",
                "text": "Bay: LT - 230kV",
                "style": {"bold": True, "fontSize": 12, "color": "#0f172a"},
            },
            {
                "type": "table",
                "tableId": "table_demo_disjuntor",
                "sheetName": "DISJUNTOR",
                "bayName": "LT - 230kV",
                "rowCount": 3,
                "colCount": 4,
                "columnWidths": [120.0, 160.0, 120.0, 80.0],
                "rows": [
                    [
                        {"text": "CABO", "bold": True, "align": "center", "bg": "#334155", "color": "#ffffff"},
                        {"text": "FUNÇÃO", "bold": True, "align": "center", "bg": "#334155", "color": "#ffffff"},
                        {"text": "DESTINO", "bold": True, "align": "center", "bg": "#334155", "color": "#ffffff"},
                        {"text": "METRAGEM (m)", "bold": True, "align": "center", "bg": "#334155", "color": "#ffffff"},
                    ],
                    [
                        {"text": "C-01", "align": "center", "bg": "#f8fafc"},
                        {"text": "Circ. Comando (Alim. 125 Vcc)", "align": "left", "bg": "#f8fafc"},
                        {"text": "DISJUNTOR", "align": "center", "bg": "#f8fafc"},
                        {"text": "8,30", "align": "center", "bg": "#f8fafc"},
                    ],
                    [
                        {"text": "C-02", "align": "center"},
                        {"text": "Ilum./Aquec./Tom.", "align": "left"},
                        {"text": "DISJUNTOR", "align": "center"},
                        {"text": "14,20", "align": "center"},
                    ],
                ],
                "merges": [],
            },
            {
                "type": "paragraph",
                "text": "Texto descritivo de exemplo mantido a partir do modelo de relatório.",
                "align": "left",
                "runs": [{"text": "Texto descritivo de exemplo mantido a partir do modelo de relatório."}],
            },
        ],
    }


@app.post("/api/export/docx/univer")
def export_docx_univer(payload: DocxUniverPayload | None = None) -> dict[str, Any]:
    """Gera o relatório Word EM MEMÓRIA e devolve os elementos formatados para o Univer Doc.

    O frontend usa este endpoint no botão "Carregar Doc": em vez de salvar o .docx no disco
    e abrir no Word, a formatação do modelo (Modules/docs/*.docx) com as tabelas preenchidas
    é carregada diretamente na tela no Univer Doc.
    """
    service, error = get_service()
    if service is None:
        return _demo_docx_univer()
    payload_data = payload or DocxUniverPayload()
    return service.export_docx_univer(
        bay_id=payload_data.bay_id,
        template_path=payload_data.template_path,
    )


@app.post("/api/export/distances")
def export_distances(payload: DistancesExportPayload) -> dict[str, Any]:
    """Gera o ``.xlsx`` da aba Distâncias de um bay."""
    service, error = get_service()
    if service is None:
        return _demo_unavailable(error)
    return service.export_distances_sheet(
        payload.bay_id, payload.distances, payload.output_path
    )


@app.get("/api/download")
def download(path: str = Query(..., description="Caminho do arquivo gerado.")) -> FileResponse:
    """Baixa um arquivo gerado pelo backend (ex.: a planilha exportada)."""
    real_path = os.path.abspath(path)
    if not os.path.isfile(real_path):
        raise HTTPException(status_code=404, detail=f"Arquivo não encontrado: {path}")
    return FileResponse(real_path, filename=os.path.basename(real_path))


def main() -> None:
    """Sobe o servidor HTTP local."""
    import uvicorn

    # Garante a semente do banco de costura em %LOCALAPPDATA%\\NEXUS — era
    # feito no startup do sidecar ZMQ (agora só a API HTTP existe).
    try:
        from backend.core.db import ensure_database

        ensure_database()
    except Exception:  # noqa: BLE001 - a API não pode falhar por causa do seed
        pass

    host = os.environ.get("UNIVER_API_HOST", "127.0.0.1")
    port = int(os.environ.get("UNIVER_API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
