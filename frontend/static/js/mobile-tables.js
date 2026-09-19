import { refreshNumberPickers } from './mobile-number-pickers.js?v=1';

// Decorate the existing cells, preserving all trading controls and listeners.
export function decorateTradingTables(root = document) {
    root.querySelectorAll('main .table-responsive table').forEach(table => {
        const headers = Array.from(table.tHead?.rows[0]?.cells || []);
        if (!headers.length) return;
        table.classList.add('mobile-records');
        for (const body of table.tBodies) {
            for (const row of body.rows) {
                const spanning = Array.from(row.cells).some(cell => cell.colSpan > 1);
                row.classList.toggle('mobile-spanning-row', spanning);
                let column = 0;
                for (const cell of row.cells) {
                    const header = headers[column];
                    const label = header?.textContent.trim() || '';
                    const key = header?.dataset.i18n || '';
                    cell.dataset.mobileLabel = spanning ? '' : label;
                    cell.classList.toggle('mobile-identity', !spanning && (
                        ['common.symbol', 'common.ticker'].includes(key) || /^(Ticker|Symbol|标的|代码|股票代码)$/i.test(label)
                    ));
                    cell.classList.toggle('mobile-actions', !spanning && (
                        ['common.action', 'common.actions'].includes(key) || /^(Actions?|操作)$/i.test(label)
                    ) && Boolean(cell.querySelector('button')));
                    cell.classList.toggle('mobile-status', !spanning && (
                        key === 'common.status' || /^(Status|状态)$/i.test(label)
                    ));
                    column += cell.colSpan;
                }
            }
        }
    });
}

if (typeof document !== 'undefined') {
    let scheduled = false;
    const refresh = () => {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => {
            scheduled = false;
            decorateTradingTables();
            refreshNumberPickers();
        });
    };
    const start = () => {
        decorateTradingTables();
        refreshNumberPickers();
        const main = document.querySelector('main');
        if (main) new MutationObserver(refresh).observe(main, {
            childList: true, subtree: true, characterData: true,
            attributes: true, attributeFilter: ['disabled', 'min', 'max']
        });
        document.addEventListener('languageChanged', refresh);
        document.addEventListener('input', refresh);
        document.addEventListener('change', refresh);
        matchMedia('(max-width: 575.98px)').addEventListener('change', refresh);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, {once: true});
    else start();
}
