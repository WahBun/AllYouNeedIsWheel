/**
 * Account module for handling portfolio data
 * Manages account summary and positions display
 */
import {
    fetchAccountData,
    fetchPositions,
    fetchPortfolioBootstrap,
    fetchLivePositions
} from './api.js?v=portfolio-live-1';
import { showAlert } from '../utils/alerts.js?v=safety-1';
import {
    getPositionKey,
    haveSamePositionSet,
    getPriceDirection
} from '../utils/live-positions.js?v=portfolio-live-1';

// Store account data
let accountData = null;
let positionsData = null;
let liveRefreshTimer = null;
let liveRefreshPromise = null;
const LIVE_REFRESH_INTERVAL_MS = 2000;

function tr(key, replacements = {}) {
    return window.t ? window.t(key, replacements) : key;
}

/**
 * Format currency value for display
 * @param {number} value - The currency value to format
 * @returns {string} Formatted currency string
 */
function formatCurrency(value) {
    if (value === null || value === undefined) return '$0.00';
    return new Intl.NumberFormat('en-US', { 
        style: 'currency', 
        currency: 'USD' 
    }).format(value);
}

/**
 * Format percentage for display
 * @param {number} value - The percentage value
 * @returns {string} Formatted percentage string
 */
function formatPercentage(value) {
    if (value === null || value === undefined) return '0.00%';
    return `${value.toFixed(2)}%`;
}

function hasNumericValue(value) {
    return value !== null && value !== undefined && Number.isFinite(Number(value));
}

function formatOptionalCurrency(value) {
    return hasNumericValue(value) ? formatCurrency(Number(value)) : 'N/A';
}

/**
 * Update account summary display
 */
function updateAccountSummary() {
    if (!accountData) return;
    
    // Update the data status indicator
    updateDataStatusIndicator(accountData.is_frozen);
    
    // Update account value
    const accountValueElement = document.getElementById('account-value');
    if (accountValueElement) {
        accountValueElement.textContent = formatCurrency(accountData.account_value || 0);
    }
    
    // Update cash balance
    const cashBalanceElement = document.getElementById('cash-balance');
    if (cashBalanceElement) {
        cashBalanceElement.textContent = formatCurrency(accountData.cash_balance || 0);
    }
    
    // Update positions count
    const positionsCountElement = document.getElementById('positions-count');
    if (positionsCountElement) {
        positionsCountElement.textContent = accountData.positions_count || 0;
    }
    
    // Update new margin metrics
    
    // Excess Liquidity
    const excessLiquidityElement = document.getElementById('excess-liquidity');
    if (excessLiquidityElement) {
        excessLiquidityElement.textContent = formatCurrency(accountData.excess_liquidity || 0);
    }
    
    // Initial Margin
    const initialMarginElement = document.getElementById('initial-margin');
    if (initialMarginElement) {
        initialMarginElement.textContent = formatCurrency(accountData.initial_margin || 0);
    }
    
    // Leverage Percentage
    const leveragePercentageElement = document.getElementById('leverage-percentage');
    if (leveragePercentageElement) {
        leveragePercentageElement.textContent = formatPercentage(accountData.leverage_percentage || 0);
    }
    
    // Update the leverage progress bar
    const leverageBar = document.getElementById('leverage-bar');
    if (leverageBar) {
        const leveragePercentage = accountData.leverage_percentage || 0;
        
        // Set the width of the progress bar
        leverageBar.style.width = `${Math.min(100, leveragePercentage)}%`;
        leverageBar.setAttribute('aria-valuenow', Math.min(100, leveragePercentage));
        
        // Update the color based on leverage level
        if (leveragePercentage < 30) {
            leverageBar.className = 'progress-bar bg-success'; // Low leverage - green
        } else if (leveragePercentage < 60) {
            leverageBar.className = 'progress-bar bg-warning'; // Medium leverage - yellow
        } else {
            leverageBar.className = 'progress-bar bg-danger';  // High leverage - red
        }
    }
}

/**
 * Populate positions tables
 */
function populatePositionsTable() {
    if (!positionsData) return;
    
    // Debug log to see what data we're working with
    console.log('Position data received:', positionsData);
    
    // Filter positions by security_type
    const stockPositions = positionsData.filter(position => 
        position.security_type === 'STK' || position.securityType === 'STK' || position.sec_type === 'STK');
    
    const optionPositions = positionsData.filter(position => 
        position.security_type === 'OPT' || position.securityType === 'OPT' || position.sec_type === 'OPT');
    
    console.log('Stock positions identified:', stockPositions.length);
    console.log('Option positions identified:', optionPositions.length);
    
    // Populate stock positions table
    populateStockPositionsTable(stockPositions);
    
    // Populate option positions table
    populateOptionPositionsTable(optionPositions);
}

/**
 * Populate stock positions table
 * @param {Array} stockPositions - Array of stock positions
 */
function populateStockPositionsTable(stockPositions) {
    const stockTableBody = document.getElementById('stock-positions-table-body');
    if (!stockTableBody) return;
    
    // Clear table
    stockTableBody.innerHTML = '';
    
    if (stockPositions.length === 0) {
        const noDataRow = document.createElement('tr');
        noDataRow.innerHTML = `<td colspan="6" class="text-center">${tr('portfolio.noStockPositions')}</td>`;
        stockTableBody.appendChild(noDataRow);
        return;
    }
    
    // Sort positions by market value (descending)
    stockPositions.sort((a, b) => {
        const marketValueA = a.market_value || 0;
        const marketValueB = b.market_value || 0;
        return marketValueB - marketValueA;
    });
    
    // Add stock positions
    stockPositions.forEach(position => {
        const row = document.createElement('tr');
        row.dataset.positionKey = getPositionKey(position);
        
        const avgCost = position.avg_cost || position.average_cost || 0;
        const marketValue = position.market_value;
        const unrealizedPnL = position.unrealized_pnl;
        const hasPnL = hasNumericValue(unrealizedPnL);
        
        // Calculate the P&L percentage based on the position's cost basis
        let unrealizedPnLPercent = 0;
        const totalCostBasis = Math.abs(position.position) * avgCost;
        if (hasPnL && totalCostBasis > 0) {
            unrealizedPnLPercent = (unrealizedPnL / totalCostBasis) * 100;
        }
        
        const pnlClass = !hasPnL
            ? 'text-muted'
            : (unrealizedPnL >= 0 ? 'text-success' : 'text-danger');
        const pnlText = hasPnL
            ? `${formatCurrency(unrealizedPnL)} (${formatPercentage(unrealizedPnLPercent)})`
            : 'N/A';
        
        row.innerHTML = `
            <td>${position.symbol}</td>
            <td class="position-quantity">${position.position}</td>
            <td class="position-avg-cost">${formatCurrency(avgCost)}</td>
            <td class="position-current-price" data-market-price="${hasNumericValue(position.market_price) ? Number(position.market_price) : ''}">${formatOptionalCurrency(position.market_price)}</td>
            <td class="position-market-value">${formatOptionalCurrency(marketValue)}</td>
            <td class="position-pnl ${pnlClass}">${pnlText}</td>
        `;
        
        stockTableBody.appendChild(row);
    });
}

/**
 * Populate option positions table
 * @param {Array} optionPositions - Array of option positions
 */
function populateOptionPositionsTable(optionPositions) {
    const optionTableBody = document.getElementById('option-positions-table-body');
    if (!optionTableBody) return;
    
    // Clear table
    optionTableBody.innerHTML = '';
    
    if (optionPositions.length === 0) {
        const noDataRow = document.createElement('tr');
        noDataRow.innerHTML = `<td colspan="10" class="text-center">${tr('portfolio.noOptionPositions')}</td>`;
        optionTableBody.appendChild(noDataRow);
        return;
    }
    
    // Group options by type (CALL/PUT)
    const callOptions = optionPositions.filter(position => {
        if (position.contract && position.contract.right) {
            return position.contract.right === 'C';
        } else {
            const optType = position.option_type || '';
            return optType === 'CALL' || optType === 'C' || optType === 'Call';
        }
    });
    
    const putOptions = optionPositions.filter(position => {
        if (position.contract && position.contract.right) {
            return position.contract.right === 'P';
        } else {
            const optType = position.option_type || '';
            return optType === 'PUT' || optType === 'P' || optType === 'Put';
        }
    });
    
    // Sort each group by market value (descending)
    const sortOptions = (a, b) => {
        const marketValueA = a.market_value || 0;
        const marketValueB = b.market_value || 0;
        return marketValueB - marketValueA;
    };
    
    callOptions.sort(sortOptions);
    putOptions.sort(sortOptions);
    
    // Add CALL options with header if there are any
    if (callOptions.length > 0) {
        const callHeader = document.createElement('tr');
        callHeader.className = 'table-primary';
        callHeader.innerHTML = `<td colspan="10" class="fw-bold">CALL OPTIONS (${callOptions.length})</td>`;
        optionTableBody.appendChild(callHeader);
        
        addOptionsToTable(callOptions, optionTableBody);
    }
    
    // Add PUT options with header if there are any
    if (putOptions.length > 0) {
        const putHeader = document.createElement('tr');
        putHeader.className = 'table-warning';
        putHeader.innerHTML = `<td colspan="10" class="fw-bold">PUT OPTIONS (${putOptions.length})</td>`;
        optionTableBody.appendChild(putHeader);
        
        addOptionsToTable(putOptions, optionTableBody);
    }
}

/**
 * Add options to the table
 * @param {Array} options - Array of option positions
 * @param {HTMLElement} tableBody - Table body element
 */
function addOptionsToTable(options, tableBody) {
    options.forEach(position => {
        const row = document.createElement('tr');
        row.dataset.positionKey = getPositionKey(position);
        
        const avgCost = position.avg_cost || position.average_cost || 0;
        const rawMarketValue = position.market_value;
        // For short options (negative position), show market value as positive
        const marketValue = hasNumericValue(rawMarketValue)
            ? (position.position < 0 ? Math.abs(rawMarketValue) : rawMarketValue)
            : null;
        const unrealizedPnL = position.unrealized_pnl;
        const hasPnL = hasNumericValue(unrealizedPnL);
        
        // Calculate the P&L percentage based on the position's cost basis
        let unrealizedPnLPercent = 0;
        const totalCostBasis = Math.abs(position.position) * avgCost;
        if (hasPnL && totalCostBasis > 0) {
            unrealizedPnLPercent = (unrealizedPnL / totalCostBasis) * 100;
        }
        
        // Extract option details
        let optionType = '-';
        let strike = '-';
        let expiry = '-';
        
        // Get option details from either contract object or direct properties
        if (position.contract && position.contract.right) {
            optionType = position.contract.right === 'P' ? 'PUT' : 'CALL';
            strike = position.contract.strike ? formatCurrency(position.contract.strike) : '-';
            expiry = position.contract.lastTradeDateOrContractMonth || '-';
        } else {
            // Try to get from direct properties
            optionType = position.option_type || '-';
            strike = position.strike ? formatCurrency(position.strike) : '-';
            expiry = position.expiration || '-';
        }
        
        // IB portfolio marketPrice is per share; averageCost is per contract.
        const perSharePrice = position.market_price;
        const multiplier = Number(position.multiplier || 100);
        const perContractPrice = hasNumericValue(perSharePrice)
            ? Number(perSharePrice) * multiplier
            : null;
        const conId = Number(position.con_id || 0);
        const closeDisabled = conId <= 0 || Number(position.position || 0) === 0;
        
        const pnlClass = !hasPnL
            ? 'text-muted'
            : (unrealizedPnL >= 0 ? 'text-success' : 'text-danger');
        const pnlText = hasPnL
            ? `${formatCurrency(unrealizedPnL)} (${formatPercentage(unrealizedPnLPercent)})`
            : 'N/A';
        
        row.innerHTML = `
            <td>${position.symbol}</td>
            <td class="position-quantity">${position.position}</td>
            <td>${optionType}</td>
            <td>${strike}</td>
            <td>${expiry}</td>
            <td class="position-avg-cost">${formatCurrency(avgCost)}</td>
            <td class="position-current-price" data-market-price="${hasNumericValue(perSharePrice) ? Number(perSharePrice) : ''}">${formatOptionalCurrency(perContractPrice)}</td>
            <td class="position-market-value">${formatOptionalCurrency(marketValue)}</td>
            <td class="position-pnl ${pnlClass}">${pnlText}</td>
            <td>
                <button type="button" class="btn btn-sm btn-outline-primary close-option-position"
                    data-con-id="${conId}"
                    ${closeDisabled ? 'disabled' : ''}
                    title="${closeDisabled ? tr('close.unavailable') : tr('close.button')}">
                    <i class="bi bi-box-arrow-in-left"></i>
                    <span>${tr('close.button')}</span>
                </button>
            </td>
        `;
        
        tableBody.appendChild(row);
    });
}

function getPnlPresentation(position) {
    const unrealizedPnL = position.unrealized_pnl;
    const hasPnL = hasNumericValue(unrealizedPnL);
    const avgCost = Number(position.avg_cost || position.average_cost || 0);
    const totalCostBasis = Math.abs(Number(position.position || 0)) * avgCost;
    const percentage = hasPnL && totalCostBasis > 0
        ? (Number(unrealizedPnL) / totalCostBasis) * 100
        : 0;

    return {
        className: !hasPnL ? 'text-muted' : (Number(unrealizedPnL) >= 0 ? 'text-success' : 'text-danger'),
        text: hasPnL
            ? `${formatCurrency(Number(unrealizedPnL))} (${formatPercentage(percentage)})`
            : 'N/A'
    };
}

function updatePriceCell(cell, position) {
    if (!cell) return;

    const nextPrice = hasNumericValue(position.market_price)
        ? Number(position.market_price)
        : null;
    const previousPrice = hasNumericValue(cell.dataset.marketPrice)
        ? Number(cell.dataset.marketPrice)
        : null;
    const multiplier = position.security_type === 'OPT'
        ? Number(position.multiplier || 100)
        : 1;

    cell.textContent = nextPrice === null
        ? 'N/A'
        : formatCurrency(nextPrice * multiplier);
    cell.dataset.marketPrice = nextPrice === null ? '' : String(nextPrice);

    const direction = getPriceDirection(previousPrice, nextPrice);
    if (!direction) return;

    cell.classList.remove('price-tick-up', 'price-tick-down');
    void cell.offsetWidth;
    cell.classList.add(direction === 'up' ? 'price-tick-up' : 'price-tick-down');
    window.setTimeout(() => {
        cell.classList.remove('price-tick-up', 'price-tick-down');
    }, 650);
}

function updatePositionRow(row, position) {
    const quantityCell = row.querySelector('.position-quantity');
    const avgCostCell = row.querySelector('.position-avg-cost');
    const marketValueCell = row.querySelector('.position-market-value');
    const pnlCell = row.querySelector('.position-pnl');

    if (quantityCell) quantityCell.textContent = position.position;
    if (avgCostCell) avgCostCell.textContent = formatCurrency(Number(position.avg_cost || 0));
    updatePriceCell(row.querySelector('.position-current-price'), position);

    const rawMarketValue = position.market_value;
    const displayMarketValue = (
        position.security_type === 'OPT'
        && Number(position.position || 0) < 0
        && hasNumericValue(rawMarketValue)
    ) ? Math.abs(Number(rawMarketValue)) : rawMarketValue;
    if (marketValueCell) marketValueCell.textContent = formatOptionalCurrency(displayMarketValue);

    if (pnlCell) {
        const pnl = getPnlPresentation(position);
        pnlCell.classList.remove('text-muted', 'text-success', 'text-danger');
        pnlCell.classList.add(pnl.className);
        pnlCell.textContent = pnl.text;
    }
}

function updateLivePositionStatus({ isFrozen = false, error = false, paused = false, asOf = null } = {}) {
    const badge = document.getElementById('position-stream-badge');
    const timestamp = document.getElementById('position-stream-time');
    if (!badge || !timestamp) return;

    badge.className = 'badge position-stream-badge';
    if (error) {
        badge.classList.add('text-bg-danger');
        badge.textContent = tr('portfolio.reconnecting');
    } else if (paused) {
        badge.classList.add('text-bg-secondary');
        badge.textContent = tr('portfolio.paused');
    } else if (isFrozen) {
        badge.classList.add('text-bg-warning');
        badge.textContent = tr('portfolio.frozenStream');
    } else {
        badge.classList.add('text-bg-success');
        badge.textContent = tr('portfolio.liveStream');
    }

    const date = asOf ? new Date(asOf) : new Date();
    timestamp.textContent = Number.isNaN(date.getTime())
        ? ''
        : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function applyLivePositions(payload) {
    if (!payload || !Array.isArray(payload.positions)) return false;

    const incomingPositions = payload.positions;
    if (!Array.isArray(positionsData) || !haveSamePositionSet(positionsData, incomingPositions)) {
        positionsData = incomingPositions;
        populatePositionsTable();
    } else {
        positionsData = incomingPositions;
        const rows = new Map(
            [...document.querySelectorAll('[data-position-key]')]
                .map(row => [row.dataset.positionKey, row])
        );
        for (const position of incomingPositions) {
            const row = rows.get(getPositionKey(position));
            if (!row) {
                populatePositionsTable();
                break;
            }
            updatePositionRow(row, position);
        }
    }

    updateLivePositionStatus({ isFrozen: payload.is_frozen, asOf: payload.as_of });
    return true;
}

async function refreshLivePositions() {
    if (liveRefreshPromise) return liveRefreshPromise;

    liveRefreshPromise = (async () => {
        try {
            const payload = await fetchLivePositions();
            return applyLivePositions(payload) ? payload : null;
        } catch (error) {
            console.error('Error refreshing live positions:', error);
            updateLivePositionStatus({ error: true });
            return null;
        } finally {
            liveRefreshPromise = null;
        }
    })();
    return liveRefreshPromise;
}

function scheduleLivePositionRefresh() {
    if (liveRefreshTimer || document.hidden) return;
    liveRefreshTimer = window.setTimeout(async () => {
        liveRefreshTimer = null;
        await refreshLivePositions();
        scheduleLivePositionRefresh();
    }, LIVE_REFRESH_INTERVAL_MS);
}

function startLivePositionUpdates() {
    if (!document.getElementById('stock-positions-table-body')) return;
    if (document.hidden) {
        updateLivePositionStatus({ paused: true });
        return;
    }
    void refreshLivePositions().finally(scheduleLivePositionRefresh);
}

function stopLivePositionUpdates() {
    if (liveRefreshTimer) {
        window.clearTimeout(liveRefreshTimer);
        liveRefreshTimer = null;
    }
}

/**
 * Load portfolio data from API
 */
async function loadPortfolioData() {
    try {
        const bootstrap = await fetchPortfolioBootstrap();
        accountData = bootstrap.summary;
        positionsData = bootstrap.positions;
        updateAccountSummary();
        populatePositionsTable();
        return { accountData, positionsData };
    } catch (error) {
        console.warn('Portfolio bootstrap failed; using compatibility endpoints:', error);
        accountData = await fetchAccountData();
        const fallbackPositions = await loadPositionsTable();
        if (accountData) updateAccountSummary();
        if (accountData || fallbackPositions) return { accountData, positionsData };
        showAlert('Error loading portfolio data. Please check your connection to Interactive Brokers.', 'danger');
        return { accountData: null, positionsData: null };
    }
}

/**
 * Load positions data from API
 */
async function loadPositionsTable() {
    const data = await fetchPositions();
    if (!data) return null;

    positionsData = data;
    if (!accountData && document.getElementById('positions-count')) {
        document.getElementById('positions-count').textContent = positionsData.length || 0;
    }
    populatePositionsTable();
    return positionsData;
}

/**
 * Update the data status indicator
 * @param {boolean} isFrozen - Whether the data is frozen (true) or real-time (false)
 */
function updateDataStatusIndicator(isFrozen) {
    const dataStatusIndicator = document.getElementById('data-status-indicator');
    const dataStatusIcon = document.getElementById('data-status-icon')?.querySelector('i');
    const dataUpdateTime = document.getElementById('data-update-time');
    
    if (!dataStatusIndicator || !dataStatusIcon || !dataUpdateTime) return;
    
    // Get current time for the update timestamp
    const now = new Date();
    const timeString = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    dataUpdateTime.textContent = tr('dashboard.updated', { time: timeString });
    
    if (isFrozen) {
        // Frozen data state
        dataStatusIndicator.className = 'badge bg-warning text-dark';
        dataStatusIndicator.textContent = tr('dashboard.frozenData');
        dataStatusIndicator.setAttribute('title', tr('dashboard.frozenTooltip'));
        
        // Change icon to snowflake
        dataStatusIcon.className = 'bi bi-snow';
    } else {
        // Real-time data state
        dataStatusIndicator.className = 'badge bg-success';
        dataStatusIndicator.textContent = tr('dashboard.realTimeData');
        dataStatusIndicator.setAttribute('title', tr('dashboard.realTimeTooltip'));
        
        // Change icon to lightning
        dataStatusIcon.className = 'bi bi-lightning-fill';
    }
}

document.addEventListener('languageChanged', () => {
    updateAccountSummary();
    populatePositionsTable();
});
document.addEventListener('visibilitychange', () => {
    if (!document.getElementById('stock-positions-table-body')) return;
    if (document.hidden) {
        stopLivePositionUpdates();
        updateLivePositionStatus({ paused: true });
    } else {
        startLivePositionUpdates();
    }
});
window.addEventListener('focus', startLivePositionUpdates);
window.addEventListener('beforeunload', stopLivePositionUpdates);

// Export functions
export {
    formatCurrency,
    formatPercentage,
    updateAccountSummary,
    populatePositionsTable,
    loadPortfolioData,
    loadPositionsTable,
    refreshLivePositions,
    startLivePositionUpdates,
    stopLivePositionUpdates,
    updateDataStatusIndicator
};
