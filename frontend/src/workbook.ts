/**
 * Constrói o snapshot do Univer (`IWorkbookData`) da saída da exportação.
 *
 * `buildOutputWorkbook` monta o workbook com o `.xlsx` gerado pelo backend
 * (`POST /api/export/all-bays/univer`): uma aba por sheet do arquivo, na mesma
 * ordem do backend — valores, estilos (bordas, preenchimento, alinhamento,
 * negrito, formato numérico), mesclagens, larguras e visibilidade.
 *
 * Junto com o snapshot vêm as tabelas a registrar depois de montar o workbook
 * (`tables`): cada seção de equipamento da saída vira uma tabela do Univer —
 * `UniverSheetsTablePreset` + `worksheet.addTable` no `UniverSheet.tsx`.
 */

import type {
    IBorderData,
    ICellData,
    IStyleData,
    IWorkbookData,
    IWorksheetData,
} from '@univerjs/core';
import type { OutputCellStyle, OutputResult, OutputSheet } from './api';
import {
    BooleanNumber,
    BorderStyleTypes,
    getSheetsEmptySnapshot,
    HorizontalAlign,
    LocaleType,
    VerticalAlign,
    WrapStrategy,
} from '@univerjs/core';

/** Workbook com a saída da exportação (`.xlsx`) montada na tela. */
export const OUTPUT_WORKBOOK_ID = 'univer-output';

const MAX_SHEET_NAME = 31;
const OUTPUT_MIN_ROWS = 40;
const OUTPUT_MIN_COLUMNS = 12;

/** Seção de uma aba da saída que vira uma tabela do Univer. */
export interface SheetTableSpec {
    /** Aba da saída, no formato `saida-<índice>`. */
    sheetId: string;
    /** Nome da tabela, sem espaços nem caracteres recusados pelo Univer. */
    name: string;
    range: { startRow: number; endRow: number; startColumn: number; endColumn: number };
}

export interface OutputWorkbook {
    snapshot: IWorkbookData;
    /** Seções de equipamento a registrar como tabelas depois de montar a planilha. */
    tables: SheetTableSpec[];
}

type CellMatrix = NonNullable<IWorksheetData['cellData']>;
type StyleMap = NonNullable<IWorkbookData['styles']>;

type RangeCells = Record<number, ICellData>;

/** Nome de aba único e dentro do limite do Excel (31 caracteres). */
function uniqueSheetName(raw: string, used: Set<string>, index: number): string {
    const base = (raw || `Aba ${index + 1}`).slice(0, MAX_SHEET_NAME);
    if (!used.has(base)) {
        used.add(base);
        return base;
    }

    let suffix = 2;
    let candidate = `${base.slice(0, MAX_SHEET_NAME - 4)} (${suffix})`;
    while (used.has(candidate)) {
        suffix += 1;
        candidate = `${base.slice(0, MAX_SHEET_NAME - 4)} (${suffix})`;
    }
    used.add(candidate);
    return candidate;
}

const H_ALIGNMENTS: Record<string, HorizontalAlign> = {
    left: HorizontalAlign.LEFT,
    center: HorizontalAlign.CENTER,
    right: HorizontalAlign.RIGHT,
    justify: HorizontalAlign.JUSTIFIED,
};

const V_ALIGNMENTS: Record<string, VerticalAlign> = {
    top: VerticalAlign.TOP,
    center: VerticalAlign.MIDDLE,
    bottom: VerticalAlign.BOTTOM,
};

/** Estilos de borda do openpyxl nos enums do Univer. */
const BORDER_STYLES: Record<string, BorderStyleTypes> = {
    hair: BorderStyleTypes.HAIR,
    thin: BorderStyleTypes.THIN,
    dotted: BorderStyleTypes.DOTTED,
    dashed: BorderStyleTypes.DASHED,
    dashDot: BorderStyleTypes.DASH_DOT,
    dashDotDot: BorderStyleTypes.DASH_DOT_DOT,
    double: BorderStyleTypes.DOUBLE,
    medium: BorderStyleTypes.MEDIUM,
    mediumDashed: BorderStyleTypes.MEDIUM_DASHED,
    mediumDashDot: BorderStyleTypes.MEDIUM_DASH_DOT,
    mediumDashDotDot: BorderStyleTypes.MEDIUM_DASH_DOT_DOT,
    slantDashDot: BorderStyleTypes.SLANT_DASH_DOT,
    thick: BorderStyleTypes.THICK,
};

/** Lados da borda no estilo do Univer (`t`/`r`/`b`/`l`). */
const BORDER_SIDES = { top: 't', right: 'r', bottom: 'b', left: 'l' } as const;

/** Converte o estilo neutro do backend (`univer_snapshot.py`) no estilo do Univer. */
function outputStyle(style: OutputCellStyle): IStyleData {
    const result: IStyleData = {};

    if (style.bold) {
        result.bl = BooleanNumber.TRUE;
    }
    if (style.italic) {
        result.it = BooleanNumber.TRUE;
    }
    if (style.size) {
        result.fs = style.size;
    }
    if (style.color) {
        result.cl = { rgb: style.color };
    }
    if (style.fill) {
        result.bg = { rgb: style.fill };
    }

    const hAlign = style.hAlign ? H_ALIGNMENTS[style.hAlign] : undefined;
    if (hAlign) {
        result.ht = hAlign;
    }
    const vAlign = style.vAlign ? V_ALIGNMENTS[style.vAlign] : undefined;
    if (vAlign) {
        result.vt = vAlign;
    }
    if (style.wrap) {
        result.tb = WrapStrategy.WRAP;
    }
    if (style.numberFormat) {
        result.n = { pattern: style.numberFormat };
    }

    if (style.border) {
        const border: IBorderData = {};
        for (const [side, key] of Object.entries(BORDER_SIDES)) {
            const entry = style.border[side as keyof typeof BORDER_SIDES];
            const line = entry ? BORDER_STYLES[entry.style] : undefined;
            if (!entry || !line) {
                continue;
            }
            border[key] = { s: line, cl: { rgb: entry.color ?? '#1f2329' } };
        }
        if (Object.keys(border).length > 0) {
            result.bd = border;
        }
    }

    return result;
}

function outputCellData(
    rows: OutputResult['sheets'][number]['rows'],
    styleIndex: (number | null)[][] | undefined,
    styleKeys: string[]
): CellMatrix {
    const cells: CellMatrix = {};

    rows.forEach((row, rowIndex) => {
        const line: RangeCells = {};
        row.forEach((value, column) => {
            const cell: ICellData = {};
            if (value !== null && value !== undefined && value !== '') {
                cell.v = value;
            }
            const style = styleIndex?.[rowIndex]?.[column];
            if (style !== null && style !== undefined && styleKeys[style]) {
                cell.s = styleKeys[style];
            }
            if (cell.v !== undefined || cell.s !== undefined) {
                line[column] = cell;
            }
        });
        if (Object.keys(line).length > 0) {
            cells[rowIndex] = line;
        }
    });

    return cells;
}

type SheetRow = OutputSheet['rows'][number];

/**
 * Nome de tabela aceito pelo Univer: sem espaço nem `: \ / ? * [ ]`, começando
 * por letra ou `_` e único no workbook (reprovado, o Univer troca por um nome
 * genérico).
 */
function uniqueTableName(raw: unknown, fallback: string, used: Set<string>): string {
    const base = String(raw ?? '').replace(/[ :\\/?*\[\]]+/g, '_').replace(/^[^A-Za-z_]+/, '') || fallback;
    let name = base;
    let suffix = 2;
    while (used.has(name.toLowerCase())) {
        name = `${base}_${suffix}`;
        suffix += 1;
    }
    used.add(name.toLowerCase());
    return name;
}

function rowHasValue(row: SheetRow | undefined, from: number, to: number): boolean {
    if (!row) {
        return false;
    }
    for (let column = from; column <= to; column += 1) {
        const value = row[column];
        if (value !== null && value !== undefined && value !== '') {
            return true;
        }
    }
    return false;
}

/**
 * Seções de uma aba da saída.
 *
 * O backend escreve cada equipamento como uma seção: uma linha de título
 * mesclada (`SECCIONADA-1`, `CAIXA CA`, `TOTAIS DO BAY`, …), a linha de
 * cabeçalho e as linhas de dados. O título dá o nome da tabela e a linha de
 * cabeçalho é onde ela começa — o título fica fora do intervalo. Abas sem
 * seção (ex.: `Sumário Geral`, que já é uma tabela única) viram uma tabela com
 * a aba inteira.
 */
function sheetTables(sheet: OutputSheet, sheetId: string, used: Set<string>): SheetTableSpec[] {
    const rows = sheet.rows ?? [];
    const merges = sheet.merges ?? [];
    const mergedRows = new Set<number>();
    for (const merge of merges) {
        for (let row = merge.startRow; row <= merge.endRow; row += 1) {
            mergedRows.add(row);
        }
    }

    const titles = merges
        .filter((merge) => merge.startRow === merge.endRow && merge.endColumn > merge.startColumn)
        .sort((a, b) => a.startRow - b.startRow || a.startColumn - b.startColumn);

    const tables: SheetTableSpec[] = [];
    titles.forEach((title, index) => {
        const headerRow = title.startRow + 1;
        // O título de uma seção é seguido de um cabeçalho de verdade; o cabeçalho
        // do bay (também mesclado) e os títulos soltos ficam de fora.
        if (
            mergedRows.has(headerRow) ||
            !rowHasValue(rows[headerRow], title.startColumn, title.endColumn)
        ) {
            return;
        }

        // A tabela vai até a última linha com dado na faixa da seção, antes do
        // próximo título — blocos de colunas diferentes dividem as mesmas linhas
        // da aba (ex.: cabos à esquerda e ajustado à direita no `Total Geral`).
        const later = titles.slice(index + 1).find((candidate) => candidate.startRow > title.startRow);
        const nextTitle = later?.startRow ?? rows.length;
        let endRow = headerRow;
        for (let row = headerRow; row < nextTitle; row += 1) {
            if (rowHasValue(rows[row], title.startColumn, title.endColumn)) {
                endRow = row;
            }
        }

        tables.push({
            sheetId,
            name: uniqueTableName(rows[title.startRow]?.[title.startColumn], sheet.name, used),
            range: {
                startRow: headerRow,
                endRow,
                startColumn: title.startColumn,
                endColumn: title.endColumn,
            },
        });
    });

    if (tables.length > 0) {
        return tables;
    }

    const columns = rows.reduce((max, row) => Math.max(max, row.length), 0);
    if (rows.length === 0 || columns === 0) {
        return [];
    }

    return [
        {
            sheetId,
            name: uniqueTableName(sheet.name, 'Tabela', used),
            range: { startRow: 0, endRow: rows.length - 1, startColumn: 0, endColumn: columns - 1 },
        },
    ];
}

/**
 * Monta um workbook do Univer com a saída da exportação: uma aba por sheet do
 * `.xlsx` gerado pelo backend — valores, estilos (bordas, preenchimento,
 * alinhamento, negrito, formato numérico), mesclagens e larguras — e as
 * tabelas a registrar nas seções de equipamento.
 */
export function buildOutputWorkbook(output: OutputResult): OutputWorkbook {
    const snapshot = getSheetsEmptySnapshot(OUTPUT_WORKBOOK_ID, LocaleType.PT_BR, 'Saída');
    const sheets: NonNullable<IWorkbookData['sheets']> = {};
    const order: string[] = [];
    const usedNames = new Set<string>();
    const tableNames = new Set<string>();
    const tables: SheetTableSpec[] = [];
    const styles: StyleMap = {};

    output.sheets.forEach((sheet, index) => {
        const sheetId = `saida-${index}`;
        const sheetName = uniqueSheetName(sheet.name, usedNames, index);
        const rows = sheet.rows ?? [];
        const columns = rows.reduce((max, row) => Math.max(max, row.length), 0);
        const columnData: NonNullable<IWorksheetData['columnData']> = {};

        // Cada aba registra as próprias combinações de estilo no workbook.
        const styleKeys = (sheet.styles ?? []).map((style, styleIndex) => {
            const key = `${sheetId}-${styleIndex}`;
            styles[key] = outputStyle(style);
            return key;
        });

        Object.entries(sheet.columnWidths ?? {}).forEach(([column, width]) => {
            const parsed = Number(width);
            if (Number.isFinite(parsed) && parsed > 0) {
                // openpyxl mede a largura em caracteres; o Univer em pixels.
                columnData[Number(column)] = { w: Math.min(Math.round(parsed * 7 + 5), 600) };
            }
        });

        // O nome da aba também não pode ser reaproveitado como nome de tabela.
        tableNames.add(sheetName.toLowerCase());
        tables.push(...sheetTables(sheet, sheetId, tableNames));

        sheets[sheetId] = {
            id: sheetId,
            name: sheetName,
            hidden: sheet.hidden ? BooleanNumber.TRUE : BooleanNumber.FALSE,
            rowCount: Math.max(OUTPUT_MIN_ROWS, rows.length + 10),
            columnCount: Math.max(OUTPUT_MIN_COLUMNS, columns + 2),
            zoomRatio: 1,
            scrollTop: 0,
            scrollLeft: 0,
            defaultColumnWidth: 110,
            defaultRowHeight: 22,
            mergeData: (sheet.merges ?? []).map((merge) => ({ ...merge })),
            cellData: outputCellData(rows, sheet.styleIndex, styleKeys),
            columnData,
            rowHeader: { width: 46, hidden: BooleanNumber.FALSE },
            columnHeader: { height: 24, hidden: BooleanNumber.FALSE },
            showGridlines: BooleanNumber.FALSE,
            rightToLeft: BooleanNumber.FALSE,
        };
        order.push(sheetId);
    });

    snapshot.styles = styles;
    snapshot.sheets = sheets;
    snapshot.sheetOrder = order;
    return { snapshot, tables };
}
