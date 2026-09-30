/**
 * Tema claro/escuro da aplicação.
 *
 * O tema ativo vive em `<html data-theme="light|dark">` (mais `color-scheme`,
 * para as barras de rolagem nativas acompanhararem) — é o que o CSS de
 * `global.css` usa para trocar os tokens. A escolha fica salva em
 * `localStorage`; sem escolha salva, vale o `prefers-color-scheme` do sistema.
 */

export type Theme = 'light' | 'dark';

export const THEME_STORAGE_KEY = 'univer-theme';

/** Escolha salva pelo usuário, ou `null` quando não há (ou está inválida). */
function storedTheme(): Theme | null {
    try {
        const value = localStorage.getItem(THEME_STORAGE_KEY);
        return value === 'light' || value === 'dark' ? value : null;
    } catch {
        // localStorage indisponível (modo privado, cota, …).
        return null;
    }
}

/** Tema inicial: o salvo, senão o preferido pelo sistema. */
export function getInitialTheme(): Theme {
    const saved = storedTheme();
    if (saved) {
        return saved;
    }
    return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Aplica o tema no documento (sem persistir — ver `saveTheme`). */
export function applyTheme(theme: Theme): void {
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
}

/** Persiste a escolha do usuário para as próximas aberturas. */
export function saveTheme(theme: Theme): void {
    try {
        localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
        // Sem persistência o tema ainda vale para a sessão corrente.
    }
}
