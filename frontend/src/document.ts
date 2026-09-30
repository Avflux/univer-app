/**
 * Monta o snapshot IDocumentData do Univer Doc a partir da saída da exportação
 * do modelo Word (`POST /api/export/docx/univer`).
 *
 * Cada elemento do resultado vira parágrafo, título ou tabela com formatação,
 * células com preenchimento, alinhamento, bordas e mesclagens compatíveis com o
 * motor de layout paginado (Traditional) do Univer Doc.
 */

import type {
    IDocumentBody,
    IDocumentData,
    IParagraph,
    ISectionBreak,
    ITable,
    ITableColumn,
    ITableRow,
    ITextRun,
} from '@univerjs/core';
import type { DocxUniverResult } from './api';
import {
    BooleanNumber,
    DataStreamTreeTokenType,
    DocumentFlavor,
    getDocsEmptySnapshot,
    HorizontalAlign,
    LocaleType,
    ObjectRelativeFromH,
    ObjectRelativeFromV,
    TableAlignmentType,
    TableLayoutType,
    TableRowHeightRule,
    TableSizeType,
    TableTextWrapType,
    VerticalAlignmentType,
} from '@univerjs/core';

export const DOC_OUTPUT_UNIT_ID = 'univer-doc-output';

export function buildOutputDocument(result: DocxUniverResult): IDocumentData {
    const title = result.template ? `Univer — ${result.template}` : 'Univer — Relatório do Modelo';
    const snapshot = getDocsEmptySnapshot(
        DOC_OUTPUT_UNIT_ID,
        LocaleType.PT_BR,
        title,
        DocumentFlavor.TRADITIONAL
    );

    let dataStream = '';
    const paragraphs: IParagraph[] = [];
    const sectionBreaks: ISectionBreak[] = [];
    const textRuns: ITextRun[] = [];
    const tables: Array<{ tableId: string; startIndex: number; endIndex: number }> = [];
    const tableSource: Record<string, ITable> = {};

    const pageWidth = snapshot.documentStyle?.pageSize?.width ?? 794;
    const marginLeft = snapshot.documentStyle?.marginLeft ?? 72;
    const marginRight = snapshot.documentStyle?.marginRight ?? 72;
    const usableWidth = Math.max(100, pageWidth - marginLeft - marginRight);

    const elements = result.elements ?? [];

    for (let elIndex = 0; elIndex < elements.length; elIndex += 1) {
        const element = elements[elIndex];

        if (element.type === 'paragraph') {
            const hasRuns = Boolean(element.runs && element.runs.length > 0);
            const text = hasRuns
                ? element.runs!.map((r) => r.text ?? '').join('')
                : (element.text ?? '');

            if (text) {
                const pStart = dataStream.length;
                dataStream += text;
                if (hasRuns) {
                    let runOffset = pStart;
                    for (const r of element.runs!) {
                        const rText = r.text ?? '';
                        if (!rText) continue;
                        textRuns.push({
                            st: runOffset,
                            ed: runOffset + rText.length,
                            ts: {
                                bl: r.bold ? BooleanNumber.TRUE : BooleanNumber.FALSE,
                                it: r.italic ? BooleanNumber.TRUE : BooleanNumber.FALSE,
                                fs: r.fontSize ?? 10.5,
                                ...(r.color ? { cl: { rgb: r.color } } : {}),
                            },
                        });
                        runOffset += rText.length;
                    }
                } else {
                    textRuns.push({
                        st: pStart,
                        ed: pStart + text.length,
                        ts: { fs: 10.5, cl: { rgb: '#1e293b' } },
                    });
                }
            }
            const pIndex = dataStream.length;
            dataStream += DataStreamTreeTokenType.PARAGRAPH;
            paragraphs.push({
                paragraphId: `p-${paragraphs.length + 1}`,
                startIndex: pIndex,
                paragraphStyle: {
                    horizontalAlign:
                        element.align === 'center'
                            ? HorizontalAlign.CENTER
                            : element.align === 'right'
                                ? HorizontalAlign.RIGHT
                                : element.align === 'justify'
                                    ? HorizontalAlign.JUSTIFIED
                                    : HorizontalAlign.LEFT,
                    lineSpacing: 1.25,
                    spaceBelow: { v: 4 },
                },
            });
        } else if (element.type === 'heading') {
            const text = element.text ?? '';
            if (text) {
                const pStart = dataStream.length;
                dataStream += text;
                textRuns.push({
                    st: pStart,
                    ed: pStart + text.length,
                    ts: {
                        bl: BooleanNumber.TRUE,
                        fs: element.style?.fontSize ?? 12,
                        cl: { rgb: element.style?.color ?? '#0f172a' },
                    },
                });
            }
            const pIndex = dataStream.length;
            dataStream += DataStreamTreeTokenType.PARAGRAPH;
            paragraphs.push({
                paragraphId: `h-${paragraphs.length + 1}`,
                startIndex: pIndex,
                paragraphStyle: {
                    horizontalAlign: HorizontalAlign.LEFT,
                    spaceAbove: { v: 12 },
                    spaceBelow: { v: 6 },
                    keepNext: BooleanNumber.TRUE,
                },
            });
        } else if (element.type === 'table') {
            const rowCount = element.rowCount || element.rows.length;
            const colCount = element.colCount || (element.rows[0]?.length ?? 0);

            if (rowCount === 0 || colCount === 0) {
                continue;
            }

            const tableId = element.tableId || `tbl-${tables.length + 1}`;
            const tableStart = dataStream.length;
            dataStream += DataStreamTreeTokenType.TABLE_START;

            // Mapeia mesclagens para rowSpan e colSpan por célula
            const rowSpanMap: number[][] = Array.from({ length: rowCount }, () =>
                new Array(colCount).fill(1));
            const colSpanMap: number[][] = Array.from({ length: rowCount }, () =>
                new Array(colCount).fill(1));

            for (const m of element.merges ?? []) {
                const rSpan = m.endRow - m.startRow + 1;
                const cSpan = m.endCol - m.startCol + 1;
                for (let r = m.startRow; r <= m.endRow && r < rowCount; r += 1) {
                    for (let c = m.startCol; c <= m.endCol && c < colCount; c += 1) {
                        if (r === m.startRow && c === m.startCol) {
                            rowSpanMap[r][c] = rSpan;
                            colSpanMap[r][c] = cSpan;
                        } else {
                            rowSpanMap[r][c] = 0;
                            colSpanMap[r][c] = 0;
                        }
                    }
                }
            }

            element.rows.forEach((row, rIdx) => {
                dataStream += DataStreamTreeTokenType.TABLE_ROW_START;
                row.forEach((cell, cIdx) => {
                    dataStream += DataStreamTreeTokenType.TABLE_CELL_START;
                    const cellText = cell.text ?? '';
                    const cellStart = dataStream.length;
                    if (cellText) {
                        dataStream += cellText;
                    }
                    const pIdx = dataStream.length;
                    dataStream += DataStreamTreeTokenType.PARAGRAPH;
                    const sIdx = dataStream.length;
                    dataStream +=
                        DataStreamTreeTokenType.SECTION_BREAK +
                        DataStreamTreeTokenType.TABLE_CELL_END;

                    paragraphs.push({
                        paragraphId: `p-${tableId}-${rIdx}-${cIdx}`,
                        startIndex: pIdx,
                        paragraphStyle: {
                            horizontalAlign:
                                cell.align === 'center'
                                    ? HorizontalAlign.CENTER
                                    : cell.align === 'right'
                                        ? HorizontalAlign.RIGHT
                                        : HorizontalAlign.LEFT,
                            lineSpacing: 1.15,
                            spaceAbove: { v: 2 },
                            spaceBelow: { v: 2 },
                        },
                    });

                    sectionBreaks.push({
                        sectionId: `s-${tableId}-${rIdx}-${cIdx}`,
                        startIndex: sIdx,
                    });

                    if (cellText) {
                        textRuns.push({
                            st: cellStart,
                            ed: cellStart + cellText.length,
                            ts: {
                                bl: cell.bold ? BooleanNumber.TRUE : BooleanNumber.FALSE,
                                it: cell.italic ? BooleanNumber.TRUE : BooleanNumber.FALSE,
                                fs: rIdx === 0 ? 9.5 : 9,
                                cl: cell.color ? { rgb: cell.color } : { rgb: '#1e293b' },
                            },
                        });
                    }
                });
                dataStream += DataStreamTreeTokenType.TABLE_ROW_END;
            });

            dataStream += DataStreamTreeTokenType.TABLE_END;
            const tableEnd = dataStream.length;

            const trailingPIdx = dataStream.length;
            dataStream += DataStreamTreeTokenType.PARAGRAPH;
            paragraphs.push({
                paragraphId: `p-after-${tableId}`,
                startIndex: trailingPIdx,
                paragraphStyle: { spaceBelow: { v: 8 } },
            });

            tables.push({
                tableId,
                startIndex: tableStart,
                endIndex: tableEnd,
            });

            // Normaliza larguras das colunas para caber na folha A4 com proporções originais
            const rawColWidths: number[] =
                element.columnWidths && element.columnWidths.length === colCount
                    ? element.columnWidths
                    : new Array(colCount).fill(usableWidth / colCount);

            const sumRaw = rawColWidths.reduce((a, b) => a + b, 0);
            const scale = sumRaw > 0 ? usableWidth / sumRaw : 1;
            const colWidths = rawColWidths.map((w) => Math.max(20, Math.round(w * scale * 10) / 10));

            const tableColumns: ITableColumn[] = colWidths.map((w) => ({
                size: {
                    type: TableSizeType.SPECIFIED,
                    width: {
                        v: w,
                    },
                },
            }));

            const tableRows: ITableRow[] = element.rows.map((row, rIdx) => ({
                trHeight: {
                    val: { v: rIdx === 0 ? 26 : 20 },
                    hRule: TableRowHeightRule.AUTO,
                },
                cantSplit: BooleanNumber.TRUE,
                isFirstRow: rIdx === 0 ? BooleanNumber.TRUE : BooleanNumber.FALSE,
                repeatHeaderRow: rIdx === 0 ? BooleanNumber.TRUE : BooleanNumber.FALSE,
                tableCells: row.map((cell, cIdx) => ({
                    vAlign: VerticalAlignmentType.CENTER,
                    margin: {
                        start: { v: 6 },
                        end: { v: 6 },
                        top: { v: 4 },
                        bottom: { v: 4 },
                    },
                    backgroundColor: cell.bg
                        ? { rgb: cell.bg }
                        : rIdx === 0
                            ? { rgb: '#f1f5f9' }
                            : undefined,
                    borderTop: { color: { rgb: '#cbd5e1' }, width: { v: 1 } },
                    borderBottom: { color: { rgb: '#cbd5e1' }, width: { v: 1 } },
                    borderLeft: { color: { rgb: '#cbd5e1' }, width: { v: 1 } },
                    borderRight: { color: { rgb: '#cbd5e1' }, width: { v: 1 } },
                    rowSpan: rowSpanMap[rIdx]?.[cIdx] ?? 1,
                    columnSpan: colSpanMap[rIdx]?.[cIdx] ?? 1,
                })),
            }));

            tableSource[tableId] = {
                tableId,
                tableColumns,
                tableRows,
                align: TableAlignmentType.CENTER,
                indent: { v: 0 },
                textWrap: TableTextWrapType.NONE,
                position: {
                    positionH: {
                        relativeFrom: ObjectRelativeFromH.PAGE,
                        posOffset: 0,
                    },
                    positionV: {
                        relativeFrom: ObjectRelativeFromV.PAGE,
                        posOffset: 0,
                    },
                },
                dist: {
                    distB: 0,
                    distL: 0,
                    distR: 0,
                    distT: 0,
                },
                cellMargin: {
                    start: { v: 6 },
                    end: { v: 6 },
                    top: { v: 4 },
                    bottom: { v: 4 },
                },
                size: {
                    type: TableSizeType.UNSPECIFIED,
                    width: { v: usableWidth },
                },
                layout: TableLayoutType.FIXED,
            };
        }
    }

    if (dataStream.length === 0) {
        dataStream = 'Sem dados no documento.\r\n';
        paragraphs.push({
            paragraphId: 'p-empty',
            startIndex: 23,
            paragraphStyle: { lineSpacing: 1 },
        });
        sectionBreaks.push({
            sectionId: 's-empty',
            startIndex: 24,
        });
    } else {
        dataStream += DataStreamTreeTokenType.SECTION_BREAK;
        sectionBreaks.push({
            sectionId: 'section-end',
            startIndex: dataStream.length - 1,
        });
    }

    paragraphs.sort((a, b) => a.startIndex - b.startIndex);
    sectionBreaks.sort((a, b) => a.startIndex - b.startIndex);
    textRuns.sort((a, b) => a.st - b.st);

    const body: IDocumentBody = {
        dataStream,
        paragraphs,
        sectionBreaks,
        textRuns,
        tables,
        customBlocks: [],
        customRanges: [],
        customDecorations: [],
        columnGroups: [],
        blockRanges: [],
    };

    snapshot.body = body;
    snapshot.tableSource = tableSource;
    snapshot.settings = {
        ...snapshot.settings,
        zoomRatio: 1,
    };

    return snapshot;
}
