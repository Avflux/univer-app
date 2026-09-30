import type { IDocumentData } from '@univerjs/core';
import { UniverDocsCorePreset } from '@univerjs/preset-docs-core';
import docsLocale from '@univerjs/preset-docs-core/locales/pt-BR';
import { UniverDocsDrawingPreset } from '@univerjs/preset-docs-drawing';
import docsDrawingLocale from '@univerjs/preset-docs-drawing/locales/pt-BR';
import { UniverDocsHyperLinkPreset } from '@univerjs/preset-docs-hyper-link';
import docsHyperLinkLocale from '@univerjs/preset-docs-hyper-link/locales/pt-BR';
import { UniverDocsThreadCommentPreset } from '@univerjs/preset-docs-thread-comment';
import docsThreadCommentLocale from '@univerjs/preset-docs-thread-comment/locales/pt-BR';
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets';
import { useEffect, useRef } from 'react';

export interface UniverDocumentProps {
    snapshot: IDocumentData;
}

/**
 * Monta uma instância do Univer Doc dentro de um container div.
 *
 * Cada snapshot novo remonta a instância do Univer para isolar o ciclo de vida.
 */
export function UniverDocument({ snapshot }: UniverDocumentProps) {
    const containerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const container = containerRef.current;
        if (!container) {
            return undefined;
        }

        const { univer, univerAPI } = createUniver({
            locale: LocaleType.PT_BR,
            locales: {
                [LocaleType.PT_BR]: mergeLocales(
                    docsLocale,
                    docsDrawingLocale,
                    docsHyperLinkLocale,
                    docsThreadCommentLocale
                ),
            },
            presets: [
                UniverDocsCorePreset({
                    container,
                    ribbonType: 'grid',
                    toc: true,
                }),
                UniverDocsDrawingPreset(),
                UniverDocsHyperLinkPreset(),
                UniverDocsThreadCommentPreset(),
            ],
        });

        univerAPI.createDocument(snapshot);

        return () => {
            univer.dispose();
        };
    }, [snapshot]);

    return <div className="app-sheet app-doc" ref={containerRef} />;
}
