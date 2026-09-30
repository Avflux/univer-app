import autoprefixer from 'autoprefixer';
import env from 'postcss-preset-env';
import replace from 'postcss-replace';
import tailwindcss from 'tailwindcss';

/**
 * PostCSS inlinado de `@univerjs-infra/shared/postcss` — pacote interno do
 * monorepo do Univer, indisponível fora do workspace. Mantém o mesmo pipeline
 * (tailwind → autoprefixer → postcss-preset-env → renomeia `--tw` para não
 * colidir com as variáveis do Univer).
 *
 * @type {import('postcss-load-config').Config}
 */
const config = {
    plugins: [
        tailwindcss,
        autoprefixer,
        env({
            features: {
                'color-functional-notation': true,
                'hexadecimal-alpha-notation': true,
            },
        }),
        replace({
            pattern: /(--tw|\*)/g,
            data: {
                '--tw': '--univer-tw',
            },
        }),
    ],
};

export default config;
