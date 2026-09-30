import type { DocxUniverResult, Health, OutputResult } from '../api';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { API_BASE, univerApi } from '../api';
import { buildOutputDocument } from '../document';
import { UniverDocument } from '../UniverDoc';
import { UniverSpreadsheet } from '../UniverSheet';
import { buildOutputWorkbook } from '../workbook';

interface StatusMessage {
    tipo: 'ok' | 'erro' | 'info';
    texto: string;
    /** Link de download do arquivo gerado (ex.: o .docx exportado). */
    href?: string;
}

export function App() {
    const [health, setHealth] = useState<Health | null>(null);
    const [output, setOutput] = useState<OutputResult | null>(null);
    const [docResult, setDocResult] = useState<DocxUniverResult | null>(null);
    const [view, setView] = useState<'sheet' | 'doc'>('sheet');
    const [revision, setRevision] = useState(0);
    const [message, setMessage] = useState<StatusMessage | null>(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [projectPath, setProjectPath] = useState('');
    const [loadingProject, setLoadingProject] = useState(false);

    /**
     * Gera a tabela de saída no backend e devolve a mensagem de status, sem
     * mexer em `busy` — quem chama decide se a tela está em espera.
     */
    const generateOutput = useCallback(async (): Promise<StatusMessage> => {
        try {
            const result = await univerApi.exportAllBaysUniver();
            if (result.status === 'sucesso' && result.sheets.length > 0) {
                setOutput(result);
                setRevision((current) => current + 1);
                return {
                    tipo: 'ok',
                    texto: `${result.mensagem ?? 'Saída gerada.'} ${
                        result.pulados?.length
                            ? `${result.pulados.length} bay(s) pulado(s). `
                            : ''
                    }Abas carregadas no Univer (somente leitura).`,
                };
            }
            return {
                tipo: 'erro',
                texto: result.mensagem ?? 'Não foi possível gerar a saída.',
            };
        } catch (error) {
            return {
                tipo: 'erro',
                texto: `Falha na exportação: ${
                    error instanceof Error ? error.message : String(error)
                }`,
            };
        }
    }, []);

    /** Lê o projeto no backend e monta a tabela de saída na tela. */
    const load = useCallback(async () => {
        setLoading(true);
        setMessage(null);
        try {
            const healthResult = await univerApi.health();
            setHealth(healthResult);
            setMessage(await generateOutput());
        } catch (error) {
            setHealth(null);
            setOutput(null);
            setMessage({
                tipo: 'erro',
                texto: `Não foi possível falar com a API em ${API_BASE}. Suba o backend com "python -m backend.api". (${
                    error instanceof Error ? error.message : String(error)
                })`,
            });
        } finally {
            setLoading(false);
        }
    }, [generateOutput]);

    useEffect(() => {
        void load();
    }, [load]);

    /**
     * Carrega a formatação do modelo Word com as tabelas de equipamento
     * diretamente no Univer Doc.
     */
    const loadDoc = useCallback(async () => {
        setBusy(true);
        setMessage({ tipo: 'info', texto: 'Carregando o modelo no Univer Doc…' });
        try {
            const result = await univerApi.exportDocxUniver();
            if (result.status === 'sucesso' && result.elements.length > 0) {
                setDocResult(result);
                setView('doc');
                setRevision((current) => current + 1);
                setMessage({
                    tipo: 'ok',
                    texto: result.mensagem ?? 'Modelo carregado no Univer Doc.',
                });
            } else {
                setMessage({
                    tipo: 'erro',
                    texto: result.mensagem ?? 'Não foi possível carregar o modelo no Univer Doc.',
                });
            }
        } catch (error) {
            setMessage({
                tipo: 'erro',
                texto: `Falha ao carregar o modelo no Univer Doc: ${
                    error instanceof Error ? error.message : String(error)
                }`,
            });
        } finally {
            setBusy(false);
        }
    }, []);

    /** Pede ao backend que abra um projeto .md do disco. */
    const loadProject = useCallback(
        async (pathArg?: string) => {
            const path = (pathArg ?? projectPath).trim();
            if (!path) {
                setMessage({ tipo: 'erro', texto: 'Informe o caminho de um arquivo .md de projeto.' });
                return;
            }

            setLoadingProject(true);
            try {
                const result = await univerApi.loadProject(path);
                if (result.status !== 'sucesso') {
                    setMessage({
                        tipo: 'erro',
                        texto: result.mensagem ?? 'Não foi possível carregar o projeto.',
                    });
                    return;
                }

                // Reflete o caminho realmente carregado (inclusive o escolhido no
                // diálogo nativo) na barra de projeto.
                setProjectPath(path);

                // Relê o projeto e remonta a saída com os dados recém-carregados.
                // `load()` limpa a mensagem, então ela é reposta depois.
                await load();
                if (view === 'doc') {
                    await loadDoc();
                }
                const nome = path.split(/[\\/]/).pop() ?? path;
                setMessage({
                    tipo: 'ok',
                    texto: `Projeto carregado: ${nome} (${result.bays ?? 0} bay(s)).`,
                });
            } catch (error) {
                setMessage({
                    tipo: 'erro',
                    texto: `Falha ao carregar o projeto: ${
                        error instanceof Error ? error.message : String(error)
                    }`,
                });
            } finally {
                setLoadingProject(false);
            }
        },
        [load, projectPath]
    );

    /** Abre o diálogo nativo "Abrir" no backend e carrega o .md escolhido. */
    const chooseProject = useCallback(async () => {
        setMessage({ tipo: 'info', texto: 'Escolha o arquivo do projeto…' });
        try {
            const picked = await univerApi.pickProject();
            if (picked.status === 'sucesso' && picked.path) {
                await loadProject(picked.path);
                return;
            }
            if (picked.status === 'erro') {
                setMessage({
                    tipo: 'erro',
                    texto: picked.mensagem ?? 'Não foi possível abrir o diálogo de arquivo.',
                });
                return;
            }
            // Cancelado: remove o aviso de "escolha o arquivo".
            setMessage(null);
        } catch (error) {
            setMessage({
                tipo: 'erro',
                texto: `Falha ao escolher o arquivo: ${
                    error instanceof Error ? error.message : String(error)
                }`,
            });
        }
    }, [loadProject]);

    /** Gera a saída no backend e monta as abas no Univer, sem baixar o .xlsx. */
    const loadOutput = useCallback(async () => {
        setBusy(true);
        setMessage({ tipo: 'info', texto: 'Gerando a saída no backend…' });
        setMessage(await generateOutput());
        setBusy(false);
    }, [generateOutput]);

    /** Gera o relatório .docx no backend (tabelas nas chaves do modelo). */
    const exportDocx = useCallback(async () => {
        setBusy(true);
        setMessage({ tipo: 'info', texto: 'Gerando o relatório .docx…' });
        try {
            const result = await univerApi.exportDocx();
            if (result.status === 'sucesso' && result.arquivo) {
                const nome = result.arquivo.split(/[\\/]/).pop() ?? result.arquivo;
                setMessage({
                    tipo: 'ok',
                    texto: `${result.mensagem ?? `Relatório gerado: ${nome}`} `,
                    href: `${API_BASE}/api/download?path=${encodeURIComponent(result.arquivo)}`,
                });
            } else {
                setMessage({
                    tipo: 'erro',
                    texto: result.mensagem ?? 'Não foi possível gerar o relatório .docx.',
                });
            }
        } catch (error) {
            setMessage({
                tipo: 'erro',
                texto: `Falha ao gerar o .docx: ${
                    error instanceof Error ? error.message : String(error)
                }`,
            });
        } finally {
            setBusy(false);
        }
    }, []);

    const workbook = useMemo(() => (output ? buildOutputWorkbook(output) : null), [output]);
    const docSnapshot = useMemo(() => (docResult ? buildOutputDocument(docResult) : null), [docResult]);
    const modo = health?.modo ?? 'erro';

    return (
        <div className="app-app">
            <header className="app-header">
                <div className="app-brand">
                    <span className="app-logo" aria-hidden="true">N</span>
                    <h1 className="app-title">Univer — Saída da exportação</h1>
                    <span className="app-badge" data-modo={modo}>
                        {health ? `API: ${modo}` : 'API offline'}
                    </span>
                    <span className="app-badge" data-modo="saida">
                        {view === 'doc' ? 'univer doc' : 'somente leitura'}
                    </span>
                </div>

                <div className="app-actions">
                    <span className="app-api-base" title={API_BASE}>{API_BASE}</span>
                    {output && docResult && (
                        <div className="app-view-switch" role="group" aria-label="Modo de visualização">
                            <button
                                className="app-button"
                                data-variant={view === 'sheet' ? 'primary' : undefined}
                                disabled={busy || loading}
                                onClick={() => setView('sheet')}
                                title="Ver planilha de saída"
                            >
                                Planilha
                            </button>
                            <button
                                className="app-button"
                                data-variant={view === 'doc' ? 'primary' : undefined}
                                disabled={busy || loading}
                                onClick={() => setView('doc')}
                                title="Ver documento do modelo"
                            >
                                Documento
                            </button>
                        </div>
                    )}
                    <button
                        className="app-button"
                        data-variant="primary"
                        disabled={busy || loading}
                        onClick={() => void loadDoc()}
                    >
                        Carregar Doc
                    </button>
                    <button
                        className="app-button"
                        disabled={busy || loading}
                        onClick={() => void exportDocx()}
                    >
                        Exportar .docx
                    </button>
                </div>
            </header>

            <div className="app-project-bar">
                <label htmlFor="app-project-path">Projeto (.md)</label>
                <input
                    className="app-input"
                    id="app-project-path"
                    onChange={(event) => setProjectPath(event.target.value)}
                    onKeyDown={(event) => {
                        if (event.key === 'Enter') {
                            void loadProject();
                        }
                    }}
                    placeholder="Escolha um arquivo .md ou digite o caminho"
                    spellCheck={false}
                    value={projectPath}
                />
                <button
                    className="app-button"
                    data-variant="primary"
                    disabled={loadingProject || busy}
                    onClick={() => void chooseProject()}
                >
                    Escolher arquivo…
                </button>
                <button
                    className="app-button"
                    disabled={loadingProject || busy || !projectPath.trim()}
                    onClick={() => void loadProject()}
                >
                    Carregar
                </button>
            </div>

            {message && (
                <div className="app-status" data-tipo={message.tipo}>
                    {message.texto}
                    {message.href && (
                        <a href={message.href} target="_blank" rel="noreferrer">
                            baixar arquivo
                        </a>
                    )}
                </div>
            )}

            <div className="app-body">
                {view === 'doc' && docSnapshot
                    ? (
                        <UniverDocument
                            key={`doc-${revision}`}
                            snapshot={docSnapshot}
                        />
                    )
                    : workbook
                        ? (
                            <UniverSpreadsheet
                                key={`saida-${revision}`}
                                snapshot={workbook.snapshot}
                                tables={workbook.tables}
                            />
                        )
                        : (
                            <div className="app-sheet app-sheet-placeholder">
                                {loading || busy
                                    ? (view === 'doc' ? 'Carregando o modelo…' : 'Gerando a saída…')
                                    : 'Sem dados para exibir.'}
                            </div>
                        )}
            </div>
        </div>
    );
}
