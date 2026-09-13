/**
 * Account module for handling portfolio data
 * Manages account summary and positions display
 */
import { fetchAccountData, fetchPositions } from './api.js?v=safety-1';
import { showAlert } from '../utils/alerts.js?v=safety-1';

// Store account data
let accountData = null;
let positionsData = null;

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
        
        const avgCost = position.avg_cost || position.average_cost || 0;
        const marketValue = position.market_value || 0;
        const unrealizedPnL = position.unrealized_pnl || 0;
        
        // Calculate the P&L percentage based on the position's cost basis
        let unrealizedPnLPercent = 0;
        const totalCostBasis = Math.abs(position.position) * avgCost;
        if (totalCostBasis > 0) {
            unrealizedPnLPercent = (unrealizedPnL / totalCostBasis) * 100;
        }
        
        const pnlClass = unrealizedPnL >= 0 ? 'text-success' : 'text-danger';
        
        row.innerHTML = `
            <td>${position.symbol}</td>
            <td>${position.position}</td>
            <td>${formatCurrency(avgCost)}</td>
            <td>${formatCurrency(position.market_price || 0)}</td>
            <td>${formatCurrency(marketValue)}</td>
            <td class="${pnlClass}">${formatCurrency(unrealizedPnL)} (${formatPercentage(unrealizedPnLPercent)})</td>
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
        
        const avgCost = position.avg_cost || position.average_cost || 0;
        const rawMarketValue = position.market_value || 0;
        // For short options (negative position), show market value as positive
        const marketValue = position.position < 0 ? Math.abs(rawMarketValue) : rawMarketValue;
        const unrealizedPnL = position.unrealized_pnl || 0;
        
        // Calculate the P&L percentage based on the position's cost basis
        let unrealizedPnLPercent = 0;
        const totalCostBasis = Math.abs(position.position) * avgCost;
        if (totalCostBasis > 0) {
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
        const perSharePrice = position.market_price || 0;
        const multiplier = Number(position.multiplier || 100);
        const perContractPrice = perSharePrice * multiplier;
        const conId = Number(position.con_id || 0);
        const closeDisabled = conId <= 0 || Number(position.position || 0) === 0;
        
        const pnlClass = unrealizedPnL >= 0 ? 'text-success' : 'text-danger';
        
        row.innerHTML = `
            <td>${position.symbol}</td>
            <td>${position.position}</td>
            <td>${optionType}</td>
            <td>${strike}</td>
            <td>${expiry}</td>
            <td>${formatCurrency(avgCost)}</td>
            <td>${formatCurrency(perContractPrice)}</td>
            <td>${formatCurrency(marketValue)}</td>
            <td class="${pnlClass}">${formatCurrency(unrealizedPnL)} (${formatPercentage(unrealizedPnLPercent)})</td>
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

/**
 * Load portfolio data from API
 */
async function loadPortfolioData() {
    try {
        // Fetch account data
        accountData = await fetchAccountData();
        if (accountData) {
            updateAccountSummary();
            await loadPositionsTable();
        }
    } catch (error) {
        console.error('Error loading portfolio data:', error);
        showAlert('Error loading portfolio data. Please check your connection to Interactive Brokers.', 'danger');
    }
}

/**
 * Load positions data from API
 */
async function loadPositionsTable() {
    const data = await fetchPositions();
    if (data) {
        positionsData = data;
        if (!accountData && document.getElementById('positions-count')) {
            document.getElementById('positions-count').textContent = positionsData.length || 0;
        }
        populatePositionsTable();
    }
}

/**
 * Update the data status indicator
 * @param {boolean} isFrozen - Whether the data is frozen (true) or real-time (false)
 */
function updateDataStatusIndicator(isFrozen) {
    const dataStatusIndicator = document.getElementById('data-status-indicator');
    const dataStatusIcon = document.getElementById('data-status-icon').querySelector('i');
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

// Export functions
export {
    formatCurrency,
    formatPercentage,
    updateAccountSummary,
    populatePositionsTable,
    loadPortfolioData,
    loadPositionsTable,
    updateDataStatusIndicator
}; 
