// Navigation is visual only: never trigger a trading control or change a quote.
export async function revealWorkflowTarget(element) {
    if (!element?.isConnected) return false;
    element.classList.add('workflow-target');
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    if (!element.isConnected) return false;
    element.scrollIntoView({behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center', inline: 'nearest'});
    window.setTimeout(() => element.classList.remove('workflow-target'), 2200);
    return true;
}

export function revealPendingOrder(orderId) {
    const body = document.getElementById('pending-orders-table-body') || document.getElementById('pending-orders-table');
    const row = Array.from(body?.querySelectorAll('tr[data-order-id]') || [])
        .find(item => item.dataset.orderId === String(orderId));
    return revealWorkflowTarget(row || body);
}

export function batchCancellationConfirmed(results) {
    return results.length > 0 && results.every(result => result.status === 'fulfilled'
        && result.value?.success === true
        && ['canceled', 'cancelled'].includes(result.value.status));
}

export function returnToWorkspace() {
    const target = document.getElementById('options-table-container')
        || document.getElementById('rollover-suggestions-table-body')
        || document.querySelector('.option-positions-table')
        || document.querySelector('main');
    return revealWorkflowTarget(target);
}

export async function returnToOpportunity(order) {
    if (document.getElementById('rollover-suggestions-table-body')) {
        return revealWorkflowTarget(document.getElementById('rollover-suggestions-table-body'));
    }
    const isClose = order?.intent === 'CLOSE';
    const isRollover = order?.isRollover === true || order?.isRollover === 1;
    const hasOpportunities = Boolean(document.getElementById('options-table-container'));
    if (isRollover || (isClose && hasOpportunities) || (!isClose && !hasOpportunities && order?.ticker)) {
        try {
            sessionStorage.setItem('workflow-return', JSON.stringify({
                ticker: order.ticker, option_type: order.option_type,
                con_id: order.con_id, intent: order.intent, isRollover
            }));
        } catch (_) { return false; }
        window.location.assign(isRollover ? '/rollover' : isClose ? '/portfolio' : '/');
        return true;
    }
    if (!hasOpportunities) {
        const button = Array.from(document.querySelectorAll('.close-option-position'))
            .find(item => String(item.dataset.conId) === String(order?.con_id));
        if (button) return revealWorkflowTarget(button.closest('tr'));
        return false;
    }
    const type = String(order?.option_type || '').toLowerCase();
    if (!['call', 'put'].includes(type)) return false;
    const table = document.getElementById(`${type}-options-table`);
    const row = Array.from(table?.querySelectorAll('tbody tr[data-ticker]') || [])
        .find(item => item.dataset.ticker === order.ticker);
    if (!row) return false;
    const tab = document.getElementById(`${type}-options-tab`);
    if (tab && window.bootstrap?.Tab) window.bootstrap.Tab.getOrCreateInstance(tab).show();
    // Bootstrap's tab fade must finish before measuring the destination.
    await new Promise(resolve => setTimeout(resolve, 180));
    return revealWorkflowTarget(row);
}

// Continue a user-triggered return across pages after asynchronous rows render.
if (typeof document !== 'undefined') {
    const restore = () => {
        let order;
        try {
            order = JSON.parse(sessionStorage.getItem('workflow-return') || 'null');
            sessionStorage.removeItem('workflow-return');
        } catch (_) { return; }
        if (!order) return;
        let busy = false;
        const observer = new MutationObserver(attempt);
        const timeout = setTimeout(() => observer.disconnect(), 15000);
        async function attempt() {
            if (busy) return;
            busy = true;
            try {
                if (await returnToOpportunity(order)) {
                    observer.disconnect();
                    clearTimeout(timeout);
                }
            } finally { busy = false; }
        }
        observer.observe(document.body, {childList: true, subtree: true});
        void attempt();
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', restore, {once: true});
    else restore();
}
