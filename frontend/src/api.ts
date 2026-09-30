/**
 * Cliente da API HTTP do backend Univer (`backend/api.py`).
 *
 * A base pode ser trocada por `VITE_UNIVER_API_BASE` no `.env` do frontend.
 */

export const API_BASE: string =
    (import.meta.env.VITE_UNIVER_API_BASE as string | undefined) ?? 'http://127.0.0.1:8000';

export interface Health {
    status: string;
    modo: 'backend' | 'demo';
    erro_backend: string | null;
    versao: string;
}

/** Estilo de uma célula da saída, com nomes neutros (o frontend converte). */
export interface OutputCellStyle {
    bold?: boolean;
    italic?: boolean;
    size?: number;
    /** Cor da fonte, `#rrggbb`. */
    color?: string;
    /** Preenchimento sólido da célula, `#rrggbb`. */
    fill?: string;
    hAlign?: 'left' | 'center' | 'right' | 'justify';
    vAlign?: 'top' | 'center' | 'bottom';
    wrap?: boolean;
    numberFormat?: string;
    border?: Partial<
        Record<'top' | 'bottom' | 'left' | 'right', { style: string; color?: string }>
    >;
}

/** Uma aba da saída (o `.xlsx` gerado pelo backend) pronta para o Univer. */
export interface OutputSheet {
    name: string;
    /** Valores por linha; `null` é célula vazia. */
    rows: (string | number | boolean | null)[][];
    /** Combinações de estilo usadas na aba (deduplicadas pelo backend). */
    styles?: OutputCellStyle[];
    /** Índice em `styles` por célula, na mesma malha de `rows`; `null` = sem estilo. */
    styleIndex?: (number | null)[][];
    /** Ranges mesclados, com índices 0-based. */
    merges?: { startRow: number; endRow: number; startColumn: number; endColumn: number }[];
    /** Larguras explícitas de coluna (em caracteres), indexadas pela coluna 0-based. */
    columnWidths?: Record<string, number>;
    hidden?: boolean;
}

/** Saída da exportação serializada para a tela (sem download). */
export interface OutputResult {
    status: string;
    modo?: 'backend' | 'demo';
    bays?: number;
    total?: number;
    mensagem?: string;
    erro_backend?: string | null;
    pulados?: { bay: string; motivo: string }[];
    sheets: OutputSheet[];
}

/** Resultado da exportação do relatório `.docx` (chaves do modelo). */
export interface DocxResult {
    status: string;
    /** Caminho do arquivo gerado pela máquina local. */
    arquivo?: string;
    bays?: number;
    /** Quantidade de tabelas inseridas nas chaves do modelo. */
    tabelas?: number;
    /** `true` quando o backend abriu o arquivo no aplicativo padrão. */
    aberto?: boolean;
    /** Motivo quando o arquivo não pôde ser aberto (a exportação segue válida). */
    aviso?: string;
    chaves_inseridas?: Record<string, string[]>;
    /** Chaves do modelo sem tabela correspondente (ficaram no documento). */
    chaves_sem_tabela?: string[];
    bays_sem_tabela?: Record<string, string[]>;
    pulados?: { bay: string; motivo: string }[];
    mensagem?: string;
}

export interface DocxUniverElementParagraph {
    type: 'paragraph';
    text: string;
    align?: 'left' | 'center' | 'right' | 'justify';
    runs?: Array<{
        text: string;
        bold?: boolean;
        italic?: boolean;
        fontSize?: number;
        color?: string;
    }>;
}

export interface DocxUniverElementHeading {
    type: 'heading';
    text: string;
    style?: {
        bold?: boolean;
        fontSize?: number;
        color?: string;
    };
}

export interface DocxUniverTableCell {
    text: string;
    bold?: boolean;
    italic?: boolean;
    align?: 'left' | 'center' | 'right';
    bg?: string;
    color?: string;
    rowSpan?: number;
    colSpan?: number;
}

export interface DocxUniverElementTable {
    type: 'table';
    tableId: string;
    sheetName?: string;
    bayName?: string;
    rowCount: number;
    colCount: number;
    columnWidths: number[];
    rows: DocxUniverTableCell[][];
    merges?: Array<{
        startRow: number;
        endRow: number;
        startCol: number;
        endCol: number;
    }>;
}

export type DocxUniverElement =
    | DocxUniverElementParagraph
    | DocxUniverElementHeading
    | DocxUniverElementTable;

export interface DocxUniverResult {
    status: 'sucesso' | 'erro';
    modo?: 'backend' | 'demo';
    template?: string;
    bays?: number;
    tabelas?: number;
    elements: DocxUniverElement[];
    chaves_inseridas?: Record<string, string[]>;
    chaves_sem_tabela?: string[];
    bays_sem_tabela?: Record<string, string[]>;
    pulados?: { bay: string; motivo: string }[];
    mensagem?: string;
}

export interface LoadResult {
    status: string;
    bays?: number;
    mensagem?: string;
}

/** Resultado da escolha do arquivo do projeto no diálogo nativo. */
export interface PickResult {
    /** `sucesso` | `cancelado` | `erro`. */
    status: string;
    /** Caminho escolhido (só em `sucesso`). */
    path?: string;
    mensagem?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, {
        ...init,
        headers: { 'content-type': 'application/json', ...(init?.headers ?? {}) },
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status} em ${path}`);
    }

    return (await response.json()) as T;
}

export const univerApi = {
    health: () => request<Health>('/api/health'),

    /** Abre o diálogo nativo "Abrir" no backend e devolve o caminho escolhido. */
    pickProject: () =>
        request<PickResult>('/api/project/pick', {
            method: 'POST',
        }),

    loadProject: (path: string) =>
        request<LoadResult>('/api/project/load', {
            method: 'POST',
            body: JSON.stringify({ path }),
        }),

    /** Zera o projeto aberto em memória (projeto vazio). */
    newProject: () =>
        request<{ status: string; mensagem?: string }>('/api/project/new', {
            method: 'POST',
        }),

    /** Gera a saída no backend e devolve as abas para montar no Univer. */
    exportAllBaysUniver: () =>
        request<OutputResult>('/api/export/all-bays/univer', {
            method: 'POST',
        }),

    /** Gera o relatório `.docx` com as tabelas dos bays nas chaves do modelo. */
    exportDocx: (payload?: { bay_id?: string; template_path?: string; output_path?: string }) =>
        request<DocxResult>('/api/export/docx', {
            method: 'POST',
            body: JSON.stringify(payload ?? {}),
        }),

    /** Gera o relatório `.pdf` com as tabelas dos bays nas chaves do modelo. */
    exportPdf: (payload?: { bay_id?: string; template_path?: string; output_path?: string }) =>
        request<DocxResult>('/api/export/pdf', {
            method: 'POST',
            body: JSON.stringify(payload ?? {}),
        }),

    /** Gera o relatório do modelo Word em memória e devolve os elementos para o Univer Doc. */
    exportDocxUniver: (payload?: { bay_id?: string; template_path?: string }) =>
        request<DocxUniverResult>('/api/export/docx/univer', {
            method: 'POST',
            body: JSON.stringify(payload ?? {}),
        }),
};
