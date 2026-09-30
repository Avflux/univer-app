"""Serializa um workbook openpyxl no formato de abas consumido pelo Univer.

O frontend (`frontend/`) mostra a saída da exportação na tela, sem
baixar o `.xlsx`: ``POST /api/export/all-bays/univer`` gera a planilha multi-bay
em memória e devolve as abas já no formato descrito aqui.

Cada aba vira um item de ``sheets``:

    {
      "name": "SUMÁRIO GERAL",
      "rows": [[valor|célula, ...], ...],          # valores por linha
      "merges": [{"startRow", "endRow",
                  "startColumn", "endColumn"}],    # índices 0-based
      "columnWidths": {"0": 12.5, ...},            # largura em caracteres
      "hidden": False,
      "styles": [{"bold": True, "fill": "#b8cce4", "hAlign": "center",
                  "border": {"top": {"style": "thin"}}, ...}, ...],
      "styleIndex": [[0, null, 1], ...],           # índice em "styles" por célula
    }

``styles`` traz só as combinações usadas na aba (deduplicadas) e ``styleIndex``
aponta para elas na mesma malha de ``rows`` — célula sem estilo fica ``null``.
Os nomes dos estilos são neutros (o frontend converte para os enums do Univer):
``bold``, ``italic``, ``size``, ``color``, ``fill``, ``hAlign`` (left/center/
right/justify), ``vAlign`` (top/center/bottom), ``wrap``, ``numberFormat`` e
``border`` (``style`` do openpyxl por lado + ``color``).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time
from typing import Any

from openpyxl.utils import column_index_from_string
from openpyxl.worksheet.worksheet import Worksheet

_RGB_RE = re.compile(r"^[0-9A-Fa-f]{6,8}$")
_BORDER_SIDES = ("top", "bottom", "left", "right")


def _hex_color(color: Any) -> str | None:
    """Cor do openpyxl como ``#rrggbb``, ou ``None`` quando não há cor.

    Cores de tema/índice (`theme=1`, por exemplo) não têm ``rgb`` utilizável —
    nelas o openpyxl devolve a mensagem de erro do descritor, então o valor só é
    aceito se passar no formato hexadecimal.
    """
    if color is None or getattr(color, "type", None) != "rgb":
        return None
    rgb = getattr(color, "rgb", None)
    if not isinstance(rgb, str) or not _RGB_RE.match(rgb):
        return None
    if rgb.upper() == "00000000":  # sem preenchimento/cor padrão
        return None
    return f"#{rgb[-6:].lower()}"


def _cell_value(value: Any) -> Any:
    """Converte o valor da célula em algo serializável em JSON."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return str(value)


def _cell_style(cell: Any) -> dict[str, Any] | None:
    """Descreve o estilo da célula, ou ``None`` quando ela é "limpa"."""
    style: dict[str, Any] = {}

    font = cell.font
    if font is not None:
        if font.bold:
            style["bold"] = True
        if font.italic:
            style["italic"] = True
        if font.sz:
            style["size"] = round(float(font.sz), 2)
        color = _hex_color(font.color)
        if color:
            style["color"] = color

    fill = cell.fill
    if fill is not None and fill.patternType == "solid":
        color = _hex_color(fill.fgColor)
        if color:
            style["fill"] = color

    align = cell.alignment
    if align is not None:
        if align.horizontal:
            style["hAlign"] = align.horizontal
        if align.vertical:
            style["vAlign"] = align.vertical
        if align.wrap_text:
            style["wrap"] = True

    border = cell.border
    sides: dict[str, dict[str, str]] = {}
    for side_name in _BORDER_SIDES:
        side = getattr(border, side_name, None)
        if side is None or not side.style:
            continue
        entry = {"style": side.style}
        color = _hex_color(side.color)
        if color:
            entry["color"] = color
        sides[side_name] = entry
    if sides:
        style["border"] = sides

    number_format = getattr(cell, "number_format", None)
    if number_format and number_format != "General":
        style["numberFormat"] = number_format

    return style or None


def _sheet_content(
    sheet: Worksheet,
) -> tuple[list[list[Any]], list[list[int | None]], list[dict[str, Any]]]:
    """Valores, índices de estilo e a lista de estilos usados na aba."""
    styles: list[dict[str, Any]] = []
    positions: dict[str, int] = {}
    rows: list[list[Any]] = []
    style_index: list[list[int | None]] = []

    for row in sheet.iter_rows():
        values: list[Any] = []
        line: list[int | None] = []
        for cell in row:
            values.append(_cell_value(cell.value))

            style = _cell_style(cell)
            if style is None:
                line.append(None)
                continue
            key = json.dumps(style, sort_keys=True)
            position = positions.get(key)
            if position is None:
                position = len(styles)
                positions[key] = position
                styles.append(style)
            line.append(position)

        rows.append(values)
        style_index.append(line)

    # As linhas vazias sobrando no fim não interessam a nenhuma das duas malhas.
    while rows and all(value is None or value == "" for value in rows[-1]):
        rows.pop()
        style_index.pop()

    return rows, style_index, styles


def _merges(sheet: Worksheet) -> list[dict[str, int]]:
    """Ranges mesclados da aba, já convertidos para índices 0-based."""
    return [
        {
            "startRow": merged.min_row - 1,
            "endRow": merged.max_row - 1,
            "startColumn": merged.min_col - 1,
            "endColumn": merged.max_col - 1,
        }
        for merged in sheet.merged_cells.ranges
    ]


def _column_widths(sheet: Worksheet) -> dict[str, float]:
    """Larguras explícitas das colunas, indexadas por coluna (0-based)."""
    widths: dict[str, float] = {}
    for letter, dimension in sheet.column_dimensions.items():
        if not dimension.width:
            continue
        widths[str(column_index_from_string(letter) - 1)] = round(float(dimension.width), 2)
    return widths


def workbook_to_sheets(workbook: Any) -> list[dict[str, Any]]:
    """Converte o workbook em uma lista de abas prontas para o frontend."""
    sheets: list[dict[str, Any]] = []

    for sheet in workbook.worksheets:
        rows, style_index, styles = _sheet_content(sheet)
        sheets.append(
            {
                "name": sheet.title,
                "rows": rows,
                "styles": styles,
                "styleIndex": style_index,
                "merges": _merges(sheet),
                "columnWidths": _column_widths(sheet),
                "hidden": sheet.sheet_state != "visible",
            }
        )

    return sheets
