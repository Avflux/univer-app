import { createRoot } from 'react-dom/client';

// Estilos do Univer publicados no npm. A ordem importa: `design` e `ui`
// primeiro, depois os CSS dos presets (mesma ordem recomendada na
// documentação oficial: https://docs.univer.ai).
import '@univerjs/design/lib/index.css';
import '@univerjs/ui/lib/index.css';
import '@univerjs/preset-docs-core/lib/index.css';
import '@univerjs/preset-docs-drawing/lib/index.css';
import '@univerjs/preset-docs-hyper-link/lib/index.css';
import '@univerjs/preset-docs-thread-comment/lib/index.css';
import '@univerjs/preset-sheets-conditional-formatting/lib/index.css';
import '@univerjs/preset-sheets-core/lib/index.css';
import '@univerjs/preset-sheets-data-validation/lib/index.css';
import '@univerjs/preset-sheets-drawing/lib/index.css';
import '@univerjs/preset-sheets-filter/lib/index.css';
import '@univerjs/preset-sheets-find-replace/lib/index.css';
import '@univerjs/preset-sheets-hyper-link/lib/index.css';
import '@univerjs/preset-sheets-note/lib/index.css';
import '@univerjs/preset-sheets-sort/lib/index.css';
import '@univerjs/preset-sheets-table/lib/index.css';
import '@univerjs/preset-sheets-thread-comment/lib/index.css';
import { App } from './App';
import './global.css';

const container = document.getElementById('root');

if (!container) {
    throw new Error('Elemento #root não encontrado no index.html.');
}

// Sem `StrictMode` de propósito: o Univer monta DOM/canvas de forma
// imperativa e o double-invoke dos efeitos em dev criaria duas instâncias.
createRoot(container).render(<App />);
