import type { DocxUniverResult, OutputResult } from '../api';
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { API_BASE, univerApi } from '../api';
import { buildOutputDocument } from '../document';
import { UniverDocument } from '../UniverDoc';
import { UniverSpreadsheet } from '../UniverSheet';
import { buildOutputWorkbook } from '../workbook';
import { applyTheme, getInitialTheme, saveTheme } from './theme';
import type { Theme } from './theme';

interface StatusMessage {
    tipo: 'ok' | 'erro' | 'info';
    texto: string;
    /** Link de download do arquivo gerado (ex.: o .docx exportado). */
    href?: string;
}

/** Mensagem do backend quando o projeto aberto não contém nenhum bay. */
const MSG_NENHUM_BAY = 'Nenhum bay encontrado no projeto.';

export function App() {
    const [output, setOutput] = useState<OutputResult | null>(null);
    const [docResult, setDocResult] = useState<DocxUniverResult | null>(null);
    const [view, setView] = useState<'sheet' | 'doc'>('sheet');
    const [revision, setRevision] = useState(0);
    const [message, setMessage] = useState<StatusMessage | null>(null);
    const [loading, setLoading] = useState(true);
    const [busy, setBusy] = useState(false);
    const [loadingProject, setLoadingProject] = useState(false);
    /** Tema da aplicação (claro/escuro) — persistido em `localStorage`. */
    const [theme, setTheme] = useState<Theme>(() => getInitialTheme());
    /** Pausa a contagem do toast enquanto o mouse está sobre ele. */
    const [toastPaused, setToastPaused] = useState(false);

    /**
     * `true` depois que um `.md` é carregado nesta sessão. A tela inicial não
     * tem arquivo aberto, então o aviso de "nenhum bay" não faz sentido ali —
     * ele só aparece quando o arquivo carregado veio sem bay.
     */
    const projectLoadedRef = useRef(false);

    /**
     * O backend é um processo separado: o projeto aberto sobrevive ao F5.
     * Este guard faz com que só a primeira carga (montagem da tela) zere o
     * backend — recarregar a página volta o app ao estado inicial vazio.
     */
    const resetBackendRef = useRef(false);

    useLayoutEffect(() => {
        applyTheme(theme);
    }, [theme]);

    /**
     * O aviso não é mais uma faixa que ocupa a janela: é um toast flutuante
     * que some sozinho — mais tempo para erro e para mensagens com link de
     * download, e a contagem pausa quando o mouse fica sobre ele.
     */
    useEffect(() => {
        if (!message || toastPaused) {
            return undefined;
        }
        const duracao = message.href ? 15000 : message.tipo === 'erro' ? 10000 : 6000;
        const timer = window.setTimeout(() => setMessage(null), duracao);
        return () => window.clearTimeout(timer);
    }, [message, toastPaused]);

    /** Alterna entre claro e escuro, guardando a escolha do usuário. */
    const toggleTheme = useCallback(() => {
        const next: Theme = theme === 'dark' ? 'light' : 'dark';
        setTheme(next);
        saveTheme(next);
    }, [theme]);

    /**
     * Reescreve o aviso de "nenhum bay" quando nenhum `.md` foi carregado:
     * ali o problema é a falta de projeto, não o arquivo. Com um projeto
     * aberto a mensagem original passa direto — é o único caso em que
     * "Nenhum bay encontrado no projeto." deve aparecer.
     */
    const mensagemComProjeto = useCallback(
        (texto: string): string =>
            !projectLoadedRef.current && texto === MSG_NENHUM_BAY
                ? 'Nenhum projeto carregado. Abra um arquivo .md para continuar.'
                : texto,
        []
    );

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
            // Só para confirmar que a API responde antes de gerar a saída —
            // falhou aqui, cai no catch abaixo.
            await univerApi.health();

            // F5 não limpa o estado do backend, então ele é zerado aqui na
            // primeira carga. A resposta é ignorada de propósito: no modo
            // demo não há serviço para zerar e isso não pode derrubar a tela.
            if (!resetBackendRef.current) {
                resetBackendRef.current = true;
                await univerApi.newProject().catch(() => undefined);
            }

            const status = await generateOutput();
            setMessage(
                !projectLoadedRef.current && status.texto === MSG_NENHUM_BAY
                    ? null
                    : status
            );
        } catch (error) {
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
                    texto: mensagemComProjeto(
                        result.mensagem ?? 'Não foi possível carregar o modelo no Univer Doc.'
                    ),
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
    }, [mensagemComProjeto]);

    /** Pede ao backend que abra um projeto .md do disco. */
    const loadProject = useCallback(
        async (pathArg: string) => {
            const path = pathArg.trim();
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

                // Relê o projeto e remonta a saída com os dados recém-carregados.
                // `load()` limpa a mensagem, então ela é reposta depois.
                projectLoadedRef.current = true;
                await load();
                if (view === 'doc') {
                    await loadDoc();
                }
                const nome = path.split(/[\\/]/).pop() ?? path;
                // Sem bay no arquivo, o aviso do backend é o que interessa — é
                // o único caso em que "Nenhum bay encontrado" deve aparecer.
                setMessage(
                    result.bays
                        ? {
                              tipo: 'ok',
                              texto: `Projeto carregado: ${nome} (${result.bays} bay(s)).`,
                          }
                        : {
                              tipo: 'erro',
                              texto: `Projeto carregado: ${nome}. ${MSG_NENHUM_BAY}`,
                          }
                );
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
        [load, loadDoc, view]
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
                    texto: mensagemComProjeto(
                        result.mensagem ?? 'Não foi possível gerar o relatório .docx.'
                    ),
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
    }, [mensagemComProjeto]);

    /** Gera o relatório .pdf no backend (converte o .docx gerado em PDF nativo via Word). */
    const exportPdf = useCallback(async () => {
        setBusy(true);
        setMessage({ tipo: 'info', texto: 'Gerando o relatório .pdf…' });
        try {
            const result = await univerApi.exportPdf();
            if (result.status === 'sucesso' && result.arquivo) {
                const nome = result.arquivo.split(/[\\/]/).pop() ?? result.arquivo;
                setMessage({
                    tipo: 'ok',
                    texto: `${result.mensagem ?? `Relatório PDF gerado: ${nome}`} `,
                    href: `${API_BASE}/api/download?path=${encodeURIComponent(result.arquivo)}`,
                });
            } else {
                setMessage({
                    tipo: 'erro',
                    texto: mensagemComProjeto(
                        result.mensagem ?? 'Não foi possível gerar o relatório .pdf.'
                    ),
                });
            }
        } catch (error) {
            setMessage({
                tipo: 'erro',
                texto: `Falha ao gerar o .pdf: ${
                    error instanceof Error ? error.message : String(error)
                }`,
            });
        } finally {
            setBusy(false);
        }
    }, [mensagemComProjeto]);

    const workbook = useMemo(() => (output ? buildOutputWorkbook(output) : null), [output]);
    const docSnapshot = useMemo(() => (docResult ? buildOutputDocument(docResult) : null), [docResult]);

    return (
        <div className="app-app">
            <header className="app-header">
                <div className="app-brand">
                    <span className="app-logo" aria-hidden="true">N</span>
                    <h1 className="app-title">Univer</h1>
                </div>

                <div className="app-actions">
                    <button
                        className="app-button"
                        data-variant="primary"
                        disabled={loadingProject || busy}
                        onClick={() => void chooseProject()}
                    >
                        Carregar arquivo…
                    </button>
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
                        Gerar Doc
                    </button>
                    <button
                        className="app-button"
                        disabled={busy || loading}
                        onClick={() => void exportDocx()}
                    >
                        Exportar .docx
                    </button>
                    <button
                        className="app-button"
                        disabled={busy || loading}
                        onClick={() => void exportPdf()}
                    >
                        Exportar .pdf
                    </button>
                    <button
                        className="app-button app-button--icon"
                        aria-label={theme === 'dark' ? 'Usar tema claro' : 'Usar tema escuro'}
                        aria-pressed={theme === 'dark'}
                        disabled={busy || loading}
                        onClick={toggleTheme}
                        title={theme === 'dark' ? 'Usar tema claro' : 'Usar tema escuro'}
                    >
                        {theme === 'dark' ? '☀️' : '🌙'}
                    </button>
                </div>
            </header>

            {message && (
                <div
                    aria-live="polite"
                    className="app-toast"
                    data-tipo={message.tipo}
                    role="status"
                    onMouseEnter={() => setToastPaused(true)}
                    onMouseLeave={() => setToastPaused(false)}
                >
                    <span className="app-toast-text">{message.texto}</span>
                    {message.href && (
                        <a
                            className="app-toast-link"
                            href={message.href}
                            rel="noreferrer"
                            target="_blank"
                        >
                            baixar arquivo
                        </a>
                    )}
                    <button
                        aria-label="Fechar aviso"
                        className="app-toast-close"
                        onClick={() => setMessage(null)}
                        type="button"
                    >
                        ×
                    </button>
                </div>
            )}

            <div className="app-body">
                {view === 'doc' && docSnapshot
                    ? (
                        <UniverDocument
                            key={`doc-${revision}`}
                            snapshot={docSnapshot}
                            dark={theme === 'dark'}
                        />
                    )
                    : workbook
                        ? (
                            <UniverSpreadsheet
                                key={`saida-${revision}`}
                                snapshot={workbook.snapshot}
                                tables={workbook.tables}
                                dark={theme === 'dark'}
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
