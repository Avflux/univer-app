"""Geração do relatório ``.docx`` com as tabelas de equipamento dos bays.

O modelo (``Modules/docs/*.docx``) traz uma chave ``{{ ... }}`` em cada posição
onde deve entrar uma tabela — ex.: ``{{ seccionadora-1 }}``, ``{{ disjuntor }}``,
``{{ caixa }}``. Este módulo abre o modelo, localiza as chaves e insere ali a
tabela do equipamento, montada a partir da aba homônima do workbook do bay.

Cada bay tem uma aba por equipamento (``bay['_workbook']`` — o mesmo workbook
que vira a seção da aba do bay na exportação ``.xlsx``), então o mapeamento
chave → aba é direto (sem distinção de caixa/acentos/hífen):

============================  ====================
Chave do modelo               Aba do workbook
============================  ====================
``{{ seccionadora-1 }}``      ``SECCIONADORA-1``
``{{ tp }}`` / ``{{ tc }}``   ``TP`` / ``TC``
``{{ disjuntor }}``           ``DISJUNTOR``
``{{ costura }}``             ``COSTURA``
``{{ caixa }}``               ``CAIXA CA``
``{{ }}`` (vazia/``…``)       ``TOTAL`` (totais)
============================  ====================

O documento é único: cada chave recebe a tabela de **todos** os bays, na ordem
do projeto, com o título ``Bay: <nome>`` antes de cada tabela quando há mais
de um bay. O texto de exemplo que segue a chave é mantido — apenas o parágrafo
da chave é removido. Chaves sem tabela correspondente ficam no documento e são
relatórias em ``chaves_sem_tabela``.
"""

from __future__ import annotations

import os
import re
import unicodedata
from typing import Any, Sequence

from backend.core.logging.logger import get_logger
from backend.processing.workbook.bay_section_copier import DATA_COLUMN_WIDTHS

log = get_logger(__name__)

try:  # python-docx é dependência opcional: o erro fica claro em build_docx.
    from docx import Document as _Document
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Emu, Pt
except ImportError:  # pragma: no cover - depende do ambiente
    _Document = None  # type: ignore[assignment]

# --- Chaves do modelo -------------------------------------------------------

# A chave precisa ocupar o parágrafo inteiro (no modelo ela vem sozinha).
KEY_RE = re.compile(r"\{\{([^{}]*)\}\}")

# Chave normalizada → nomes possíveis da aba (testados na ordem).
KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "": ("TOTAL",),
    "total": ("TOTAL",),
    "totais": ("TOTAL",),
    "total do bay": ("TOTAL",),
    "caixa": ("CAIXA CA", "CAIXA DE DISTRIBUIÇÃO CA", "CAIXA"),
    "caixa ca": ("CAIXA CA", "CAIXA DE DISTRIBUIÇÃO CA"),
    "caixa de distribuicao ca": ("CAIXA CA", "CAIXA DE DISTRIBUIÇÃO CA"),
}

# Larguras usadas quando a aba não define a coluna (espelha a exportação).
_FALLBACK_COLUMN_WIDTH = 15.0


def normalize(text: Any) -> str:
    """Chave comparável: caixa alta sem acentos, pontuação vira espaço.

    ``seccionadora-1``, ``Seccionadora 1`` e ``SECCIONADORA--1`` normalizam
    para o mesmo valor, então a chave casa com o nome da aba.
    """
    decomposed = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^A-Za-z0-9]+", " ", stripped.upper()).split())


def find_key(paragraph_text: Any) -> str | None:
    """Extrai a chave de um parágrafo ``{{ ... }}`` (parágrafo inteiro).

    Returns:
        A chave cru (sem as chaves externas), ou ``None`` quando o parágrafo
        não é uma chave.
    """
    compact = " ".join(str(paragraph_text or "").split())
    match = KEY_RE.fullmatch(compact)
    if match is None:
        return None
    return match.group(1).strip()


def resolve_sheet_name(key: str, sheet_names: Sequence[str]) -> str | None:
    """Localiza a aba do equipamento para uma chave do modelo."""
    index = {normalize(name): name for name in sheet_names}
    normalized = normalize(key)

    if normalized in index:
        return index[normalized]

    for alias in KEY_ALIASES.get(normalized, ()):
        target = normalize(alias)
        if target in index:
            return index[target]

    # Prefixo único: ``seccionadora`` → ``SECCIONADORA-1`` (só se não for
    # ambíguo — ``seccionadora`` com duas abas não escolhe por conta própria).
    candidates = [
        name
        for norm, name in index.items()
        if norm.startswith(f"{normalized} ")
    ]
    if len(candidates) == 1:
        return candidates[0]
    return None


# --- Conversão aba do Excel → tabela Word -----------------------------------


def _used_range(worksheet: Any) -> tuple[int, int]:
    """Última linha/coluna com valor (células só formatadas não contam)."""
    max_row = 0
    max_col = 0
    for row in worksheet.iter_rows():
        for cell in row:
            if cell.value not in (None, ""):
                max_row = max(max_row, cell.row)
                max_col = max(max_col, cell.column)
    return max_row, max_col


def _cell_text(value: Any) -> str:
    """Texto da célula no Word (``0.00`` do Excel vira ``10,00``)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, float):
        return f"{value:.2f}".replace(".", ",")
    return str(value)


def _fill_rgb(cell: Any) -> str | None:
    """Cor de preenchimento sólido da célula em ``rrggbb`` (se houver)."""
    fill = getattr(cell, "fill", None)
    if fill is None or getattr(fill, "fill_type", None) != "solid":
        return None
    color = getattr(fill, "fgColor", None)
    if color is None or getattr(color, "type", None) != "rgb":
        return None
    rgb = color.rgb
    if isinstance(rgb, str) and len(rgb) >= 6:
        return rgb[-6:].upper()
    return None


def _insert_ordered(parent: Any, element: Any, successors: Sequence[str]) -> None:
    """Insere ``element`` em ``parent`` respeitando a ordem do schema OOXML."""
    for child in parent:
        if child.tag in successors:
            child.addprevious(element)
            return
    parent.append(element)


def _set_table_borders(table: Any) -> None:
    """Moldura simples em todas as células (o modelo não tem estilo de tabela)."""
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "auto")
        borders.append(element)
    tbl_pr = table._tbl.tblPr
    successors = tuple(
        qn(tag)
        for tag in (
            "w:shd",
            "w:tblLayout",
            "w:tblCellMar",
            "w:tblLook",
            "w:tblCaption",
            "w:tblDescription",
            "w:tblPrChange",
        )
    )
    _insert_ordered(tbl_pr, borders, successors)


def _shade(cell: Any, rgb: str) -> None:
    """Aplica preenchimento sólido na célula."""
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), rgb)
    successors = tuple(
        qn(tag)
        for tag in (
            "w:noWrap",
            "w:tcMar",
            "w:textDirection",
            "w:tcFitText",
            "w:vAlign",
            "w:hideMark",
        )
    )
    _insert_ordered(tc_pr, shd, successors)


def _column_widths(worksheet: Any, max_col: int) -> list[int]:
    """Larguras das colunas em twips (largura de caractere do Excel → página)."""
    from openpyxl.utils import get_column_letter

    widths: list[int] = []
    for index in range(1, max_col + 1):
        letter = get_column_letter(index)
        dimension = worksheet.column_dimensions.get(letter)
        char_width = getattr(dimension, "width", None) if dimension else None
        if not char_width:
            char_width = DATA_COLUMN_WIDTHS.get(letter, _FALLBACK_COLUMN_WIDTH)
        pixels = char_width * 7 + 5
        # 1 polegada = 96 px = 1440 twips → 1 px = 15 twips.
        widths.append(max(100, int(round(pixels * 15))))
    return widths


def _apply_widths(doc: Any, table: Any, widths: Sequence[int]) -> None:
    """Escreve as larguras (tblW + gridCol + tcW), reduzindo se não couber na página."""
    section = doc.sections[0]
    usable_emu = int(section.page_width - section.left_margin - section.right_margin)
    total_emu = sum(widths) * 635  # 1 twip = 635 EMU
    factor = 1.0 if total_emu <= usable_emu else usable_emu / total_emu

    scaled = [max(100, int(width * factor)) for width in widths]

    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is not None:
        tbl_w.set(qn("w:type"), "dxa")
        tbl_w.set(qn("w:w"), str(sum(scaled)))

    for column_index, width in enumerate(scaled):
        emu = Emu(width * 635)
        table.columns[column_index].width = emu
        for row in table.rows:
            row.cells[column_index].width = emu


def _cell_alignment(column_index: int, is_header: bool) -> Any:
    if is_header:
        return WD_ALIGN_PARAGRAPH.CENTER
    if column_index in (1, 2):  # Formação / Função — texto longo
        return WD_ALIGN_PARAGRAPH.LEFT
    return WD_ALIGN_PARAGRAPH.CENTER


def _merge_cells(table: Any, worksheet: Any, max_row: int, max_col: int) -> None:
    """Reproduz as mesclagens da planilha na tabela Word (melhor esforço)."""
    ranges = sorted(
        worksheet.merged_cells.ranges,
        key=lambda item: (item.min_row, item.min_col),
    )
    for merged in ranges:
        if merged.min_row > max_row or merged.min_col > max_col:
            continue
        try:
            top_left = table.cell(merged.min_row - 1, merged.min_col - 1)
            bottom_right = table.cell(
                min(merged.max_row, max_row) - 1,
                min(merged.max_col, max_col) - 1,
            )
            # Células vazias dentro da mesclagem não devem virar parágrafos
            # em branco dentro da célula final.
            for row_index in range(merged.min_row - 1, min(merged.max_row, max_row)):
                for col_index in range(merged.min_col - 1, min(merged.max_col, max_col)):
                    if (row_index, col_index) == (
                        merged.min_row - 1,
                        merged.min_col - 1,
                    ):
                        continue
                    cell = table.cell(row_index, col_index)
                    if cell.text.strip():
                        continue
                    for paragraph in list(cell._tc.findall(qn("w:p"))):
                        cell._tc.remove(paragraph)
            if top_left._tc is not bottom_right._tc:
                top_left.merge(bottom_right)
        except Exception:  # noqa: BLE001 - mesclagem é cosmética
            log.warning("Não foi possível mesclar %s em %s", merged, worksheet.title)
            continue


def sheet_to_table(doc: Any, worksheet: Any) -> Any | None:
    """Monta a tabela Word de uma aba (cabeçalho + linhas) e a anexa ao fim do doc.

    Returns:
        A ``Table`` criada, ou ``None`` quando a aba não tem valores.
    """
    max_row, max_col = _used_range(worksheet)
    if max_row == 0 or max_col == 0:
        return None

    table = doc.add_table(rows=max_row, cols=max_col)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    _set_table_borders(table)
    widths = _column_widths(worksheet, max_col)
    _apply_widths(doc, table, widths)

    header_fill = _fill_rgb(worksheet.cell(row=1, column=1))

    for row_index in range(1, max_row + 1):
        is_header = row_index == 1
        for col_index in range(1, max_col + 1):
            source = worksheet.cell(row=row_index, column=col_index)
            cell = table.cell(row_index - 1, col_index - 1)
            cell.text = _cell_text(source.value)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

            paragraph = cell.paragraphs[0]
            paragraph.alignment = _cell_alignment(col_index - 1, is_header)
            for run in paragraph.runs:
                if is_header:
                    run.font.bold = True
                    run.font.size = Pt(9)
                else:
                    run.font.size = Pt(9)

            if is_header:
                fill = header_fill or _fill_rgb(source)
                if fill:
                    _shade(cell, fill)
            else:
                fill = _fill_rgb(source)
                if fill:
                    _shade(cell, fill)

    _merge_cells(table, worksheet, max_row, max_col)
    return table


# --- Montagem do documento --------------------------------------------------


def _bay_heading(doc: Any, bay_name: str) -> Any:
    """Parágrafo em negrito identificando o bay da tabela que vem abaixo."""
    paragraph = doc.add_paragraph()
    run = paragraph.add_run(f"Bay: {bay_name}")
    run.bold = True
    run.font.size = Pt(11)
    return paragraph._p


def _insert_after(anchor: Any, elements: Sequence[Any]) -> None:
    """Move os elementos criados no fim do corpo para depois de ``anchor``."""
    current = anchor
    for element in elements:
        current.addnext(element)
        current = element


def build_docx(template_path: str, output_path: str, bay_workbooks: Sequence[tuple[str, Any]]) -> dict:
    """Gera o ``.docx`` inserindo as tabelas de cada bay nas chaves do modelo.

    Args:
        template_path: Modelo ``.docx`` com as chaves ``{{ ... }}``.
        output_path: Caminho do arquivo gerado.
        bay_workbooks: ``[(nome_do_bay, workbook), ...]`` — o ``bay['_workbook']``
            de cada bay exportado (uma aba por equipamento + ``TOTAL``).

    Returns:
        {
          "arquivo": str,
          "tabelas": int,                  # tabelas inseridas no total
          "chaves_inseridas": {chave: [bay, ...]},
          "chaves_sem_tabela": [chave, ...],   # mantidas no documento
          "bays_sem_tabela": {chave: [bay, ...]},
        }
    """
    if _Document is None:
        raise RuntimeError(
            "python-docx não está instalado. Rode: pip install python-docx"
        )
    if not bay_workbooks:
        raise ValueError("Nenhum bay para exportar.")

    doc = _Document(template_path)
    multi_bay = len(bay_workbooks) > 1

    chaves_inseridas: dict[str, list[str]] = {}
    chaves_sem_tabela: list[str] = []
    bays_sem_tabela: dict[str, list[str]] = {}

    # Lista estática: os parágrafos criados aqui (títulos de bay) não devem
    # ser varridos — só os originais do modelo.
    for paragraph in list(doc.paragraphs):
        key = find_key(paragraph.text)
        if key is None:
            continue

        elements: list[Any] = []
        inserted_for: list[str] = []
        missing: list[str] = []

        for bay_name, workbook in bay_workbooks:
            sheet_name = resolve_sheet_name(key, workbook.sheetnames)
            if sheet_name is None:
                missing.append(bay_name)
                continue

            table = sheet_to_table(doc, workbook[sheet_name])
            if table is None:
                missing.append(bay_name)
                continue

            if multi_bay:
                elements.append(_bay_heading(doc, bay_name))
            elements.append(table._tbl)
            inserted_for.append(bay_name)

        if inserted_for:
            _insert_after(paragraph._p, elements)
            paragraph._p.getparent().remove(paragraph._p)
            chaves_inseridas[key] = inserted_for
        else:
            # Sem tabela em nenhum bay: a chave fica no documento como aviso.
            chaves_sem_tabela.append(key)

        if missing:
            bays_sem_tabela.setdefault(key, []).extend(missing)

    doc.save(output_path)

    total = sum(len(bays) for bays in chaves_inseridas.values())
    log.info(
        "build_docx: %s — %d tabela(s) em %d chave(s)%s",
        output_path,
        total,
        len(chaves_inseridas),
        f", {len(chaves_sem_tabela)} chave(s) sem tabela" if chaves_sem_tabela else "",
    )
    return {
        "arquivo": output_path,
        "tabelas": total,
        "chaves_inseridas": chaves_inseridas,
        "chaves_sem_tabela": chaves_sem_tabela,
        "bays_sem_tabela": bays_sem_tabela,
    }


def docx_to_univer(
    template_path: str,
    bay_workbooks: Sequence[tuple[str, Any]],
) -> dict:
    """Extrai os elementos do relatório .docx formatados para o Univer Doc.

    Mesma lógica de substituição de chaves de ``build_docx``, mas em vez de salvar
    em arquivo .docx no disco, gera uma estrutura com parágrafos (texto, estilo,
    alinhamento) e tabelas (células, alinhamentos, preenchimento, bordas,
    mesclagens e larguras) pronta para ser montada pelo Univer Doc no frontend.
    """
    if _Document is None:
        raise RuntimeError(
            "python-docx não está instalado. Rode: pip install python-docx"
        )
    if not bay_workbooks:
        raise ValueError("Nenhum bay para exportar.")

    doc = _Document(template_path)
    multi_bay = len(bay_workbooks) > 1

    elements: list[dict[str, Any]] = []
    chaves_inseridas: dict[str, list[str]] = {}
    chaves_sem_tabela: list[str] = []
    bays_sem_tabela: dict[str, list[str]] = {}

    for paragraph in list(doc.paragraphs):
        key = find_key(paragraph.text)
        if key is None:
            runs: list[dict[str, Any]] = []
            for r in paragraph.runs:
                if not r.text:
                    continue
                run_data: dict[str, Any] = {"text": r.text}
                if r.font.bold:
                    run_data["bold"] = True
                if r.font.italic:
                    run_data["italic"] = True
                if r.font.size and hasattr(r.font.size, "pt"):
                    run_data["fontSize"] = float(r.font.size.pt)
                if r.font.color and getattr(r.font.color, "rgb", None):
                    run_data["color"] = f"#{r.font.color.rgb[-6:]}"
                runs.append(run_data)

            align_name = "left"
            if paragraph.alignment == WD_ALIGN_PARAGRAPH.CENTER:
                align_name = "center"
            elif paragraph.alignment == WD_ALIGN_PARAGRAPH.RIGHT:
                align_name = "right"
            elif paragraph.alignment == WD_ALIGN_PARAGRAPH.JUSTIFY:
                align_name = "justify"

            elements.append({
                "type": "paragraph",
                "text": paragraph.text,
                "align": align_name,
                "runs": runs,
            })
            continue

        inserted_for: list[str] = []
        missing: list[str] = []

        for bay_name, workbook in bay_workbooks:
            sheet_name = resolve_sheet_name(key, workbook.sheetnames)
            if sheet_name is None:
                missing.append(bay_name)
                continue

            worksheet = workbook[sheet_name]
            max_row, max_col = _used_range(worksheet)
            if max_row == 0 or max_col == 0:
                missing.append(bay_name)
                continue

            if multi_bay:
                elements.append({
                    "type": "heading",
                    "text": f"Bay: {bay_name}",
                    "style": {"bold": True, "fontSize": 11, "color": "#1e293b"},
                })

            header_fill = _fill_rgb(worksheet.cell(row=1, column=1))
            twip_widths = _column_widths(worksheet, max_col)
            pt_widths = [round(w / 20.0, 1) for w in twip_widths]
            total_pt = sum(pt_widths)
            if total_pt > 495.0 and total_pt > 0:
                factor = 495.0 / total_pt
                pt_widths = [round(w * factor, 1) for w in pt_widths]

            rows_data: list[list[dict[str, Any]]] = []
            for row_index in range(1, max_row + 1):
                is_header = (row_index == 1)
                row_cells: list[dict[str, Any]] = []
                for col_index in range(1, max_col + 1):
                    cell = worksheet.cell(row=row_index, column=col_index)
                    text_val = _cell_text(cell.value)
                    fill = (header_fill or _fill_rgb(cell)) if is_header else _fill_rgb(cell)
                    align = "center"
                    if not is_header and col_index in (2, 3):
                        align = "left"
                    row_cells.append({
                        "text": text_val,
                        "bold": is_header or bool(getattr(getattr(cell, "font", None), "bold", False)),
                        "italic": bool(getattr(getattr(cell, "font", None), "italic", False)),
                        "align": align,
                        "bg": f"#{fill}" if fill else None,
                        "color": "#ffffff" if (is_header and fill and fill.startswith("3")) else None,
                    })
                rows_data.append(row_cells)

            merges: list[dict[str, int]] = []
            for merged in worksheet.merged_cells.ranges:
                if merged.min_row <= max_row and merged.min_col <= max_col:
                    merges.append({
                        "startRow": merged.min_row - 1,
                        "endRow": min(merged.max_row, max_row) - 1,
                        "startCol": merged.min_col - 1,
                        "endCol": min(merged.max_col, max_col) - 1,
                    })

            table_id = f"table_{normalize(key)}_{normalize(bay_name)}".replace(" ", "_")
            elements.append({
                "type": "table",
                "tableId": table_id,
                "sheetName": sheet_name,
                "bayName": bay_name,
                "rowCount": max_row,
                "colCount": max_col,
                "columnWidths": pt_widths,
                "rows": rows_data,
                "merges": merges,
            })
            inserted_for.append(bay_name)

        if inserted_for:
            chaves_inseridas[key] = inserted_for
        else:
            chaves_sem_tabela.append(key)
            elements.append({
                "type": "paragraph",
                "text": paragraph.text,
                "align": "left",
                "runs": [{"text": paragraph.text, "color": "#94a3b8", "italic": True}],
            })

        if missing:
            bays_sem_tabela.setdefault(key, []).extend(missing)

    total = sum(len(bays) for bays in chaves_inseridas.values())
    return {
        "status": "sucesso",
        "template": os.path.basename(template_path),
        "elements": elements,
        "tabelas": total,
        "chaves_inseridas": chaves_inseridas,
        "chaves_sem_tabela": chaves_sem_tabela,
        "bays_sem_tabela": bays_sem_tabela,
    }


__all__ = [
    "build_docx",
    "docx_to_univer",
    "find_key",
    "normalize",
    "resolve_sheet_name",
    "sheet_to_table",
]
