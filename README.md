# Univer — app de saída da exportação

Aplicação independente (backend Python + frontend React/Vite) que lê um projeto
`.md` e mostra/exporta a saída da exportação com o
[Univer](https://univer.ai) — o `.xlsx` multi-bay gerado pelo backend e o
relatório `.docx`.

> Esta aplicação foi extraída do monorepo do Univer (antes `tests/nexus`) e
> renomeada de **Nexus** para **Univer**. Ela agora é **independente**: o
> frontend consome os pacotes `@univerjs/*` publicados no npm (versão `1.0.3`,
> em vez de `workspace:*`) e pode ser movida/cloneada para qualquer lugar.

## Estrutura

```
univer-app/
  backend/          API HTTP local (FastAPI) + núcleo headless (Python)
    api.py          `python -m backend.api` a partir da raiz deste diretório
    core/           caminhos, config, logging, banco de costura
    processing/     exportação .xlsx/.docx e snapshots do Univer
    sidecar/        estado e serviço headless
    Modules/        templates Excel, modelos .docx e a semente nexus_costura.db
  frontend/         React + Vite + Univer (pacote `univer-frontend`)
    src/            api.ts, App.tsx, UniverSheet.tsx, UniverDoc.tsx, ...
  docs/
    UNIVER_INTEGRATION.md   guia de integração do Univer nesta aplicação
    univer/                 documentação original do Univer (cópia do repo)
  .gitignore
```

## Rodando

### Backend

```bash
cd univer-app
python -m venv backend/venv          # primeira vez
backend/venv/Scripts/pip install -r backend/requirements.txt   # Windows
# fonte: backend/venv/bin/pip install -r backend/requirements.txt (Linux/macOS)
python -m backend.api
```

A API sobe em <http://127.0.0.1:8000> com CORS liberado para `localhost:5173`.

### Frontend

```bash
cd univer-app/frontend
pnpm install
pnpm dev
```

A aplicação sobe em <http://localhost:5173> (`strictPort`).

## Variáveis de ambiente

| Variável               | Padrão                  | Descrição                                    |
| ---------------------- | ----------------------- | -------------------------------------------- |
| `VITE_UNIVER_API_BASE` | `http://127.0.0.1:8000` | Base da API do backend (lado frontend, `.env`) |
| `UNIVER_API_HOST`      | `127.0.0.1`             | Host da API (lado backend)                   |
| `UNIVER_API_PORT`      | `8000`                  | Porta da API (lado backend)                  |
| `UNIVER_DATA_DIR`      | `%LOCALAPPDATA%\NEXUS`  | Diretório gravável de dados do usuário       |
| `NEXUS_DATA_DIR`       | —                       | Nome antigo de `UNIVER_DATA_DIR` (compatibilidade) |

## O que a tela faz

1. **Carrega um projeto `.md`** — **Escolher arquivo…** abre o diálogo nativo
   (`POST /api/project/pick`, a janela abre no backend — ele roda na sua
   máquina) ou digite o caminho e clique em **Carregar**
   (`POST /api/project/load`). O projeto abre no núcleo headless do backend
   (`backend.sidecar.service`) e a saída é gerada de novo em seguida.
2. **Mostra a saída da exportação** — `POST /api/export/all-bays/univer` roda o
   mesmo `ExcelProcessor` da exportação (templates + openpyxl) **em memória** e
   devolve as abas em JSON — valores, estilos, mesclagens, larguras e
   visibilidade (`processing/workbook/univer_snapshot.py`). O Univer monta uma
   aba por sheet (`Sumário Geral`, `Total Geral` e uma aba por bay), marcada
   como leitura. Cada seção de equipamento vira uma **tabela do Univer**
   (`@univerjs/preset-sheets-table`, com cabeçalho e filtros).
3. **Exporta o relatório `.docx`** — `POST /api/export/docx` preenche o modelo
   Word de `Modules/docs` com as tabelas de todos os bays
   (`processing/docx/docx_exporter.py`) e abre o arquivo no aplicativo padrão.
   Alternativamente, **Carregar Doc** (`POST /api/export/docx/univer`) carrega
   o documento em memória direto na tela no **Univer Doc**. Um seletor alterna
   entre **Planilha** e **Documento**.

Rotas antigas seguem disponíveis na API: `GET /api/sheet/preview`,
`POST /api/bays/{bay}/cables`, `POST /api/export/all-bays` + `GET /api/download`.

## Modo demo

Se o núcleo headless não puder ser importado (ex.: `backend/core` ausente), a
API sobe em **modo demo** com um projeto de exemplo em memória — a tela
funciona inteira, mas as exportações mexem só na memória do processo. O badge no
topo indica o modo (`API: backend` ou `API: demo`).

## Notas sobre a separação (Nexus → Univer)

- **Mantido por compatibilidade com dados existentes:** o banco
  `nexus_costura.db`, a pasta de dados `%LOCALAPPDATA%\NEXUS` e o diretório de
  exportações `~/nexus_exports`. Quem já usava a versão Nexus continua com os
  mesmos dados.
- **Renomeado (código/marca):** pacote `univer-frontend`, variáveis
  `UNIVER_API_*` / `VITE_UNIVER_API_BASE` / `UNIVER_DATA_DIR`, textos da UI
  (`Univer — Saída da exportação`), classes CSS `app-*` (antes `nexus-*`,
  prefixo evitado para não colidir com as classes `univer-*` do próprio
  Univer), logger `univer` e log `univer.log`.
- **Fora do workspace:** nada aqui usa `workspace:*`; `pnpm install` aqui é
  independente do monorepo.

## Documentação

- [`docs/UNIVER_INTEGRATION.md`](docs/UNIVER_INTEGRATION.md) — como o Univer é
  instalado e usado nesta aplicação (guia para trazer o Univer para outra app).
- [`docs/univer/README.md`](docs/univer/README.md) — README original do projeto
  Univer, mais [`docs/univer/`](docs/univer/) com a documentação do repositório
  original (API stability, naming, arquitetura em `tldr/` etc.).
- [docs.univer.ai](https://docs.univer.ai) — documentação oficial.
