import type { UserConfig } from 'vite';
import { defineConfig } from 'vite';

/**
 * Não usamos `@vitejs/plugin-react`: o Vite 8 (oxc/rolldown) já transforma os
 * `.tsx` com o runtime automático do React por padrão. Não há Fast Refresh —
 * edite e recarregue a página.
 */
export default defineConfig(({ command, mode }): UserConfig => ({
    build: {
        sourcemap: false,
    },
    experimental: {
        bundledDev: command === 'serve' && mode !== 'test',
    },
    preview: {
        port: 5173,
        strictPort: true,
    },
    server: {
        port: 5173,
        strictPort: true,
    },
}));
