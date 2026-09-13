import { showAlert } from '../utils/alerts.js?v=close-position-1';

let closePreview = null;
let closeModal = null;
let quoteRequestId = 0;
let stageInFlight = false;

function tr(key, replacements = {}) {
    return window.t ? window.t(key, replacements) : key;
}

function formatCurrency(value) {
    if (value === null || value === undefined || !Number.isFinite(Number(value))) return '-';
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(Number(value));
}

function formatPrice(value) {
    const price = Number(value);
    return Number.isFinite(price) && price > 0 ? `$${price.toFixed(2)}` : '-';
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || data.message || `HTTP error ${response.status}`);
    }
    return data;
}

function setLoading(isLoading) {
    document.getElementById('close-position-loading')?.classList.toggle('d-none', !isLoading);
    document.getElementById('close-position-content')?.classList.toggle('d-none', isLoading);
    const refreshButton = document.getElementById('close-position-refresh');
    if (refreshButton) refreshButton.disabled = isLoading;
}

function showModalError(message) {
    const error = document.getElementById('close-position-error');
    if (!error) return;
    error.textContent = message;
    error.classList.remove('d-none');
}

function clearModalError() {
    const error = document.getElementById('close-position-error');
    if (!error) return;
    error.textContent = '';
    error.classList.add('d-none');
}

function quotePrice(field) {
    const value = Number(closePreview?.[field]);
    return Number.isFinite(value) && value > 0 ? value : null;
}

function selectedQuantity() {
    const input = document.getElementById('close-position-quantity');
    const value = Number.parseInt(input?.value || '', 10);
    return Number.isInteger(value) ? value : 0;
}

function selectedLimitPrice() {
    const input = document.getElementById('close-position-limit');
    const value = Number.parseFloat(input?.value || '');
    return Number.isFinite(value) ? value : 0;
}

function updateCloseSummary() {
    if (!closePreview) return;

    const held = Math.abs(Number(closePreview.position || 0));
    const quantity = selectedQuantity();
    const limitPrice = selectedLimitPrice();
    const multiplier = Number(closePreview.multiplier || 100);
    const entryPrice = Number(closePreview.avg_cost_per_share || 0);
    const remaining = Math.max(0, held - quantity);
    const isValid = quantity >= 1 && quantity <= held && limitPrice > 0;

    const remainingElement = document.getElementById('close-position-remaining');
    if (remainingElement) {
        remainingElement.textContent = tr('close.remaining', { count: remaining });
    }

    const total = isValid ? limitPrice * multiplier * quantity : null;
    const pnlPerShare = closePreview.close_action === 'BUY'
        ? entryPrice - limitPrice
        : limitPrice - entryPrice;
    const estimatedPnl = isValid && entryPrice > 0
        ? pnlPerShare * multiplier * quantity
        : null;
    const estimatedReturn = estimatedPnl !== null && entryPrice > 0
        ? (estimatedPnl / (entryPrice * multiplier * quantity)) * 100
        : null;

    const totalElement = document.getElementById('close-position-total');
    const pnlElement = document.getElementById('close-position-pnl');
    const returnElement = document.getElementById('close-position-return');
    if (totalElement) totalElement.textContent = total === null ? '-' : formatCurrency(total);
    if (pnlElement) {
        pnlElement.textContent = estimatedPnl === null ? '-' : formatCurrency(estimatedPnl);
        pnlElement.className = estimatedPnl === null
            ? ''
            : (estimatedPnl >= 0 ? 'text-success' : 'text-danger');
    }
    if (returnElement) {
        returnElement.textContent = estimatedReturn === null ? '-' : `${estimatedReturn.toFixed(1)}%`;
        returnElement.className = estimatedReturn === null
            ? ''
            : (estimatedReturn >= 0 ? 'text-success' : 'text-danger');
    }

    const stageButton = document.getElementById('close-position-stage');
    if (stageButton) stageButton.disabled = !isValid || stageInFlight;
}

function setLimitPrice(price, quoteField = null) {
    const input = document.getElementById('close-position-limit');
    if (!input || !Number.isFinite(Number(price)) || Number(price) <= 0) return;
    input.value = Number(price).toFixed(2);
    document.querySelectorAll('.close-quote-choice').forEach(button => {
        button.classList.toggle('active', button.dataset.quoteField === quoteField);
    });
    updateCloseSummary();
}

function renderQuote() {
    if (!closePreview) return;

    const position = Number(closePreview.position || 0);
    const held = Math.abs(position);
    const actionLabel = closePreview.close_action === 'BUY'
        ? tr('close.buyToClose')
        : tr('close.sellToClose');

    document.getElementById('close-position-symbol').textContent = closePreview.symbol || '-';
    document.getElementById('close-position-type').textContent = closePreview.option_type || '-';
    document.getElementById('close-position-action').textContent = actionLabel;
    document.getElementById('close-position-contract').textContent = tr('close.contractSummary', {
        strike: formatCurrency(closePreview.strike),
        expiration: closePreview.expiration || '-',
        count: held
    });
    document.getElementById('close-position-account').textContent = `•••• ${closePreview.account_suffix || '----'}`;
    document.getElementById('close-position-bid').textContent = formatPrice(closePreview.bid);
    document.getElementById('close-position-mid').textContent = formatPrice(closePreview.mid);
    document.getElementById('close-position-ask').textContent = formatPrice(closePreview.ask);

    document.querySelectorAll('.close-quote-choice').forEach(button => {
        const available = quotePrice(button.dataset.quoteField) !== null;
        button.disabled = !available;
        if (!available) button.classList.remove('active');
    });
    const joinMidButton = document.getElementById('close-position-join-mid');
    if (joinMidButton) joinMidButton.disabled = quotePrice('mid') === null;

    const status = document.getElementById('close-position-data-status');
    if (status) {
        status.textContent = closePreview.is_frozen
            ? tr('dashboard.frozenData')
            : tr('dashboard.realTimeData');
        status.className = `badge ${closePreview.is_frozen ? 'text-bg-warning' : 'text-bg-success'}`;
    }

    const quoteTime = document.getElementById('close-position-quote-time');
    if (quoteTime) {
        const date = closePreview.quote_time ? new Date(closePreview.quote_time) : null;
        quoteTime.textContent = date && !Number.isNaN(date.getTime())
            ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
            : '-';
    }

    const rawSpread = closePreview.spread_percent;
    const spread = Number(rawSpread);
    const spreadElement = document.getElementById('close-position-spread');
    if (spreadElement) {
        if (rawSpread !== null && rawSpread !== undefined && Number.isFinite(spread)) {
            spreadElement.textContent = tr('close.spread', { value: `${spread.toFixed(1)}%` });
            spreadElement.className = `small mb-4 ${spread <= 10 ? 'spread-tight' : spread <= 20 ? 'spread-medium' : 'spread-wide'}`;
        } else {
            spreadElement.textContent = tr('close.spreadUnavailable');
            spreadElement.className = 'small mb-4 spread-unavailable';
        }
    }

    const quantityInput = document.getElementById('close-position-quantity');
    if (quantityInput) {
        quantityInput.max = String(held);
        quantityInput.value = '1';
    }

    const runnerButton = document.querySelector('[data-close-quantity="runner"]');
    if (runnerButton) runnerButton.disabled = held <= 1;

    const defaultPrice = quotePrice('mid');
    const limitInput = document.getElementById('close-position-limit');
    if (defaultPrice) {
        setLimitPrice(defaultPrice, 'mid');
    } else if (limitInput) {
        limitInput.value = '';
        updateCloseSummary();
    }
}

async function loadClosePreview(conId, { preserveInputs = false } = {}) {
    const requestId = ++quoteRequestId;
    const previousQuantity = preserveInputs ? selectedQuantity() : null;
    const previousPrice = preserveInputs ? selectedLimitPrice() : null;
    clearModalError();
    setLoading(true);

    try {
        const preview = await requestJson(`/api/portfolio/option-position/${encodeURIComponent(conId)}/quote?t=${Date.now()}`);
        if (requestId !== quoteRequestId) return;
        closePreview = preview;
        renderQuote();

        if (preserveInputs) {
            const maxQuantity = Math.abs(Number(closePreview.position || 0));
            if (previousQuantity >= 1 && previousQuantity <= maxQuantity) {
                document.getElementById('close-position-quantity').value = String(previousQuantity);
            }
            if (previousPrice > 0) setLimitPrice(previousPrice);
            updateCloseSummary();
        }
    } catch (error) {
        if (requestId !== quoteRequestId) return;
        closePreview = null;
        showModalError(error.message);
    } finally {
        if (requestId === quoteRequestId) {
            setLoading(false);
            if (!closePreview) {
                document.getElementById('close-position-content')?.classList.add('d-none');
            }
        }
    }
}

async function openCloseModal(conId) {
    if (!conId) return;
    closePreview = null;
    clearModalError();
    closeModal.show();
    await loadClosePreview(conId);
}

async function stageCloseOrder() {
    if (!closePreview || stageInFlight) return;

    const quantity = selectedQuantity();
    const limitPrice = selectedLimitPrice();
    stageInFlight = true;
    updateCloseSummary();

    try {
        const result = await requestJson('/api/options/close-order', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-All-You-Need-Is-Wheel': '1'
            },
            body: JSON.stringify({
                con_id: closePreview.con_id,
                quantity,
                limit_price: limitPrice
            })
        });

        closeModal.hide();
        showAlert(tr('close.staged', { id: result.order_id }), 'success');
        document.dispatchEvent(new CustomEvent('ordersUpdated'));
    } catch (error) {
        showModalError(error.message);
    } finally {
        stageInFlight = false;
        updateCloseSummary();
    }
}

function initializeClosePosition() {
    const modalElement = document.getElementById('close-position-modal');
    if (!modalElement || !window.bootstrap?.Modal) return;
    closeModal = bootstrap.Modal.getOrCreateInstance(modalElement);

    document.addEventListener('click', event => {
        const closeButton = event.target.closest('.close-option-position');
        if (closeButton && !closeButton.disabled) {
            openCloseModal(Number(closeButton.dataset.conId));
            return;
        }

        const quoteChoice = event.target.closest('.close-quote-choice');
        if (quoteChoice) {
            const field = quoteChoice.dataset.quoteField;
            const price = quotePrice(field);
            if (price) setLimitPrice(price, field);
            return;
        }

        const quantityButton = event.target.closest('[data-close-quantity]');
        if (quantityButton && closePreview) {
            const held = Math.abs(Number(closePreview.position || 0));
            const mode = quantityButton.dataset.closeQuantity;
            let quantity = 1;
            if (mode === 'half') quantity = Math.max(1, Math.floor(held / 2));
            if (mode === 'runner') quantity = Math.max(1, held - 1);
            if (mode === 'all') quantity = held;
            document.getElementById('close-position-quantity').value = String(quantity);
            updateCloseSummary();
        }
    });

    document.getElementById('close-position-quantity')?.addEventListener('input', updateCloseSummary);
    document.getElementById('close-position-limit')?.addEventListener('input', () => {
        document.querySelectorAll('.close-quote-choice').forEach(button => button.classList.remove('active'));
        updateCloseSummary();
    });
    document.getElementById('close-position-join-mid')?.addEventListener('click', () => {
        const mid = quotePrice('mid');
        if (mid) setLimitPrice(mid, 'mid');
    });
    document.getElementById('close-position-refresh')?.addEventListener('click', () => {
        if (closePreview?.con_id) loadClosePreview(closePreview.con_id, { preserveInputs: true });
    });
    document.getElementById('close-position-stage')?.addEventListener('click', stageCloseOrder);
    document.addEventListener('languageChanged', () => {
        if (!closePreview) return;
        const quantity = selectedQuantity();
        const limitPrice = selectedLimitPrice();
        renderQuote();
        document.getElementById('close-position-quantity').value = String(quantity);
        if (limitPrice > 0) setLimitPrice(limitPrice);
        updateCloseSummary();
    });
}

export { initializeClosePosition };
