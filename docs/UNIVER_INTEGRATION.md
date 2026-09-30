# Guia de integração do Univer

Como o [Univer](https://univer.ai) é instalado e usado nesta aplicação. Serve
de ponto de partida para trazer o Univer para **outra aplicação**.

Documentação oficial: [docs.univer.ai](https://docs.univer.ai) ·
Código-fonte: [github.com/dream-num/univer](https://github.com/dream-num/univer)

## 1. Instalação

```bash
pnpm add @univerjs/core @univerjs/design @univerjs/ui @univerjs/presets \
  @univerjs/preset-sheets-core @univerjs/preset-sheets-conditional-formatting \
  @univerjs/preset-sheets-data-validation @univerjs/preset-sheets-drawing \
  @univerjs/preset-sheets-filter @univerjs/preset-sheets-find-replace \
  @univerjs/preset-sheets-hyper-link @univerjs/preset-sheets-note \
  @univerjs/preset-sheets-sort @univerjs/preset-sheets-table \
  @univerjs/preset-sheets-thread-comment \
  @univerjs/preset-docs-core @univerjs/preset-docs-drawing \
  @univerjs/preset-docs-hyper-link @univerjs/preset-docs-thread-comment
```

Regras importantes (documentação oficial):

- **Todas as dependências `@univerjs/*` na mesma versão** (aqui: `1.0.3`,
  fixada no `frontend/package.json`). Misturar versões quebra.
- **Não registrar um plugin que já existe no preset** — senão há conflito.
- `react`/`react-dom` são *peerDependencies*; o pnpm ≥ 8 instala sozinho.

## 2. Estilos (ordem importa)

A UI do Univer vem **compilada** nos pacotes npm — não é preciso varrer o
código do Univer com o Tailwind. Importe os CSS **antes** do CSS da sua app,
com `@univerjs/design` e `@univerjs/ui` primeiro
(`frontend/src/main.tsx`):

```ts
import '@univerjs/design/lib/index.css';
import '@univerjs/ui/lib/index.css';
import '@univerjs/preset-sheets-core/lib/index.css';
import '@univerjs/preset-docs-core/lib/index.css';
// ... um lib/index.css por preset usado
import './global.css'; // CSS da sua aplicação, por último
```

## 3. Criar uma instância (modo preset)

Modo preset = plugins pré-configurados, sem se preocupar com ordem de
registro. Exemplo real em `frontend/src/UniverSheet.tsx`:

```ts
import { createUniver, LocaleType, mergeLocales } from '@univerjs/presets';
import { UniverSheetsCorePreset } from '@univerjs/preset-sheets-core';
import coreLocale from '@univerjs/preset-sheets-core/locales/pt-BR';
import { UniverSheetsTablePreset } from '@univerjs/preset-sheets-table';
import tableLocale from '@univerjs/preset-sheets-table/locales/pt-BR';

const { univer, univerAPI } = createUniver({
    locale: LocaleType.PT_BR,
    locales: {
        [LocaleType.PT_BR]: mergeLocales(coreLocale, tableLocale /* ... */),
    },
    presets: [
        UniverSheetsCorePreset({ container, ribbonType: 'grid' }),
        UniverSheetsTablePreset(),
        // ...demais presets
    ],
});

univerAPI.createWorkbook(snapshot);   // IWorkbookData
// ...
univer.dispose();                     // desmonta no cleanup
```

Para documentos, o equivalente está em `frontend/src/UniverDoc.tsx`:
`UniverDocsCorePreset({ container, ribbonType: 'grid', toc: true })` +
`univerAPI.createDocument(snapshot)` (`IDocumentData`).

Pontos de integração usados aqui:

- **Container**: o Univer monta dentro de um `div` seu — a app controla o
  layout (`className="app-sheet"`).
- **Ciclo de vida**: um `createUniver` por `snapshot`; no React, `useEffect`
  com `univer.dispose()` no cleanup e `key` para forçar remount.
- **Somente leitura**: o resultado da exportação é visualização; as abas são
  montadas a partir do snapshot e não editadas.
- **Locales**: `LocaleType.PT_BR` com `mergeLocales(...)` de cada preset.
- **Tabelas**: `worksheet.addTable(nome, intervalo, id)` depois de
  `createWorkbook` (comandos assíncronos; uma recusa só deixa a aba sem tabela).

## 4. Snapshots (os dados)

A ponte entre backend e Univer são os *snapshots*:

- `IWorkbookData` — montado em `frontend/src/workbook.ts` a partir do JSON de
  `POST /api/export/all-bays/univer` (valores, estilos, mesclagens, larguras,
  visibilidade).
- `IDocumentData` — montado em `frontend/src/document.ts` a partir do modelo
  Word preenchido em memória pelo backend.

O backend gera esses payloads em
`backend/processing/workbook/univer_snapshot.py` (openpyxl → JSON) — o mesmo
caminho usado pela exportação real em disco.

## 5. Modo plugin (alternativa)

Para customização profunda, em vez dos presets registre os plugins na ordem
certa (`UniverRenderEnginePlugin`, `UniverUIPlugin`, `UniverSheetsPlugin`,
`UniverSheetsUIPlugin`, ...). Referência:
[Installation & Basic Usage](https://docs.univer.ai/guides/sheets/getting-started/installation).

## 6. Links úteis

- [Instalação — Sheets](https://docs.univer.ai/guides/sheets/getting-started/installation)
- [Instalação — Docs](https://docs.univer.ai/guides/docs/getting-started/installation)
- [Arquitetura do Univer](https://docs.univer.ai/guides/recipes/architecture/univer)
- [Facade API](https://docs.univer.ai/reference/classes/univer)
- [Repositório original](https://github.com/dream-num/univer) e
  [npm](https://www.npmjs.com/package/@univerjs/core)
- Documentação copiada do repositório original: [`univer/`](univer/)
  (estabilidade da API, convenção de nomes, memória, isomorfismo e diagramas
  em [`univer/tldr/`](univer/tldr))
