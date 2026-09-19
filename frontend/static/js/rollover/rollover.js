/**
 * Rollover module
 * Handles options approaching strike price and rollover suggestions
 */
import { fetchPositions, fetchOptionData, fetchPendingOrders, cancelOrder, executeOrder, checkOrderStatus, fetchStockPrices as apiFetchStockPrices, fetchOptionExpirations } from '../dashboard/api.js?v=safety-1';
import { formatCurrency } from '../utils/formatters.js';
import { showAlert } from '../utils/alerts.js?v=scroll-stable-1';
import { calculateMidPrice, positivePrice } from '../utils/option-pricing.js?v=pricing-safety-1';
import { revealPendingOrder, returnToOpportunity, revealWorkflowTarget } from '../utils/workflow-navigation.js?v=4';

// Store data
let optionsData = null;
let selectedOption = null;
let rolloverSuggestions = [];
let pendingOrders = [];
let orderStatusTimer = null;
const orderExecutionInFlight = new Set();
const TRACKED_ORDER_STATUSES = ['submitting', 'processing', 'canceling', 'unknown'];
const ACTIVE_ORDER_STATUSES = ['pending', ...TRACKED_ORDER_STATUSES];
const ORDER_STATUS_INTERVAL = 10000;

function tr(key, replacements = {}) {
    return window.t ? window.t(key, replacements) : key;
}

function formatQuotePrice(value) {
    return value === null ? 'N/A' : formatCurrency(value);
}

async function fetchHeldOptionQuote(conId) {
    const response = await fetch(
        `/api/portfolio/option-position/${encodeURIComponent(conId)}/quote?t=${Date.now()}`
    );
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || `Unable to refresh held option quote (${response.status})`);
    }
    return data;
}

/**
 * Format percentage for display
 * @param {number} value - The percentage value
 * @returns {string} Formatted percentage string with color classes
 */
function formatPercentage(value, includeColorClass = true) {
    if (value === null || value === undefined) return '0.00%';
    const percentStr = `${Math.abs(value).toFixed(2)}%`;
    
    if (!includeColorClass) return percentStr;
    
    // Add color class based on proximity to strike
    if (value < 5) {
        return `<span class="text-danger fw-bold">${percentStr}</span>`;
    } else if (value < 10) {
        return `<span class="text-danger">${percentStr}</span>`;
    } else {
        return `<span>${percentStr}</span>`;
    }
}

/**
 * Initialize the rollover page
 */
async function initializeRollover() {
    try {
        // Load option positions
        await loadOptionPositions();
        
        // Load pending orders
        await loadPendingOrders();
        
        // Add event listener to option rows
        const optionsTable = document.getElementById('options-approaching-table');
        if (optionsTable) {
            optionsTable.addEventListener('click', async (event) => {
                // Find closest roll button
                const rollButton = event.target.closest('.roll-btn');
                if (rollButton) {
                    const optionId = parseInt(rollButton.getAttribute('data-option-id'));
                    if (!isNaN(optionId)) {
                        await selectOptionToRoll(optionId);
                    }
                }
            });
        }
        
        // Set up refresh button with event listener to preserve state
        const refreshBtn = document.getElementById('refresh-rollover');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', async () => {
                try {
                    // Save current state (create deep copies to avoid reference issues)
                    const currentSelectedOption = selectedOption ? JSON.parse(JSON.stringify(selectedOption)) : null;
                    const currentSuggestions = rolloverSuggestions ? JSON.parse(JSON.stringify(rolloverSuggestions)) : [];
                    
                    // Refresh data
                    await Promise.all([
                        loadOptionPositions(), 
                        loadPendingOrders()
                    ]);
                    
                    // Restore state if there was a previously selected option
                    if (currentSelectedOption && currentSuggestions && currentSuggestions.length > 0) {
                        selectedOption = currentSelectedOption;
                        rolloverSuggestions = currentSuggestions;
                        
                        // Re-populate the suggestions table
                        populateRolloverSuggestionsTable(rolloverSuggestions);
                    }
                } catch (error) {
                    console.error('Error during refresh:', error);
                }
            });
        }
        
        // Set up refresh pending orders button
        const refreshPendingOrdersBtn = document.getElementById('refresh-pending-orders');
        if (refreshPendingOrdersBtn) {
            refreshPendingOrdersBtn.addEventListener('click', async () => {
                try {
                    // Refresh pending orders only
                    await loadPendingOrders();
                } catch (error) {
                    console.error('Error refreshing pending orders:', error);
                }
            });
        }
    } catch (error) {
        console.error('Error initializing rollover page:', error);
    }
}

/**
 * Load option positions and identify those approaching strike price
 */
async function loadOptionPositions() {
    try {
        // Fetch positions data
        const positionsData = await fetchPositions();
        if (!positionsData) {
            throw new Error('Failed to fetch positions data');
        }
        
        // Filter only option positions
        const optionPositions = positionsData.filter(position => 
            position.security_type === 'OPT' || position.securityType === 'OPT' || position.sec_type === 'OPT');
        
        console.log('Option positions loaded:', optionPositions.length);
        
        // Process all option positions with stock prices
        const processedOptions = await processOptionPositions(optionPositions);
        
        // Store the options data
        optionsData = processedOptions;
        
        // Populate the options table
        populateOptionsTable(processedOptions);
        
        // Only clear rollover suggestions if no option is selected AND we have no existing suggestions
        if (!selectedOption && (!rolloverSuggestions || rolloverSuggestions.length === 0)) {
            clearRolloverSuggestions();
        }
    } catch (error) {
        console.error('Error loading option positions:', error);
    }
}

/**
 * Process all option positions with strike price and stock price information
 * @param {Array} optionPositions - Array of option positions
 * @returns {Array} Processed options with additional information
 */
async function processOptionPositions(optionPositions) {
    // Filter options that have market price data
    const validOptions = optionPositions.filter(position => 
        position.market_price !== undefined && position.market_price !== null);
    
    // Extract tickers from options to fetch current stock prices
    const tickers = validOptions.map(position => {
        // Get base ticker symbol (without option specifics)
        const fullSymbol = position.symbol || '';
        return fullSymbol.split(' ')[0];
    });
    
    // Fetch current stock prices for all tickers
    const stockPrices = await fetchStockPrices(tickers);
    
    // Calculate difference from strike price for each option
    const processedOptions = validOptions.map(position => {
        // Extract option details
        let strike = 0;
        let optionType = '';
        
        // Get strike price and option type from either contract object or direct properties
        if (position.contract && position.contract.strike) {
            strike = position.contract.strike;
            optionType = position.contract.right === 'P' ? 'PUT' : 'CALL';
        } else {
            strike = position.strike || 0;
            optionType = position.option_type || '';
        }
        
        // Get base ticker symbol
        const ticker = (position.symbol || '').split(' ')[0];
        
        // Get current stock price - first try from fetched prices, then position data, then default to 0
        const stockPrice = stockPrices[ticker] || position.underlying_price || position.stock_price || 0;
        
        // Calculate difference between current price and strike
        let difference = 0;
        let percentDifference = 0;
        
        if (stockPrice > 0 && strike > 0) {
            // For calls: how far stock price is from strike (strike - stock)
            // For puts: how far stock price is from strike (stock - strike)
            if (optionType === 'CALL' || optionType === 'C' || optionType === 'Call') {
                difference = strike - stockPrice;
                percentDifference = (difference / strike) * 100;
            } else {
                difference = stockPrice - strike;
                percentDifference = (difference / strike) * 100;
            }
        }
        
        // Add a flag to indicate if the option is approaching strike price
        const isApproachingStrike = percentDifference >= 0 && percentDifference < 10;
        
        return {
            ...position,
            strike,
            optionType,
            stockPrice,
            difference,
            percentDifference,
            isApproachingStrike
        };
    });
    
    // Return all processed options, sorted by percentage difference in ascending order
    return processedOptions.sort((a, b) => {
        // Sort by crossing the strike first (negative percentDifference), then by absolute value
        if (a.percentDifference < 0 && b.percentDifference >= 0) return -1;
        if (a.percentDifference >= 0 && b.percentDifference < 0) return 1;
        // Both on same side, sort by absolute value (closer to zero is higher)
        return Math.abs(a.percentDifference) - Math.abs(b.percentDifference);
    });
}

/**
 * Populate options table with all option positions
 * @param {Array} options - Array of option positions
 */
function populateOptionsTable(options) {
    const tableBody = document.getElementById('option-positions-table-body');
    if (!tableBody) return;
    
    // Clear table
    tableBody.innerHTML = '';
    
    if (options.length === 0) {
        const noDataRow = document.createElement('tr');
        noDataRow.innerHTML = '<td colspan="9" class="text-center">No option positions found</td>';
        tableBody.appendChild(noDataRow);
        return;
    }
    
    // Add options to table
    options.forEach(option => {
        const row = document.createElement('tr');
        
        // Add row class based on percentage difference for approaching strike options
        if (option.isApproachingStrike) {
            if (option.percentDifference < 5) {
                row.classList.add('table-danger'); // Very close to strike
            } else if (option.percentDifference < 10) {
                row.classList.add('table-warning'); // Getting close to strike
            }
        }
        
        // Extract expiration date
        let expiration = '-';
        if (option.contract && option.contract.lastTradeDateOrContractMonth) {
            expiration = option.contract.lastTradeDateOrContractMonth;
        } else {
            expiration = option.expiration || '-';
        }
        
        // Make sure stockPrice is not undefined or zero
        const stockPrice = option.stockPrice > 0 ? option.stockPrice : 'Fetching...';
        
        // Format the difference with its sign (can be negative)
        const formattedDifference = formatCurrency(option.difference);
        
        // Format percent difference (still showing as absolute for highlighting)
        const absolutePercentDifference = Math.abs(option.percentDifference);
        
        // Color-code based on how close to strike (smaller is closer)
        let differenceColorClass = '';
        if (absolutePercentDifference < 5) {
            differenceColorClass = 'text-danger fw-bold';
        } else if (absolutePercentDifference < 10) {
            differenceColorClass = 'text-danger';
        }
        
        // Format percent difference display with the sign
        const percentDifferenceDisplay = `<span class="${differenceColorClass}">${option.percentDifference.toFixed(2)}%</span>`;
        
        const isShortPosition = Number(option.position) < 0;
        row.innerHTML = `
            <td>${option.symbol}</td>
            <td>${option.position}</td>
            <td>${option.optionType}</td>
            <td>${formatCurrency(option.strike)}</td>
            <td>${expiration}</td>
            <td>${typeof stockPrice === 'number' ? formatCurrency(stockPrice) : stockPrice}</td>
            <td>${formattedDifference}</td>
            <td>${percentDifferenceDisplay}</td>
            <td>
                <button class="btn btn-sm btn-primary roll-option-btn" data-option-id="${options.indexOf(option)}" ${isShortPosition ? '' : 'disabled'}>
                    ${isShortPosition ? 'Roll' : 'Long position'}
                </button>
            </td>
        `;
        
        tableBody.appendChild(row);
    });
    
    // Add event listeners to roll buttons
    const rollButtons = tableBody.querySelectorAll('.roll-option-btn');
    rollButtons.forEach(button => {
        button.addEventListener('click', async (event) => {
            const optionId = event.target.getAttribute('data-option-id');
            await selectOptionToRoll(parseInt(optionId));
            await revealWorkflowTarget(document.getElementById('rollover-suggestions-table-body'));
        });
    });
}

/**
 * Load pending orders from the API
 */
async function loadPendingOrders() {
    try {
        // Fetch only rollover-related orders
        const result = await fetchPendingOrders(false, true);
        if (!result) {
            throw new Error('Failed to fetch pending orders');
        }
        
        // Store the rollover orders directly
        pendingOrders = result.orders || [];
        
        // Populate the pending orders table
        populatePendingOrdersTable(pendingOrders);
        syncOrderStatusPolling();
        
        console.log('Rollover pending orders loaded:', pendingOrders.length);
    } catch (error) {
        console.error('Error loading pending orders:', error);
        showAlert(`Error loading rollover orders: ${error.message}`, 'danger');
    }
}

function syncOrderStatusPolling() {
    const needsTracking = pendingOrders.some(order =>
        TRACKED_ORDER_STATUSES.includes(String(order.status || '').toLowerCase())
    );

    if (needsTracking && !orderStatusTimer) {
        orderStatusTimer = setInterval(async () => {
            try {
                await checkOrderStatus();
                await loadPendingOrders();
            } catch (error) {
                console.error('Error tracking rollover order status:', error);
            }
        }, ORDER_STATUS_INTERVAL);
    } else if (!needsTracking && orderStatusTimer) {
        clearInterval(orderStatusTimer);
        orderStatusTimer = null;
    }
}

/**
 * Fetch current stock prices for the given tickers
 * @param {Array} tickers - Array of ticker symbols
 * @returns {Object} Object with ticker symbols as keys and stock prices as values
 */
async function fetchStockPrices(tickers) {
    try {
        const uniqueTickers = [...new Set(tickers)].filter(Boolean);
        
        if (uniqueTickers.length === 0) {
            console.log('No valid tickers to fetch prices for');
            return {};
        }
        
        console.log(`Fetching stock prices for ${uniqueTickers.length} tickers:`, uniqueTickers);
        
        // Call the dedicated API endpoint for stock prices
        const stockPrices = await apiFetchStockPrices(uniqueTickers);
        
        console.log('Fetched stock prices:', stockPrices);
        return stockPrices;
    } catch (error) {
        console.error('Error in fetchStockPrices:', error);
        return {};
    }
}

/**
 * Select an option to roll and prepare the UI without fetching data by default
 * @param {number} optionId - Index of the selected option in optionsData array
 */
async function selectOptionToRoll(optionId) {
    try {
        if (!optionsData || optionId < 0 || optionId >= optionsData.length) {
            throw new Error('Invalid option selected');
        }
        
        const option = optionsData[optionId];
        if (Number(option.position) >= 0) {
            throw new Error('Rollover is only supported for short option positions');
        }
        if (!Number.isInteger(Number(option.con_id)) || Number(option.con_id) <= 0) {
            throw new Error('The held option contract identifier is unavailable');
        }

        const freshQuote = await fetchHeldOptionQuote(option.con_id);
        selectedOption = {
            ...option,
            ...freshQuote,
            optionType: freshQuote.option_type || option.optionType,
            stockPrice: option.stockPrice
        };
        console.log('Selected option to roll:', selectedOption);
        
        // Get ticker symbol (remove option-specific parts if needed)
        const ticker = selectedOption.symbol.split(' ')[0];
        
        // Save current OTM percentage if already set
        let currentOtmValue = 10; // Default 10% OTM
        const existingOtmSelect = document.getElementById('otm-percentage');
        if (existingOtmSelect) {
            currentOtmValue = parseInt(existingOtmSelect.value) || 10;
        }
        
        // Clear previous suggestions
        const tableBody = document.getElementById('rollover-suggestions-table-body');
        if (!tableBody) return;
        
        // Clear the table
        tableBody.innerHTML = '';
        
        // Create OTM selector at the top (this will always be present)
        const otmSelectorRow = document.createElement('tr');
        otmSelectorRow.className = 'bg-light';
        otmSelectorRow.id = 'otm-selector-row'; // Add ID for easier reference
        
        // Create options string with 1% granularity
        let optionsHTML = '';
        for (let i = 1; i <= 30; i++) {
            const selected = i === currentOtmValue ? 'selected' : '';
            optionsHTML += `<option value="${i}" ${selected}>${i}%</option>`;
        }
        
        otmSelectorRow.innerHTML = `
            <td colspan="11">
                <div class="d-flex justify-content-between align-items-center mb-2">
                    <div class="d-flex align-items-center">
                        <label for="otm-percentage" class="me-2 mb-0">OTM Percentage:</label>
                        <select id="otm-percentage" class="form-select form-select-sm" style="width: auto;">
                            ${optionsHTML}
                        </select>
                    </div>
                    <button id="fetch-suggestions-btn" class="btn btn-sm btn-primary">
                        <i class="bi bi-arrow-repeat"></i> Fetch Rollover Options
                    </button>
                </div>
            </td>
        `;
        tableBody.appendChild(otmSelectorRow);
        
        // Show loading indicator
        const loadingRow = document.createElement('tr');
        loadingRow.innerHTML = `
            <td colspan="11" class="text-center">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading expiration dates...</span>
                </div>
                <p class="mt-2">Loading expiration dates for ${ticker}...</p>
            </td>
        `;
        tableBody.appendChild(loadingRow);
        
        // Fetch available expiration dates for the ticker
        let expirationDates = [];
        try {
            const expirationData = await fetchOptionExpirations(ticker);
            if (expirationData && expirationData.expirations) {
                expirationDates = expirationData.expirations;
                console.log(`Fetched ${expirationDates.length} expiration dates for ${ticker}`);
            }
        } catch (error) {
            console.error(`Error fetching expiration dates for ${ticker}:`, error);
            // Continue even if we couldn't fetch expirations, we'll use the default +7 days
        }
        
        // Remove loading indicator but keep OTM selector
        tableBody.innerHTML = '';
        tableBody.appendChild(otmSelectorRow);
        
        // Create a header row for the buy action
        const buyHeaderRow = document.createElement('tr');
        buyHeaderRow.className = 'table-primary';
        buyHeaderRow.innerHTML = '<td colspan="9" class="fw-bold">BUY TO CLOSE</td>';
        tableBody.appendChild(buyHeaderRow);
        
        // Create row for the buy action (current option)
        const buyRow = document.createElement('tr');
        
        // For BUY TO CLOSE, we use the ask price since we're buying
        const buyAsk = positivePrice(selectedOption.ask);
        const quantity = Math.abs(selectedOption.position);
        
        // Get delta and IV for current option
        const delta = selectedOption.delta || 'N/A';
        const iv = selectedOption.implied_volatility || 'N/A';
        const formattedDelta = typeof delta === 'number' ? delta.toFixed(2) : delta;
        const formattedIV = typeof iv === 'number' ? `${iv.toFixed(1)}%` : iv;
        
        buyRow.innerHTML = `
            <td>BUY</td>
            <td>${selectedOption.symbol}</td>
            <td>${selectedOption.optionType}</td>
            <td>${formatCurrency(selectedOption.strike)}</td>
            <td>${selectedOption.expiration}</td>
            <td>${quantity}</td>
            <td>${formatQuotePrice(buyAsk)} <small class="text-muted" title="Ask price per share">(ask)</small></td>
            <td>LIMIT</td>
            <td>${formattedDelta}</td>
            <td>${formattedIV}</td>
            <td><span class="badge bg-info">Current Position</span></td>
        `;
        tableBody.appendChild(buyRow);
        
        // Create a header row for the sell action
        const sellHeaderRow = document.createElement('tr');
        sellHeaderRow.className = 'table-success';
        sellHeaderRow.innerHTML = '<td colspan="9" class="fw-bold">SELL TO OPEN (NEW POSITION)</td>';
        tableBody.appendChild(sellHeaderRow);
        
        // Calculate estimated values for the new option
        let estimatedStrike;
        const optionType = selectedOption.optionType;
        const defaultOtm = currentOtmValue; // Use the current OTM value from dropdown
        
        // Calculate estimated strike based on option type and current stock price
        if (optionType === 'CALL' || optionType === 'C' || optionType === 'Call') {
            // For calls, target is higher than current price (OTM)
            estimatedStrike = selectedOption.stockPrice * (1 + defaultOtm/100);
        } else {
            // For puts, target is lower than current price (OTM)
            estimatedStrike = selectedOption.stockPrice * (1 - defaultOtm/100);
        }
        
        // Round the strike to common option strike increments
        const roundedStrike = Math.round(estimatedStrike * 2) / 2; // Round to nearest 0.5
        
        // Parse expiration date of current option to calculate new expiration (one week later)
        let currentExpiry;
        let oneWeekLaterFormatted = "Exp. date + 1 week";
        
        try {
            // Parse the expiration date of the current option
            if (selectedOption.expiration.includes('-')) {
                // If it's already in YYYY-MM-DD format
                currentExpiry = new Date(selectedOption.expiration);
            } else if (selectedOption.expiration.includes('/')) {
                // If it's in MM/DD/YYYY format
                const parts = selectedOption.expiration.split('/');
                currentExpiry = new Date(parts[2], parts[0] - 1, parts[1]);
            } else if (/^\d{8}$/.test(selectedOption.expiration)) {
                // If it's in YYYYMMDD format
                const year = selectedOption.expiration.substring(0, 4);
                const month = selectedOption.expiration.substring(4, 6);
                const day = selectedOption.expiration.substring(6, 8);
                currentExpiry = new Date(year, month - 1, day);
            } else {
                // Try direct parsing as a fallback
                currentExpiry = new Date(selectedOption.expiration);
            }
            
            // Add 7 days to get the estimated expiration
            const oneWeekLater = new Date(currentExpiry);
            oneWeekLater.setDate(oneWeekLater.getDate() + 7);
            
            // Format to MM/DD/YYYY for display
            const month = String(oneWeekLater.getMonth() + 1).padStart(2, '0');
            const day = String(oneWeekLater.getDate()).padStart(2, '0');
            const year = oneWeekLater.getFullYear();
            oneWeekLaterFormatted = `${month}/${day}/${year}`;
            
            // Also format to YYYYMMDD for API
            const apiFormat = `${year}${month}${day}`;
            selectedOption.estimatedNextExpiration = apiFormat;
        } catch (e) {
            console.warn("Error estimating expiration date:", e);
        }
        
        // Create expiration date dropdown options using the fetched dates
        let expirationOptionsHtml = '';
        let defaultExpirationFound = false;
        
        if (expirationDates.length > 0) {
            // We have expiration dates from the API, use them
            expirationDates.forEach(exp => {
                // Try to set default to the closest to one week after current
                let selected = '';
                if (selectedOption.estimatedNextExpiration) {
                    if (exp.value >= selectedOption.estimatedNextExpiration && !defaultExpirationFound) {
                        selected = 'selected';
                        defaultExpirationFound = true;
                    }
                }
                expirationOptionsHtml += `<option value="${exp.value}" ${selected}>${exp.label}</option>`;
            });
        } else {
            // Fallback to a single estimated option
            expirationOptionsHtml = `<option value="estimated" selected>${oneWeekLaterFormatted}</option>`;
        }
        
        // Add placeholder row with estimated values and expiration dropdown for sell action
        const sellRow = document.createElement('tr');
        sellRow.innerHTML = `
            <td>SELL</td>
            <td>${ticker}</td>
            <td>${optionType}</td>
            <td>${formatCurrency(roundedStrike)} (est.)</td>
            <td>
                <select id="expiration-select" class="form-select form-select-sm">
                    ${expirationOptionsHtml}
                </select>
            </td>
            <td>${quantity}</td>
            <td>-- (fetch to see)</td>
            <td>LIMIT</td>
            <td>-- (fetch to see)</td>
        `;
        tableBody.appendChild(sellRow);
        
        // Add event listener to fetch button
        setTimeout(() => {
            const fetchBtn = document.getElementById('fetch-suggestions-btn');
            if (fetchBtn) {
                fetchBtn.addEventListener('click', async () => {
                    const otmSelect = document.getElementById('otm-percentage');
                    const expSelect = document.getElementById('expiration-select');
                    
                    // Add null checks before accessing value properties
                    const otmValue = otmSelect ? parseInt(otmSelect.value) : 10; // Default to 10% OTM if not found
                    const expValue = expSelect ? expSelect.value : 'estimated'; // Default to 'estimated' if not found
                    
                    if (selectedOption && otmValue) {
                        // Update the selectedOption with the user selections
                        selectedOption.otmPercentage = otmValue;
                        
                        // Only set expiration if it's a valid value (not "estimated")
                        if (expValue !== 'estimated') {
                            selectedOption.targetExpiration = expValue;
                        }
                        
                        // Now fetch the actual option data
                        await fetchRolloverSuggestions();
                    }
                });
            }
        }, 0);
    } catch (error) {
        console.error('Error selecting option to roll:', error);
        showAlert(`Rollover is unavailable: ${error.message}`, 'danger', 10000);
    }
}

/**
 * Populate rollover suggestions table
 * @param {Array} suggestions - Array of rollover suggestions
 */
function populateRolloverSuggestionsTable(suggestions) {
    const tableBody = document.getElementById('rollover-suggestions-table-body');
    if (!tableBody) return;
    
    // Save the current OTM selector row if it exists
    const otmSelectorRow = document.getElementById('otm-selector-row');
    
    // Clear table except for the OTM selector row if it exists
    if (otmSelectorRow) {
        tableBody.innerHTML = '';
        tableBody.appendChild(otmSelectorRow);
    } else {
        tableBody.innerHTML = '';
    }
    
    if (!selectedOption || suggestions.length === 0) {
        const noDataRow = document.createElement('tr');
        noDataRow.innerHTML = '<td colspan="11" class="text-center">No rollover suggestions available</td>';
        tableBody.appendChild(noDataRow);
        return;
    }

    // Create a header row for the buy action
    const buyHeaderRow = document.createElement('tr');
    buyHeaderRow.className = 'table-primary';
    buyHeaderRow.innerHTML = '<td colspan="11" class="fw-bold">BUY TO CLOSE</td>';
    tableBody.appendChild(buyHeaderRow);
    
    // Create row for the buy action (current option)
    const buyRow = document.createElement('tr');
    
    // For BUY TO CLOSE, we use the ask price since we're buying
    const buyAsk = positivePrice(selectedOption.ask);
    const quantity = Math.abs(selectedOption.position);
    
    // Get delta and IV for current option
    const delta = selectedOption.delta || 'N/A';
    const iv = selectedOption.implied_volatility || 'N/A';
    const formattedDelta = typeof delta === 'number' ? delta.toFixed(2) : delta;
    const formattedIV = typeof iv === 'number' ? `${iv.toFixed(1)}%` : iv;
    
    buyRow.innerHTML = `
        <td>BUY</td>
        <td>${selectedOption.symbol}</td>
        <td>${selectedOption.optionType}</td>
        <td>${formatCurrency(selectedOption.strike)}</td>
        <td>${selectedOption.expiration}</td>
        <td>${quantity}</td>
        <td>${formatQuotePrice(buyAsk)} <small class="text-muted" title="Ask price per share">(ask)</small></td>
        <td>LIMIT</td>
        <td>${formattedDelta}</td>
        <td>${formattedIV}</td>
        <td><span class="badge bg-info">Current Position</span></td>
    `;
    tableBody.appendChild(buyRow);
    
    // Create a header row for the sell action
    const sellHeaderRow = document.createElement('tr');
    sellHeaderRow.className = 'table-success';
    sellHeaderRow.innerHTML = '<td colspan="11" class="fw-bold">SELL TO OPEN (NEW POSITION)</td>';
    tableBody.appendChild(sellHeaderRow);
    
    // For each suggestion, create a sell row
    suggestions.forEach((suggestion, index) => {
        const sellRow = document.createElement('tr');
        
        // Calculate the mid price for limit orders
        const bid = positivePrice(suggestion.bid);
        const ask = positivePrice(suggestion.ask);
        const midPrice = calculateMidPrice(bid, ask);
        const quoteAvailable = buyAsk !== null && midPrice !== null;
        
        // Include bid/ask in tooltip for transparency
        const bidAskTooltip = `bid: ${formatQuotePrice(bid)}, ask: ${formatQuotePrice(ask)}`;
        
        // Get delta and IV for suggestion
        const delta = suggestion.delta || 'N/A';
        const iv = suggestion.implied_volatility || 'N/A';
        const formattedDelta = typeof delta === 'number' ? delta.toFixed(2) : delta;
        const formattedIV = typeof iv === 'number' ? `${iv.toFixed(1)}%` : iv;
        
        sellRow.innerHTML = `
            <td>SELL</td>
            <td>${selectedOption.symbol.split(' ')[0]}</td>
            <td>${selectedOption.optionType}</td>
            <td>${formatCurrency(suggestion.strike)}</td>
            <td>${suggestion.expiration}</td>
            <td>${quantity}</td>
            <td>${formatQuotePrice(midPrice)} <small class="text-muted" title="${bidAskTooltip}">(mid)</small></td>
            <td>LIMIT</td>
            <td>${formattedDelta}</td>
            <td>${formattedIV}</td>
            <td>
                <button class="btn btn-sm btn-success rollover-btn" data-suggestion-id="${index}" ${quoteAvailable ? '' : 'disabled'}>
                    Execute Rollover
                </button>
            </td>
        `;
        
        tableBody.appendChild(sellRow);
    });
    
    // Only add an execute button for all if we have multiple suggestions
    const firstSuggestionMid = suggestions.length > 0
        ? calculateMidPrice(suggestions[0].bid, suggestions[0].ask)
        : null;
    if (suggestions.length > 1) {
        // Single execute button at the bottom
        const executeAllRow = document.createElement('tr');
        executeAllRow.className = 'bg-light';
        executeAllRow.innerHTML = `
            <td colspan="11" class="text-center">
                <button id="execute-rollover-btn" class="btn btn-primary mt-2" ${buyAsk !== null && firstSuggestionMid !== null ? '' : 'disabled'}>
                    <i class="bi bi-check2-all"></i> Execute Rollover with First Option
                </button>
            </td>
        `;
        tableBody.appendChild(executeAllRow);
    }
    
    // Add event listeners to rollover buttons
    const rolloverButtons = tableBody.querySelectorAll('.rollover-btn');
    rolloverButtons.forEach(button => {
        button.addEventListener('click', async (event) => {
            const suggestionId = parseInt(event.target.getAttribute('data-suggestion-id'));
            await addRolloverOrder(suggestionId);
        });
    });
    
    // Add event listener to execute button
    const executeBtn = document.getElementById('execute-rollover-btn');
    if (executeBtn) {
        executeBtn.addEventListener('click', async () => {
            if (suggestions.length > 0) {
                await addRolloverOrder(0); // Execute with the first suggestion
            }
        });
    }
}

/**
 * Populate pending orders table
 * @param {Array} orders - Array of pending orders
 */
function populatePendingOrdersTable(orders) {
    const tableBody = document.getElementById('pending-orders-table-body');
    if (!tableBody) return;

    tableBody.innerHTML = '';

    const visibleOrders = (orders || []).filter(order =>
        ACTIVE_ORDER_STATUSES.includes(String(order.status || '').toLowerCase())
    );
    if (visibleOrders.length === 0) {
        const noDataRow = document.createElement('tr');
        noDataRow.innerHTML = '<td colspan="10" class="text-center">No pending rollover orders found</td>';
        tableBody.appendChild(noDataRow);
        return;
    }

    visibleOrders.sort((a, b) => {
        const timestampA = a.timestamp || a.date_created || 0;
        const timestampB = b.timestamp || b.date_created || 0;
        if (!isNaN(timestampA) && !isNaN(timestampB)) {
            return timestampB - timestampA;
        }
        return new Date(timestampB) - new Date(timestampA);
    });

    visibleOrders.forEach(order => {
        const row = document.createElement('tr');
        row.dataset.orderId = String(order.id);
        const strike = order.strike ? formatCurrency(order.strike) : 'N/A';
        const limitPrice = Number(order.premium);
        let priceContext = '';
        if (order.action === 'BUY' && Number(order.ask) > 0) {
            priceContext = '<small class="text-muted" title="Ask price per share">(ask)</small>';
        } else if (order.action === 'SELL' && Number(order.bid) > 0 && Number(order.ask) > 0) {
            const bidAskTooltip = `bid: ${formatCurrency(order.bid)}, ask: ${formatCurrency(order.ask)}`;
            priceContext = `<small class="text-muted" title="${bidAskTooltip}">(mid)</small>`;
        }
        const limitPriceDisplay = Number.isFinite(limitPrice) && limitPrice > 0
            ? `${formatCurrency(limitPrice)} ${priceContext}`
            : '-';
        const createdAt = formatDate(order.timestamp || order.date_created);
        const normalizedStatus = String(order.status || 'pending').toLowerCase();
        let statusText = normalizedStatus;
        let rowClass = '';

        if (normalizedStatus === 'executed' || normalizedStatus === 'filled') {
            rowClass = 'table-success';
            statusText = 'Executed';
        } else if (['cancelled', 'rejected', 'canceled'].includes(normalizedStatus)) {
            rowClass = 'table-danger';
            statusText = normalizedStatus === 'rejected' ? 'Rejected' : 'Cancelled';
        } else if (normalizedStatus === 'submitting') {
            rowClass = 'table-warning';
            statusText = 'Submitting';
        } else if (normalizedStatus === 'processing') {
            rowClass = 'table-warning';
            statusText = 'Processing';
        } else if (normalizedStatus === 'canceling') {
            rowClass = 'table-warning';
            statusText = 'Canceling';
        } else if (normalizedStatus === 'unknown') {
            rowClass = 'table-danger';
            statusText = 'Check IB';
        } else {
            statusText = 'Pending';
        }

        let statusHtml = `<span class="badge bg-${getBadgeColor(order.status)}">${statusText}</span>`;
        if (createdAt) {
            statusHtml += `<br><small class="text-muted">${createdAt}</small>`;
        }
        if (order.ib_order_id) {
            statusHtml += `
                <br><small class="text-muted"><strong>IB ID:</strong> ${order.ib_order_id}</small>
                <br><small class="text-muted"><strong>Status:</strong> ${order.ib_status || 'Unknown'}</small>
            `;
            if (order.avg_fill_price && order.status === 'executed') {
                statusHtml += `<br><small class="text-muted"><strong>Fill Price:</strong> ${formatCurrency(order.avg_fill_price)}</small>`;
            }
        }

        const quantityCell = normalizedStatus === 'pending' && !String(order.id).startsWith('temp-')
            ? `<input type="number" class="form-control form-control-sm quantity-input" data-order-id="${order.id}" value="${order.quantity}" min="1" max="100">`
            : `${order.quantity}`;
        let actionButtons = '';
        const isTemporaryOrder = String(order.id).startsWith('temp-');

        if (isTemporaryOrder) {
            actionButtons = `
                <button class="btn btn-sm btn-outline-secondary" disabled>
                    <i class="bi bi-hourglass"></i> Pending Submission
                </button>
            `;
        } else if (normalizedStatus === 'pending') {
            actionButtons = `
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-primary execute-order-btn" data-order-id="${order.id}">
                        <i class="bi bi-play-fill"></i> Execute
                    </button>
                    <button class="btn btn-outline-danger cancel-order-btn" data-order-id="${order.id}">
                        <i class="bi bi-x-circle"></i> Cancel
                    </button>
                </div>
            `;
        } else if (normalizedStatus === 'processing' || (normalizedStatus === 'unknown' && order.ib_order_id)) {
            actionButtons = `
                <button class="btn btn-sm btn-outline-danger cancel-order-btn" data-order-id="${order.id}">
                    <i class="bi bi-x-circle"></i> Cancel
                </button>
            `;
        } else if (normalizedStatus === 'submitting' || normalizedStatus === 'canceling') {
            actionButtons = `
                <button class="btn btn-sm btn-outline-secondary" disabled>
                    <i class="bi bi-hourglass-split"></i> ${statusText}
                </button>
            `;
        } else {
            actionButtons = '-';
        }

        row.className = rowClass;
        row.innerHTML = `
            <td>${isTemporaryOrder ? '<span class="badge bg-info">Pending</span>' : order.id}</td>
            <td>${order.action}</td>
            <td>${order.ticker}</td>
            <td>${order.option_type}</td>
            <td>${strike}</td>
            <td>${order.expiration || 'N/A'}</td>
            <td>${quantityCell}</td>
            <td>${limitPriceDisplay}</td>
            <td>${statusHtml}</td>
            <td>${actionButtons}</td>
        `;
        tableBody.appendChild(row);
    });

    const executeButtons = tableBody.querySelectorAll('.execute-order-btn');
    executeButtons.forEach(button => {
        button.addEventListener('click', async (event) => {
            const orderId = event.target.closest('.execute-order-btn').getAttribute('data-order-id');
            confirmOrderExecution(parseInt(orderId, 10), button);
        });
    });

    const cancelButtons = tableBody.querySelectorAll('.cancel-order-btn');
    cancelButtons.forEach(button => {
        button.addEventListener('click', async (event) => {
            const orderId = event.target.closest('.cancel-order-btn').getAttribute('data-order-id');
            await cancelOrderById(parseInt(orderId, 10));
        });
    });

    const quantityInputs = tableBody.querySelectorAll('.quantity-input');
    quantityInputs.forEach(input => {
        input.addEventListener('change', async (event) => {
            const orderId = event.target.dataset.orderId;
            const newQuantity = parseInt(event.target.value, 10);
            if (orderId && !isNaN(newQuantity) && newQuantity > 0) {
                try {
                    const response = await fetch(`/api/options/order/${orderId}/quantity`, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-All-You-Need-Is-Wheel': '1',
                        },
                        body: JSON.stringify({ quantity: newQuantity })
                    });
                    
                    if (!response.ok) {
                        const data = await response.json().catch(() => ({}));
                        throw new Error(data.error || `Failed to update quantity: ${response.statusText}`);
                    }
                    await response.json();
                    showAlert(`Quantity updated to ${newQuantity}`, 'success');
                    await loadPendingOrders();
                } catch (error) {
                    console.error(`Error updating quantity for order ${orderId}:`, error);
                    showAlert(`Quantity was not updated: ${error.message}`, 'danger');
                    const order = pendingOrders.find(o => o.id === parseInt(orderId, 10));
                    if (order) {
                        event.target.value = order.quantity || 1;
                    }
                }
            } else {
                showAlert('Quantity must be a whole number between 1 and 100', 'warning');
                const order = pendingOrders.find(o => o.id === parseInt(orderId, 10));
                if (order) {
                    event.target.value = order.quantity || 1;
                }
            }
        });
    });
}

/**
 * Get appropriate badge color for order status
 * @param {string} status - Order status
 * @returns {string} Bootstrap color class
 */
function getBadgeColor(status) {
    if (!status) return 'secondary';
    
    status = status.toLowerCase();
    
    if (status === 'executed' || status === 'filled') {
        return 'success';
    } else if (status === 'cancelled' || status === 'canceled' || status === 'rejected') {
        return 'danger';
    } else if (status === 'submitting' || status === 'processing' || status === 'canceling') {
        return 'warning';
    } else if (status === 'unknown') {
        return 'danger';
    } else {
        return 'secondary'; // Default for pending and other statuses
    }
}

/**
 * Format a date string for display
 * @param {string} dateStr - Date string to format
 * @returns {string} Formatted date string
 */
function formatDate(dateStr) {
    if (!dateStr) return '';
    
    try {
        const date = new Date(dateStr);
        if (isNaN(date.getTime())) return dateStr; // Return original if invalid
        
        return date.toLocaleString();
    } catch (e) {
        return dateStr; // Return original on error
    }
}

/**
 * Execute an order by ID
 * @param {number} orderId - The order ID to execute
 */
function confirmOrderExecution(orderId, sourceButton) {
    const order = pendingOrders.find(item => item.id === orderId);
    if (!order || String(order.status).toLowerCase() !== 'pending') {
        showAlert('Only pending orders can be executed', 'warning');
        return;
    }

    if (window.shouldConfirmOrderExecution?.() === false) {
        void executeOrderById(orderId, sourceButton);
        return;
    }

    const quantity = Number(order.quantity || 1);
    const price = Number(order.premium || 0);
    const summary = [
        'This submits ONE rollover leg to IB.',
        `${tr('common.action')}: ${order.action}`,
        `${tr('common.ticker')}: ${order.ticker} ${order.option_type}`,
        `${tr('common.strike')}: ${formatCurrency(order.strike)}`,
        `${tr('common.expiration')}: ${order.expiration}`,
        `${tr('common.quantity')}: ${quantity}`,
        `${tr('common.limitPrice')}: ${formatCurrency(price)} / share`,
        `Contract total: ${formatCurrency(price * 100 * quantity)}`,
        'Verify the other rollover leg separately.'
    ].join('\n');

    const modalElement = document.getElementById('confirmRolloverOrderModal');
    const confirmButton = document.getElementById('confirmRolloverOrderModal-confirm');
    if (!modalElement || !confirmButton || !window.bootstrap?.Modal) {
        if (window.confirm(summary)) executeOrderById(orderId, sourceButton);
        return;
    }

    const modalBody = modalElement.querySelector('.modal-body');
    modalBody.textContent = summary;
    modalBody.style.whiteSpace = 'pre-line';
    const modal = bootstrap.Modal.getOrCreateInstance(modalElement);
    confirmButton.onclick = async () => {
        confirmButton.disabled = true;
        modal.hide();
        try {
            await executeOrderById(orderId, sourceButton);
        } finally {
            confirmButton.disabled = false;
        }
    };
    modal.show();
}

async function executeOrderById(orderId, sourceButton = null) {
    if (orderExecutionInFlight.has(orderId)) return;
    orderExecutionInFlight.add(orderId);
    if (sourceButton) sourceButton.disabled = true;

    try {
        if (!orderId) {
            throw new Error('Invalid order ID');
        }
        
        // Find the order in pendingOrders array
        const order = pendingOrders.find(o => o.id === orderId);
        if (!order) {
            throw new Error(`Order with ID ${orderId} not found`);
        }
        
        const result = await executeOrder(orderId);
        
        if (result && result.success) {
            showAlert(`Rollover leg sent to IB (order ${result.ib_order_id || '-'})`, 'success');
            await loadPendingOrders();
        } else {
            throw new Error(result.error || 'Failed to execute order');
        }
    } catch (error) {
        console.error('Error executing order:', error);
        showAlert(`Rollover order was not confirmed: ${error.message}`, 'danger', 10000);
        await loadPendingOrders();
    } finally {
        orderExecutionInFlight.delete(orderId);
        if (sourceButton?.isConnected) sourceButton.disabled = false;
    }
}

/**
 * Cancel an order by ID
 * @param {number} orderId - The order ID to cancel
 */
async function cancelOrderById(orderId) {
    const sourceOrder = pendingOrders.find(order => order.id === orderId);
    try {
        if (!orderId) {
            throw new Error('Invalid order ID');
        }
        
        // Cancel the order
        const result = await cancelOrder(orderId);
        
        if (result && result.success) {
            showAlert(result.message || 'Cancellation requested', 'success');
            await loadPendingOrders();
            if (['canceled', 'cancelled'].includes(result.status)) await returnToOpportunity(sourceOrder);
        } else {
            throw new Error(result.error || 'Failed to cancel order');
        }
    } catch (error) {
        console.error('Error cancelling order:', error);
        showAlert(`Cancellation was not confirmed: ${error.message}`, 'danger', 10000);
        await loadPendingOrders();
    }
}

/**
 * Clear rollover suggestions table (only if there are no existing suggestions)
 */
function clearRolloverSuggestions() {
    const tableBody = document.getElementById('rollover-suggestions-table-body');
    if (!tableBody) return;
    
    // Don't clear anything if we already have content (except for the default message)
    if (tableBody.childElementCount > 1) {
        return;
    }
    
    // Only clear and show default message if the table is empty or just has the default message
    tableBody.innerHTML = '<tr><td colspan="9" class="text-center">Select an option to roll to view suggested replacements.</td></tr>';
}

/**
 * Add a rollover order
 * @param {number} suggestionId - ID of the suggestion to use for rollover
 */
async function addRolloverOrder(suggestionId) {
    try {
        if (!selectedOption || !rolloverSuggestions || suggestionId < 0 || suggestionId >= rolloverSuggestions.length) {
            throw new Error('Invalid rollover suggestion selected');
        }
        
        const suggestion = rolloverSuggestions[suggestionId];
        
        // Calculate quantities and premiums
        const quantity = Math.abs(selectedOption.position);
        
        // For the SELL TO OPEN (new position), calculate mid price between bid and ask
        const sellBid = positivePrice(suggestion.bid);
        const sellAsk = positivePrice(suggestion.ask);
        const sellMidPrice = calculateMidPrice(sellBid, sellAsk);

        if (sellMidPrice === null) {
            throw new Error('A valid two-sided quote is required for the new option');
        }
        
        console.log(`Using sell mid price: $${sellMidPrice} per share (bid: $${sellBid}, ask: $${sellAsk})`);
        
        // For the BUY TO CLOSE (current position), use the ask price
        // We're buying, so we pay what sellers are asking
        const buyAsk = positivePrice(selectedOption.ask);
        const buyBid = positivePrice(selectedOption.bid);

        if (buyAsk === null) {
            throw new Error('A valid ask quote is required for the current option');
        }
        
        console.log(`Using buy ask price: $${buyAsk} per share`);
        
        // IB option limit prices use the displayed per-share quote for both legs.
        const buyLimitPrice = buyAsk;
        const sellLimitPrice = sellMidPrice;
        
        // Create rollover data object
        const rolloverData = {
            current_con_id: selectedOption.con_id,
            ticker: selectedOption.symbol.split(' ')[0],
            current_option_type: selectedOption.optionType,
            current_strike: selectedOption.strike,
            current_expiration: selectedOption.expiration,
            new_strike: suggestion.strike,
            new_expiration: suggestion.expiration,
            quantity: quantity,
            // Use LIMIT for both orders
            current_order_type: 'LIMIT',
            new_order_type: 'LIMIT',
            current_limit_price: buyLimitPrice,
            new_limit_price: sellLimitPrice,
            // Include raw bid and ask information for both current and new positions
            current_bid: buyBid,
            current_ask: buyAsk,
            new_bid: sellBid,
            new_ask: sellAsk,
            isRollover: true  // Explicitly flag these as rollover orders
        };
        
        console.log('Rollover order data prepared:', rolloverData);
        
        // Submit the order directly without creating temporary orders
        
        // Save current suggestions and selected option for restoring UI state later
        const currentSuggestions = [...rolloverSuggestions];
        const currentOption = {...selectedOption};
        
        // Call the rollover API endpoint
        const response = await fetch('/api/options/rollover', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-All-You-Need-Is-Wheel': '1',
            },
            body: JSON.stringify(rolloverData)
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP error ${response.status}: ${errorText}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
            showAlert(
                `Rollover staged: BUY ${formatCurrency(buyLimitPrice)} and SELL ${formatCurrency(sellLimitPrice)} per share`,
                'success'
            );
            // Reload pending orders and option positions
            await Promise.all([
                loadPendingOrders(),
                loadOptionPositions()
            ]);
            
            // Restore the suggestions and selected option to keep UI consistent
            rolloverSuggestions = currentSuggestions;
            selectedOption = currentOption;
            
            // Re-populate the rollover suggestions table with the saved suggestions
            if (rolloverSuggestions.length > 0) {
                populateRolloverSuggestionsTable(rolloverSuggestions);
            }
            await revealPendingOrder(result.buy_order_id);
        } else {
            throw new Error(result.error || 'Failed to submit rollover orders');
        }
    } catch (error) {
        console.error('Error preparing rollover order:', error);
        showAlert(`Rollover was not staged: ${error.message}`, 'danger', 10000);
    }
}

/**
 * Fetch rollover suggestions based on the selected option and OTM percentage
 */
async function fetchRolloverSuggestions() {
    try {
        if (!selectedOption) {
            throw new Error('No option selected for rollover');
        }
        
        // Save the OTM selector row
        const otmSelectorRow = document.getElementById('otm-selector-row');
        const tableBody = document.getElementById('rollover-suggestions-table-body');
        
        // Show loading indicator while preserving OTM selector
        if (tableBody && otmSelectorRow) {
            tableBody.innerHTML = '';
            tableBody.appendChild(otmSelectorRow);
            
            const loadingRow = document.createElement('tr');
            loadingRow.innerHTML = `
                <td colspan="11" class="text-center">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Loading expiration dates...</span>
                    </div>
                    <p class="mt-2">Loading expiration dates for ${selectedOption.symbol.split(' ')[0]}...</p>
                </td>
            `;
            tableBody.appendChild(loadingRow);
        }
        
        // Get ticker symbol (remove option-specific parts if needed)
        const ticker = selectedOption.symbol.split(' ')[0];
        
        // Fetch current stock price using the dedicated endpoint
        const stockPrices = await apiFetchStockPrices(ticker);
        const latestStockPrice = stockPrices[ticker] || selectedOption.stockPrice;
        
        // Update the stock price with the latest data
        selectedOption.stockPrice = latestStockPrice;
        
        // Recalculate difference and percentage with updated stock price
        if (latestStockPrice > 0 && selectedOption.strike > 0) {
            if (selectedOption.optionType === 'CALL' || selectedOption.optionType === 'C' || selectedOption.optionType === 'Call') {
                selectedOption.difference = selectedOption.strike - latestStockPrice;
                selectedOption.percentDifference = (selectedOption.difference / selectedOption.strike) * 100;
            } else {
                selectedOption.difference = latestStockPrice - selectedOption.strike;
                selectedOption.percentDifference = (selectedOption.difference / selectedOption.strike) * 100;
            }
        }
        
        // Get OTM percentage from dropdown
        let otmPercentage = 10; // Default
        
        // If the dropdown exists, get value from there
        const otmDropdown = document.getElementById('otm-percentage');
        if (otmDropdown) {
            const dropdownValue = parseInt(otmDropdown.value);
            if (!isNaN(dropdownValue)) {
                otmPercentage = dropdownValue;
                // Save this value for future use
                selectedOption.otmPercentage = otmPercentage;
            }
        } else if (selectedOption.otmPercentage) {
            // If dropdown doesn't exist but we have a saved percentage, use that
            otmPercentage = selectedOption.otmPercentage;
        }
        
        console.log(`Using OTM percentage: ${otmPercentage}%`);
        
        // Get target expiration date - prioritize the user selection from dropdown if available
        let targetExpirationForAPI;
        
        // Check if the expiration dropdown exists
        const expDropdown = document.getElementById('expiration-select');
        if (expDropdown && expDropdown.value && expDropdown.value !== 'estimated') {
            // Use the expiration selected by the user in the dropdown
            targetExpirationForAPI = expDropdown.value;
            selectedOption.targetExpiration = targetExpirationForAPI;
            console.log(`Using user-selected expiration date: ${targetExpirationForAPI}`);
        } else if (selectedOption.targetExpiration) {
            // If dropdown doesn't exist but we have a saved target expiration, use that
            targetExpirationForAPI = selectedOption.targetExpiration;
            console.log(`Using previously saved expiration date: ${targetExpirationForAPI}`);
        } else {
            // Fall back to calculating expiration based on current option + 7 days
            console.log("No user-selected expiration date. Calculating based on current option + 7 days.");
            
            // Safely parse the expiration date
            let currentExpiry;
            try {
                // Make sure we have an expiration date to work with
                if (!selectedOption.expiration) {
                    throw new Error("Option has no expiration date");
                }
                
                console.log("Raw expiration date to parse:", selectedOption.expiration);
                
                // Try different date formats since the expiration might be in various formats
                if (selectedOption.expiration.includes('-')) {
                    // If it's already in YYYY-MM-DD format
                    currentExpiry = new Date(selectedOption.expiration);
                } else if (selectedOption.expiration.includes('/')) {
                    // If it's in MM/DD/YYYY format
                    const parts = selectedOption.expiration.split('/');
                    currentExpiry = new Date(parts[2], parts[0] - 1, parts[1]);
                } else if (/^\d{8}$/.test(selectedOption.expiration)) {
                    // If it's in YYYYMMDD format
                    const year = selectedOption.expiration.substring(0, 4);
                    const month = selectedOption.expiration.substring(4, 6);
                    const day = selectedOption.expiration.substring(6, 8);
                    currentExpiry = new Date(year, month - 1, day);
                } else if (/^\d{6}$/.test(selectedOption.expiration)) {
                    // If it's in YYMMDD format
                    const year = "20" + selectedOption.expiration.substring(0, 2);
                    const month = selectedOption.expiration.substring(2, 4);
                    const day = selectedOption.expiration.substring(4, 6);
                    currentExpiry = new Date(year, month - 1, day);
                } else {
                    // Try direct parsing as a fallback
                    currentExpiry = new Date(selectedOption.expiration);
                }
                
                // Validate the date
                if (isNaN(currentExpiry.getTime())) {
                    throw new Error("Invalid date format: " + selectedOption.expiration);
                }
                
                console.log("Successfully parsed expiration date:", currentExpiry);
                
                // Calculate the target date (exactly one week later from the option's expiration)
                const oneWeekLater = new Date(currentExpiry);
                oneWeekLater.setDate(oneWeekLater.getDate() + 7);
                
                console.log("Option expiration:", currentExpiry.toISOString().split('T')[0]);
                console.log("Target date (one week later):", oneWeekLater.toISOString().split('T')[0]);
                
                // Format target date for API (YYYYMMDD format)
                const formatAPIDate = (date) => {
                    const year = date.getFullYear();
                    const month = String(date.getMonth() + 1).padStart(2, '0');
                    const day = String(date.getDate()).padStart(2, '0');
                    return `${year}${month}${day}`;
                };
                
                targetExpirationForAPI = formatAPIDate(oneWeekLater);
                console.log("Calculated target expiration for API:", targetExpirationForAPI);
            } catch (e) {
                console.error("Error parsing expiration date:", e);
                
                // Instead of using today's date, we'll need to abort the operation
                // since we don't have a valid reference point
                throw new Error(`Couldn't parse option expiration date: ${e.message}`);
            }
        }
        
        // Fetch option data for the ticker with the OTM percentage and target expiration
        const optionData = await fetchOptionData(
            ticker, 
            otmPercentage, 
            selectedOption.optionType,
            targetExpirationForAPI
        );
        
        if (!optionData || !optionData.data || !optionData.data[ticker]) {
            throw new Error(`Failed to fetch option data for ${ticker}`);
        }
        
        // Get options based on the selected option type
        const optionType = selectedOption.optionType.toUpperCase();
        let availableOptions = [];
        
        if (optionType === 'CALL' || optionType === 'C') {
            availableOptions = optionData.data[ticker].calls || [];
        } else {
            availableOptions = optionData.data[ticker].puts || [];
        }
        
        console.log(`Found ${availableOptions.length} available ${optionType} options for ${ticker}`);
        
        // If we got options with the specific expiration, use them directly
        if (availableOptions.length > 0) {
            const firstOption = availableOptions[0];
            console.log("Found options with requested expiration:", firstOption.expiration);
            
            // Find the appropriate strike price
            // Calculate target OTM strike price based on current price and option type
            let targetStrike;
            if (optionType === 'CALL' || optionType === 'C') {
                // For calls, target is higher than current price (OTM)
                targetStrike = latestStockPrice * (1 + otmPercentage/100);
            } else {
                // For puts, target is lower than current price (OTM)
                targetStrike = latestStockPrice * (1 - otmPercentage/100);
            }
            
            // Find all strikes for the available options
            const availableStrikes = availableOptions
                .map(option => option.strike)
                .filter(strike => !isNaN(parseFloat(strike))) // Filter out invalid strikes
                .sort((a, b) => a - b);
            
            console.log("Available strikes:", availableStrikes);
            
            if (availableStrikes.length === 0) {
                throw new Error("No valid strikes found for the options");
            }
            
            // Find the closest strike to our target
            const closestStrike = availableStrikes.reduce((prev, curr) => {
                return (Math.abs(curr - targetStrike) < Math.abs(prev - targetStrike) ? curr : prev);
            });
            
            console.log("Selected strike:", closestStrike);
            
            // Get the specific option with the selected strike
            const selectedNewOption = availableOptions.find(
                option => option.strike === closestStrike
            );
            
            if (!selectedNewOption) {
                throw new Error("Could not find specific option contract for rollover");
            }
            
            console.log("Selected new option for rollover:", selectedNewOption);
            
            // Set the rollover suggestion
            rolloverSuggestions = [selectedNewOption];
            
            // Populate rollover suggestions table
            populateRolloverSuggestionsTable(rolloverSuggestions);
            return;
        }
        
        // If we couldn't get options with the specific expiration, fall back to the old method
        console.warn("No options found with requested expiration. Falling back to generic search.");
        
        // Find all available expirations
        const allExpirations = [...new Set(availableOptions.map(opt => opt.expiration))]
            .filter(expDate => {
                try {
                    const expDateTime = new Date(expDate);
                    return !isNaN(expDateTime.getTime());
                } catch (e) {
                    console.warn(`Skipping invalid expiration date: ${expDate}`);
                    return false;
                }
            })
            .sort((a, b) => {
                try {
                    return new Date(a) - new Date(b);
                } catch (e) {
                    console.warn(`Error comparing dates ${a} and ${b}`);
                    return 0;
                }
            });
        
        console.log("All available expirations:", allExpirations);
        
        if (allExpirations.length === 0) {
            throw new Error("No valid expiration dates found for rolling options");
        }
        
        // Use the first available expiration
        const nextExpiration = allExpirations[0];
        console.log("Selected next expiration:", nextExpiration);
        
        // Find all strikes for the selected expiration
        const strikesForExpiration = availableOptions
            .filter(option => {
                try {
                    return option.expiration === nextExpiration;
                } catch (e) {
                    console.warn(`Error comparing expiration dates:`, e);
                    return false;
                }
            })
            .map(option => option.strike)
            .filter(strike => !isNaN(parseFloat(strike))) // Filter out invalid strikes
            .sort((a, b) => a - b);
        
        console.log("Available strikes for next expiration:", strikesForExpiration);
        
        if (strikesForExpiration.length === 0) {
            throw new Error("No valid strikes found for the next expiration date");
        }
        
        // Calculate target OTM strike price based on current price and option type
        let targetStrike;
        if (optionType === 'CALL' || optionType === 'C') {
            // For calls, target is higher than current price (OTM)
            targetStrike = latestStockPrice * (1 + otmPercentage/100);
        } else {
            // For puts, target is lower than current price (OTM)
            targetStrike = latestStockPrice * (1 - otmPercentage/100);
        }
        
        // Find the closest strike to our target
        const closestStrike = strikesForExpiration.reduce((prev, curr) => {
            return (Math.abs(curr - targetStrike) < Math.abs(prev - targetStrike) ? curr : prev);
        });
        
        console.log("Selected strike:", closestStrike);
        
        // Get the specific option for the selected expiration and strike
        let selectedNewOption;
        try {
            selectedNewOption = availableOptions.find(
                option => option.expiration === nextExpiration && option.strike === closestStrike
            );
            
            if (!selectedNewOption) {
                // Try a more flexible search if exact match fails
                console.log("Couldn't find exact option match, trying more flexible search");
                selectedNewOption = availableOptions.find(
                    option => option.expiration === nextExpiration && 
                            Math.abs(option.strike - closestStrike) < 0.01 // Allow small difference in strike
                );
            }
            
            if (!selectedNewOption) {
                throw new Error("Could not find specific option contract for rollover");
            }
        } catch (e) {
            console.error("Error finding specific option:", e);
            throw new Error("Could not find specific option contract for rollover: " + e.message);
        }
        
        console.log("Selected new option for rollover:", selectedNewOption);
        
        // Set the rollover suggestion
        rolloverSuggestions = [selectedNewOption];
        
        // Populate rollover suggestions table
        populateRolloverSuggestionsTable(rolloverSuggestions);
    } catch (error) {
        console.error('Error fetching rollover suggestions:', error);
        
        // Ensure the OTM selector stays visible even after error
        const otmSelectorRow = document.getElementById('otm-selector-row');
        const tableBody = document.getElementById('rollover-suggestions-table-body');
        if (tableBody && otmSelectorRow && tableBody.childElementCount <= 1) {
            tableBody.innerHTML = '';
            tableBody.appendChild(otmSelectorRow);
            
            const errorRow = document.createElement('tr');
            errorRow.innerHTML = `<td colspan="11" class="text-center text-danger">Error: ${error.message}</td>`;
            tableBody.appendChild(errorRow);
        }
    }
}

// Initialize the rollover page when the DOM is loaded
document.addEventListener('DOMContentLoaded', initializeRollover);
window.addEventListener('beforeunload', () => {
    if (orderStatusTimer) clearInterval(orderStatusTimer);
});
