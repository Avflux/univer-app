import type { Config } from 'tailwindcss';
import animate from 'tailwindcss-animate';

/**
 * Preset do Tailwind inlinado de `@univerjs-infra/shared/tailwind` — pacote
 * interno do monorepo do Univer, indisponível fora do workspace.
 *
 * A UI do Univer já vem compilada nos CSS publicados no npm
 * (`@univerjs/<pkg>/lib/index.css`, importados em `src/main.tsx`), então por
 * aqui só as classes do próprio app são geradas. O prefixo `univer-` é
 * mantido por consistência com o ecossistema Univer.
 */
const config: Config = {
    prefix: 'univer-',
    darkMode: 'selector',
    future: {
        hoverOnlyWhenSupported: true,
    },
    corePlugins: {
        preflight: false,
    },
    content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
    plugins: [animate],
};

export default config;
