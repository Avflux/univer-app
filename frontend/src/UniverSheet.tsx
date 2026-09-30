import type { IWorkbookData } from '@univerjs/core';
import type { SheetTableSpec } from './workbook';
import { UniverSheetsConditionalFormattingPreset } from '@univerjs/preset-sheets-conditional-formatting';
import conditionalFormattingLocale from '@univerjs/preset-sheets-conditional-formatting/locales/pt-BR';
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import coreLocale from '@univerjs/preset-sheets-core/locales/pt-BR';
import { UniverSheetsDataValidationPreset } from '@univerjs/preset-sheets-data-validation';
import dataValidationLocale from '@univerjs/preset-sheets-data-validation/locales/pt-BR';
import { UniverSheetsDrawingPreset } from '@univerjs/preset-sheets-drawing';
import drawingLocale from '@univerjs/preset-sheets-drawing/locales/pt-BR';
import { UniverSheetsFilterPreset } from '@univerjs/preset-sheets-filter';
import filterLocale from '@univerjs/preset-sheets-filter/locales/pt-BR';
import { UniverSheetsFindReplacePreset } from '@univerjs/preset-sheets-find-replace';
import findReplaceLocale from '@univerjs/preset-sheets-find-replace/locales/pt-BR';
import { UniverSheetsHyperLinkPreset } from '@univerjs/preset-sheets-hyper-link';
import hyperLinkLocale from '@univerjs/preset-sheets-hyper-link/locales/pt-BR';
import { UniverSheetsNotePreset } from '@univerjs/preset-sheets-note';
import noteLocale from '@univerjs/preset-sheets-note/locales/pt-BR';
import { UniverSheetsSortPreset } from '@univerjs/preset-sheets-sort';
import sortLocale from '@univerjs/preset-sheets-sort/locales/pt-BR';
import { UniverSheetsTablePreset } from '@univerjs/preset-sheets-table';
import tableLocale from '@univerjs/preset-sheets-table/locales/pt-BR';
import { UniverSheetsThreadCommentPreset } from '@univerjs/preset-sheets-thread-comment';
import threadCommentLocale from '@univerjs/preset-sheets-thread-comment/locales/pt-BR';
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets';
import { useEffect, useRef } from 'react';

interface UniverSpreadsheetProps {
    snapshot: IWorkbookData;
    /** Seções da saída que viram tabelas do Univer (cabeçalho e filtros). */
    tables: SheetTableSpec[];
}

/**
 * Monta uma instância do Univer dentro de um `div`.
 *
 * Cada `snapshot` novo recria a instância (o chamador troca a `key` do
 * componente para forçar o remount), o que mantém o ciclo de vida simples:
 * um Univer por snapshot.
 */
export function UniverSpreadsheet({ snapshot, tables }: UniverSpreadsheetProps) {
    const containerRef = useRef<HTMLDivElement>(null);
    const tablesRef = useRef(tables);
    tablesRef.current = tables;

    useEffect(() => {
        const container = containerRef.current;
        if (!container) {
            return undefined;
        }

        const { univer, univerAPI } = createUniver({
            locale: LocaleType.PT_BR,
            locales: {
                [LocaleType.PT_BR]: mergeLocales(
                    coreLocale,
                    tableLocale,
                    drawingLocale,
                    conditionalFormattingLocale,
                    dataValidationLocale,
                    filterLocale,
                    findReplaceLocale,
                    hyperLinkLocale,
                    noteLocale,
                    sortLocale,
                    threadCommentLocale
                ),
            },
            presets: [
                UniverSheetsCorePreset({
                    container,
                    ribbonType: 'grid',
                }),
                UniverSheetsDrawingPreset(),
                UniverSheetsConditionalFormattingPreset(),
                UniverSheetsDataValidationPreset(),
                UniverSheetsFilterPreset(),
                UniverSheetsFindReplacePreset(),
                UniverSheetsHyperLinkPreset(),
                UniverSheetsNotePreset(),
                UniverSheetsSortPreset(),
                UniverSheetsTablePreset(),
                UniverSheetsThreadCommentPreset(),
            ],
        });

        univerAPI.createWorkbook(snapshot);

        // As tabelas são comandos assíncronos, registrados em ordem depois de o
        // workbook existir. Uma seção recusada (nome ou intervalo inválido) só
        // deixa a aba sem aquela tabela — não derruba a tela.
        let disposed = false;
        const workbook = univerAPI.getActiveWorkbook();
        void (async () => {
            for (const table of tablesRef.current) {
                if (disposed) {
                    return;
                }
                const worksheet = workbook?.getSheetBySheetId(table.sheetId);
                await worksheet?.addTable(table.name, table.range, `${table.sheetId}-${table.name}`);
            }
        })();

        return () => {
            disposed = true;
            univer.dispose();
        };
    }, [snapshot]);

    return <div className="app-sheet" ref={containerRef} />;
}
