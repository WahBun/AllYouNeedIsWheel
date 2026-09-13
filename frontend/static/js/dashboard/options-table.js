/**
 * Options Table module for handling options display and interaction
 */
import { fetchOptionData, fetchTickers, saveOptionOrder, fetchAccountData, fetchOptionExpirations, fetchStockPrices } from './api.js?v=safety-1';
import { showAlert } from '../utils/alerts.js?v=safety-1';
import { formatCurrency, formatPercentage } from './account.js?v=safety-1';

// Store options data
let tickersData = {};
// Store portfolio summary data
let portfolioSummary = null;
// Flag to track if event listeners have been initialized
let eventListenersInitialized = false;
// Flag to track if container event listeners have been initialized
let containerEventListenersInitialized = false;
// Track custom tickers added to the put table
let customTickers = new Set();
// Flag to track if custom ticker event listeners have been initialized
let customTickerListenersInitialized = false;
// Track manual limit price edits for the currently displayed option rows
let manualLimitPrices = {};
const expirationRequests = new Map();
const EXPIRATION_CACHE_TTL_MS = 30 * 60 * 1000;
const REFRESH_CONCURRENCY = 2;

// Reference to loadPendingOrders function from orders.js
let loadPendingOrdersFunc = null;

function tr(key, replacements = {}) {
    return window.t ? window.t(key, replacements) : key;
}

function cleanupTooltips(root = document) {
    if (window.bootstrap && window.bootstrap.Tooltip && root.querySelectorAll) {
        root.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(element => {
            const tooltip = window.bootstrap.Tooltip.getInstance(element);
            if (tooltip) {
                tooltip.hide();
                tooltip.dispose();
            }
        });
    }

    document.querySelectorAll('.tooltip').forEach(tooltip => tooltip.remove());
}

function initializeTooltips(root = document) {
    if (!window.bootstrap || !window.bootstrap.Tooltip || !root.querySelectorAll) return;

    root.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(element => {
        window.bootstrap.Tooltip.getOrCreateInstance(element, {
            trigger: 'hover focus'
        });
    });
}

/**
 * Try to get the loadPendingOrders function from window or import it dynamically
 * @returns {Function|null} The loadPendingOrders function or null if not available
 */
async function getLoadPendingOrdersFunction() {
    // First check if it's available on window (global)
    if (typeof window.loadPendingOrders === 'function') {
        return window.loadPendingOrders;
    }
    
    // If not, try to get it from a custom event
    if (!loadPendingOrdersFunc) {
        try {
            // Create and dispatch a custom event to request the function
            const requestEvent = new CustomEvent('requestPendingOrdersRefresh', {
                detail: { source: 'options-table' }
            });
            document.dispatchEvent(requestEvent);
            console.log('Dispatched event requesting pending orders refresh');
        } catch (error) {
            console.error('Error trying to request pending orders refresh:', error);
        }
    }
    
    return null;
}

/**
 * Refresh the pending orders table
 */
async function refreshPendingOrders() {
    try {
        // Try multiple methods to refresh the pending orders table
        
        // Method 1: Use the global loadPendingOrders function if available
        if (typeof window.loadPendingOrders === 'function') {
            console.log('Refreshing pending orders using window.loadPendingOrders');
            await window.loadPendingOrders();
            return;
        }
        
        // Method 2: Dispatch a custom event that orders.js is listening for
        console.log('Dispatching ordersUpdated event to trigger refresh');
        const event = new CustomEvent('ordersUpdated');
        document.dispatchEvent(event);
        
        // Method 3: Try to find and click the refresh button in the DOM
        const refreshButton = document.getElementById('refresh-pending-orders');
        if (refreshButton) {
            console.log('Clicking the refresh-pending-orders button');
            refreshButton.click();
            return;
        }
        
        console.log('All pending orders refresh methods attempted');
    } catch (error) {
        console.error('Error refreshing pending orders:', error);
    }
}

function ensureTickerData(ticker) {
    if (!tickersData[ticker]) {
        tickersData[ticker] = {
            data: { data: {} },
            callOtmPercentage: 10,
            putOtmPercentage: 10,
            putQuantity: 1
        };
    }

    if (!tickersData[ticker].data) {
        tickersData[ticker].data = { data: {} };
    }

    if (!tickersData[ticker].data.data) {
        tickersData[ticker].data.data = {};
    }

    if (!tickersData[ticker].data.data[ticker]) {
        tickersData[ticker].data.data[ticker] = {
            stock_price: 0,
            position: 0,
            calls: [],
            puts: []
        };
    }

    return tickersData[ticker];
}

function getSelectedExpiration(ticker, optionType, fallback = null) {
    const tickerData = tickersData[ticker] || {};
    const key = optionType === 'CALL' ? 'callSelectedExpiration' : 'putSelectedExpiration';
    const selectedExpiration = tickerData[key] || tickerData.selectedExpiration || fallback;
    const expirations = tickerData.expirations || [];
    const selectedStillExists = expirations.length === 0 ||
        expirations.some(exp => exp.value === selectedExpiration);

    return selectedStillExists ? selectedExpiration : fallback;
}

function getDefaultExpiration(expirations) {
    if (!Array.isArray(expirations) || expirations.length === 0) return null;
    return expirations.find(expiration => expiration.is_default)?.value || expirations[0].value;
}

function setSelectedExpiration(ticker, optionType, expiration) {
    if (!expiration) return;
    const tickerData = ensureTickerData(ticker);
    const key = optionType === 'CALL' ? 'callSelectedExpiration' : 'putSelectedExpiration';
    tickerData[key] = expiration;
    tickerData.selectedExpiration = expiration;
}

function storeTickerExpirations(ticker, expirations) {
    if (!Array.isArray(expirations) || expirations.length === 0) return;
    const tickerData = ensureTickerData(ticker);
    tickerData.expirations = expirations;
    tickerData.expirationsFetchedAt = Date.now();
}

async function getTickerExpirations(ticker, force = false) {
    const tickerData = ensureTickerData(ticker);
    const hasFreshCache = (
        Array.isArray(tickerData.expirations) &&
        tickerData.expirations.length > 0 &&
        Date.now() - (tickerData.expirationsFetchedAt || 0) < EXPIRATION_CACHE_TTL_MS
    );

    if (!force && hasFreshCache) {
        return tickerData.expirations;
    }

    if (expirationRequests.has(ticker)) {
        return expirationRequests.get(ticker);
    }

    const request = fetchOptionExpirations(ticker)
        .then(expirationData => {
            const expirations = expirationData?.expirations || [];
            storeTickerExpirations(ticker, expirations);
            return expirations;
        })
        .finally(() => expirationRequests.delete(ticker));

    expirationRequests.set(ticker, request);
    return request;
}

async function runWithConcurrency(items, concurrency, worker) {
    let nextIndex = 0;
    const workerCount = Math.min(concurrency, items.length);

    await Promise.all(Array.from({ length: workerCount }, async () => {
        while (nextIndex < items.length) {
            const currentIndex = nextIndex++;
            await worker(items[currentIndex], currentIndex);
        }
    }));
}

function updateTickerOptionData(ticker, optionType, optionData) {
    if (!optionData || !optionData.data || !optionData.data[ticker]) {
        return false;
    }

    const tickerData = ensureTickerData(ticker);
    const freshData = optionData.data[ticker];
    const currentData = tickerData.data.data[ticker];

    if (freshData.stock_price !== undefined && freshData.stock_price !== null) {
        currentData.stock_price = freshData.stock_price;
    }
    if (freshData.position !== undefined && freshData.position !== null) {
        currentData.position = freshData.position;
    }

    if (optionType === 'CALL') {
        currentData.calls = freshData.calls || [];
    } else {
        currentData.puts = freshData.puts || [];
    }

    return true;
}

/**
 * Calculate premium based on bid and ask prices with proper fallbacks
 * @param {string|number} bid - Bid price
 * @param {string|number} ask - Ask price
 * @param {string|number} last - Last price (fallback)
 * @returns {number} - Calculated premium
 */
function calculatePremium(bid, ask, last) {
    // Parse all inputs to ensure they're numbers
    const bidNum = parseFloat(bid || 0);
    const askNum = parseFloat(ask || 0);
    const lastNum = parseFloat(last || 0);
    
    console.log(`Calculating premium - bid: ${bidNum}, ask: ${askNum}, last: ${lastNum}`);
    
    // Both bid and ask are valid - use midpoint
    if (bidNum > 0 && askNum > 0) {
        const midPrice = (bidNum + askNum) / 2;
        console.log(`Using mid price for premium: ${midPrice}`);
        return midPrice;
    }
    
    // Only bid is valid
    if (bidNum > 0) {
        console.log(`Only bid is valid, using: ${bidNum}`);
        return bidNum;
    }
    
    // Only ask is valid
    if (askNum > 0) {
        console.log(`Only ask is valid, using: ${askNum}`);
        return askNum;
    }
    
    // Fallback to last price
    if (lastNum > 0) {
        console.log(`Using last price as fallback: ${lastNum}`);
        return lastNum;
    }
    
    // No valid price data, return minimum
    console.log('No valid price data, using minimum 0.05');
    return 0.05;
}

function calculateSpreadPercentage(bid, ask) {
    const bidNum = parseFloat(bid || 0);
    const askNum = parseFloat(ask || 0);

    if (!Number.isFinite(bidNum) || !Number.isFinite(askNum) || bidNum <= 0 || askNum <= 0 || askNum < bidNum) {
        return null;
    }

    const mid = (bidNum + askNum) / 2;
    if (mid <= 0) return null;

    return ((askNum - bidNum) / mid) * 100;
}

function getSpreadClass(spreadPercentage) {
    if (spreadPercentage === null) return 'spread-unavailable';
    if (spreadPercentage <= 10) return 'spread-tight';
    if (spreadPercentage <= 20) return 'spread-medium';
    return 'spread-wide';
}

function formatPriceWithSpread(price, bid, ask) {
    const priceNum = parseFloat(price || 0);
    if (!Number.isFinite(priceNum) || priceNum <= 0) {
        return 'N/A';
    }

    const spreadPercentage = calculateSpreadPercentage(bid, ask);
    const spreadText = spreadPercentage === null ? 'N/A' : `${spreadPercentage.toFixed(1)}%`;
    const spreadClass = getSpreadClass(spreadPercentage);

    return `$ ${priceNum.toFixed(2)} <span class="spread-percent ${spreadClass}" title="Bid/ask spread">(${spreadText})</span>`;
}

function getOptionPriceKey(option) {
    if (!option) return '';
    const strike = Number.parseFloat(option.strike || 0).toFixed(2);
    return `${option.expiration || ''}|${strike}`;
}

function getManualLimitPrice(ticker, optionType, option) {
    const entry = manualLimitPrices[ticker]?.[optionType];
    if (!entry || entry.key !== getOptionPriceKey(option)) return null;
    const price = Number.parseFloat(entry.price);
    return Number.isFinite(price) && price > 0 ? price : null;
}

function setManualLimitPrice(ticker, optionType, option, price) {
    const priceNum = Number.parseFloat(price);
    if (!Number.isFinite(priceNum) || priceNum <= 0) return;

    if (!manualLimitPrices[ticker]) manualLimitPrices[ticker] = {};
    manualLimitPrices[ticker][optionType] = {
        key: getOptionPriceKey(option),
        price: priceNum
    };
}

function clearManualLimitPrice(ticker, optionType) {
    if (!manualLimitPrices[ticker]) return;
    delete manualLimitPrices[ticker][optionType];
    if (Object.keys(manualLimitPrices[ticker]).length === 0) {
        delete manualLimitPrices[ticker];
    }
}

function formatSpreadBadge(bid, ask) {
    const spreadPercentage = calculateSpreadPercentage(bid, ask);
    const spreadText = spreadPercentage === null ? 'N/A' : `${spreadPercentage.toFixed(1)}%`;
    const spreadClass = getSpreadClass(spreadPercentage);
    return `<span class="input-group-text spread-input-addon ${spreadClass}">(${spreadText})</span>`;
}

function buildLimitPriceControl(ticker, optionType, option, displayedPrice, defaultPrice) {
    const safeDisplayed = Number.parseFloat(displayedPrice || 0);
    const safeDefault = Number.parseFloat(defaultPrice || 0);
    const value = Number.isFinite(safeDisplayed) && safeDisplayed > 0 ? safeDisplayed : safeDefault;

    if (!Number.isFinite(value) || value <= 0) {
        return formatPriceWithSpread(defaultPrice, option.bid, option.ask);
    }

    return `
        <div class="mid-price-control">
            <div class="input-group input-group-sm">
                <span class="input-group-text">$</span>
                <input type="number"
                    class="form-control form-control-sm mid-price-input"
                    data-ticker="${ticker}"
                    data-option-type="${optionType}"
                    data-strike="${option.strike || 0}"
                    data-expiration="${option.expiration || ''}"
                    data-default-price="${safeDefault.toFixed(2)}"
                    min="0.01"
                    step="0.01"
                    value="${value.toFixed(2)}">
                <button class="btn btn-outline-secondary btn-sm reset-mid-price"
                    type="button"
                    data-bs-toggle="tooltip"
                    title="Reset to current mid">
                    <i class="bi bi-arrow-repeat"></i>
                </button>
                ${formatSpreadBadge(option.bid, option.ask)}
            </div>
        </div>
    `;
}

function getRowLimitPrice(row, fallbackPrice = 0) {
    const input = row?.querySelector('.mid-price-input');
    const price = Number.parseFloat(input?.value);
    if (Number.isFinite(price) && price > 0) return price;

    const fallback = Number.parseFloat(fallbackPrice);
    return Number.isFinite(fallback) && fallback > 0 ? fallback : 0;
}

function getOptionFromRow(row) {
    if (!row) return null;
    return {
        strike: Number.parseFloat(row.dataset.strike || 0),
        expiration: row.dataset.expiration || ''
    };
}

function getRowQuantity(row) {
    if (!row) return 1;
    const qtyInput = row.querySelector('.put-qty-input');
    if (qtyInput) {
        const qty = Number.parseInt(qtyInput.value, 10);
        return Number.isFinite(qty) && qty > 0 ? qty : 1;
    }

    const qty = Number.parseInt(row.dataset.contracts || '1', 10);
    return Number.isFinite(qty) && qty > 0 ? qty : 1;
}

function updateRowPremiumDisplay(row) {
    if (!row) return;

    const limitPrice = getRowLimitPrice(row, Number.parseFloat(row.dataset.defaultPremium || 0));
    const quantity = getRowQuantity(row);
    const strike = Number.parseFloat(row.dataset.strike || 0);
    row.dataset.premium = (limitPrice * 100).toString();

    const totalPremiumCell = row.querySelector('.total-premium');
    if (totalPremiumCell) {
        totalPremiumCell.textContent = formatCurrency(limitPrice * 100 * quantity);
    }

    const cashRequiredCell = row.querySelector('.cash-required');
    if (cashRequiredCell) {
        cashRequiredCell.textContent = formatCurrency(strike * 100 * quantity);
    }
}

/**
 * Calculate the Out of The Money percentage
 * @param {number} strikePrice - The option strike price
 * @param {number} currentPrice - The current stock price
 * @returns {number} The OTM percentage
 */
function calculateOTMPercentage(strikePrice, currentPrice) {
    if (!strikePrice || !currentPrice) return 0;
    
    const diff = strikePrice - currentPrice;
    return (diff / currentPrice) * 100;
}

/**
 * Calculate recommended put options quantity based on portfolio data
 * @param {number} stockPrice - Current stock price
 * @param {number} putStrike - Put option strike price
 * @param {string} ticker - The ticker symbol
 * @returns {Object} Recommended quantity and explanation
 */
function calculateRecommendedPutQuantity(stockPrice, putStrike, ticker) {
    // Default recommendation if we can't calculate
    const defaultRecommendation = {
        quantity: 1,
        explanation: "Default recommendation"
    };
    
    // If we don't have portfolio data, return default
    if (!portfolioSummary || !stockPrice || !putStrike) {
        return defaultRecommendation;
    }
    
    try {
        // Get cash balance and total portfolio value
        const cashBalance = portfolioSummary.cash_balance || 0;
        const totalPortfolioValue = portfolioSummary.account_value || 0;
        
        // Get number of unique tickers (for diversification)
        const totalStocks = Object.keys(tickersData).length || 1;
        
        // Calculate maximum allocation per stock (200% of cash balance / number of stocks)
        const maxAllocationPerStock = (2.0 * cashBalance) / totalStocks;
        
        // Calculate how many contracts that would allow (each contract = 100 shares)
        const potentialContracts = Math.floor(maxAllocationPerStock / (putStrike * 100));
        
        // Limit to a reasonable number based on portfolio size
        const maxContracts = Math.min(potentialContracts, 10);
        const recommendedQuantity = Math.max(1, maxContracts);
        
        return {
            quantity: recommendedQuantity,
            explanation: `Based on cash: ${formatCurrency(cashBalance)}, diversification across ${totalStocks} stocks`
        };
    } catch (error) {
        console.error("Error calculating recommended put quantity:", error);
        return defaultRecommendation;
    }
}

/**
 * Calculate earnings summary based on current options data
 * @returns {Object} Summary of earnings
 */
function calculateEarningsSummary() {
    const summary = {
        totalWeeklyCallPremium: 0,
        totalWeeklyPutPremium: 0,
        totalWeeklyPremium: 0,
        portfolioValue: 0,
        projectedAnnualEarnings: 0,
        projectedAnnualReturn: 0,
        weeklyReturn: 0,
        totalPutExerciseCost: 0,
        cashBalance: portfolioSummary ? portfolioSummary.cash_balance || 0 : 0
    };
    
    // Process each ticker to get total premium earnings
    Object.values(tickersData).forEach(tickerData => {
        if (!tickerData || !tickerData.data || !tickerData.data.data) {
            console.log("Skipping ticker with invalid data structure", tickerData);
            return;
        }
        
        // Process each ticker's option data
        Object.values(tickerData.data.data).forEach(optionData => {
            // Get position information (number of shares owned)
            const sharesOwned = optionData.position || 0;
            const ticker = optionData.symbol || Object.keys(tickerData.data.data)[0];
            const isCustomTicker = customTickers.has(ticker);
            
            // Skip positions with less than 100 shares for calls (minimum for 1 option contract)
            // But include all custom tickers for put calculations regardless of shares owned
            if (sharesOwned < 100 && !isCustomTicker) {
                console.log(`Skipping position with ${sharesOwned} shares (less than 100) and not a custom ticker`);
                return; // Skip this position in earnings calculation
            }
            
            // Add portfolio value from stock positions
            const stockPrice = optionData.stock_price || 0;
            summary.portfolioValue += sharesOwned * stockPrice;
            
            // Calculate max contracts based on shares owned
            const maxCallContracts = Math.floor(sharesOwned / 100);
            
            // Process call options (only for positions with enough shares)
            if (sharesOwned >= 100 && optionData.calls && optionData.calls.length > 0) {
                const callOption = optionData.calls[0];
                if (callOption) {
                    const callLimitPrice = getManualLimitPrice(ticker, 'CALL', callOption) ??
                        calculatePremium(callOption.bid, callOption.ask, callOption.last);
                    const callPremiumPerContract = callLimitPrice * 100;
                    const totalCallPremium = callPremiumPerContract * maxCallContracts;
                    summary.totalWeeklyCallPremium += totalCallPremium;
                }
            }
            
            // Process put options for both regular positions and custom tickers
            if ((sharesOwned >= 100 || isCustomTicker) && optionData.puts && optionData.puts.length > 0) {
                const putOption = optionData.puts[0];
                if (putOption) {
                    const putLimitPrice = getManualLimitPrice(ticker, 'PUT', putOption) ??
                        calculatePremium(putOption.bid, putOption.ask, putOption.last);
                    const putPremiumPerContract = putLimitPrice * 100;
                    
                    // Use custom put quantity if available, otherwise calculate based on shares
                    const customPutQuantity = tickerData.putQuantity || 
                                             (sharesOwned >= 100 ? Math.floor(sharesOwned / 100) : 1);
                    
                    const totalPutPremium = putPremiumPerContract * customPutQuantity;
                    summary.totalWeeklyPutPremium += totalPutPremium;
                
                    // Calculate total exercise cost
                    const putExerciseCost = putOption.strike * customPutQuantity * 100;
                    summary.totalPutExerciseCost += putExerciseCost;
                }
            }
        });
    });
    
    // Calculate total weekly premium
    summary.totalWeeklyPremium = summary.totalWeeklyCallPremium + summary.totalWeeklyPutPremium;
    
    // Get portfolio value from portfolioSummary first (most accurate source)
    let totalPortfolioValue = 0;
    
    if (portfolioSummary) {
        // Use the account_value field if available, which should include both stock value and cash
        totalPortfolioValue = portfolioSummary.account_value || 0;
        
        if (totalPortfolioValue === 0) {
            // If account_value is not available, try to calculate from stock value and cash balance
            const stockValue = portfolioSummary.stock_value || 0;
            const cashBalance = portfolioSummary.cash_balance || 0;
            totalPortfolioValue = stockValue + cashBalance;
            
            // Store these values in summary for display
            summary.portfolioValue = stockValue;
            summary.cashBalance = cashBalance;
        } else {
            // If we have account_value, still try to get the breakdown for display purposes
            summary.portfolioValue = portfolioSummary.stock_value || 0;
            summary.cashBalance = portfolioSummary.cash_balance || 0;
        }
    }
    
    // Fallback to window.portfolioData if portfolioSummary didn't provide values
    if (totalPortfolioValue === 0 && window.portfolioData) {
        summary.portfolioValue = window.portfolioData.stockValue || 0;
        summary.cashBalance = window.portfolioData.cashBalance || 0;
        totalPortfolioValue = summary.portfolioValue + summary.cashBalance;
    }
    
    console.log("Portfolio values:", {
        fromSummary: portfolioSummary ? portfolioSummary.account_value : 'N/A',
        calculatedTotal: totalPortfolioValue,
        stockValue: summary.portfolioValue,
        cashBalance: summary.cashBalance
    });
    
    // Calculate weekly return percentage against total portfolio value
    if (totalPortfolioValue > 0) {
        summary.weeklyReturn = (summary.totalWeeklyPremium / totalPortfolioValue) * 100;
        
        // Calculate projected annual earnings (Weekly premium * 52 weeks)
    summary.projectedAnnualEarnings = summary.totalWeeklyPremium * 52;
    
        // Calculate projected annual return as annual income divided by portfolio value
        summary.projectedAnnualReturn = (summary.projectedAnnualEarnings / totalPortfolioValue) * 100;
        
        // Log values for debugging
        console.log("Annual return calculation:", {
            annualEarnings: summary.projectedAnnualEarnings,
            portfolioValue: totalPortfolioValue,
            weeklyReturn: summary.weeklyReturn,
            annualReturn: summary.projectedAnnualReturn
        });
    } else {
        // Calculate projected annual earnings even if portfolio value is zero
        summary.projectedAnnualEarnings = summary.totalWeeklyPremium * 52;
    }
    
    console.log("Earnings summary:", summary);
    
    return summary;
}

/**
 * Update options table with data from stock positions
 */
function updateOptionsTable() {
    console.log("Updating options table with data:", tickersData);
    
    const optionsTableContainer = document.getElementById('options-table-container');
    if (!optionsTableContainer) {
        console.error("Options table container not found in the DOM");
        return;
    }
    
    // Remember which tab was active before rebuilding the UI
    const putTabWasActive = document.querySelector('#put-options-tab.active') !== null ||
                           document.querySelector('#put-options-section.active') !== null;
    console.log("Put tab was active before update:", putTabWasActive);
    
    cleanupTooltips(optionsTableContainer);

    // Clear existing tables
    optionsTableContainer.innerHTML = '';
    
    // Get tickers
    const tickers = Object.keys(tickersData);
    
    if (tickers.length === 0) {
        console.log("No tickers found");
        optionsTableContainer.innerHTML = `<div class="alert alert-info">${tr('options.noStockPositions')}</div>`;
        return;
    }
    
    console.log("Found ticker data for:", tickers.join(", "));
    
    // Keep track of tickers with sufficient shares
    let sufficientSharesCount = 0;
    let insufficientSharesCount = 0;
    let filteredTickers = [];
    let visibleTickers = [];
    
    // First pass: Pre-filter tickers with insufficient shares for calls only
    const eligibleTickers = tickers.filter(ticker => {
        const tickerData = tickersData[ticker];
        
        // Skip tickers without data
        if (!tickerData || !tickerData.data || !tickerData.data.data || !tickerData.data.data[ticker]) {
            console.log(`Ticker ${ticker} has no data or invalid data structure:`, tickerData);
            return true; // Keep to show "No data available" message
        }
        
        // Check shares
        const optionData = tickerData.data.data[ticker];
        const sharesOwned = optionData.position || 0;
        
        console.log(`Ticker ${ticker} has ${sharesOwned} shares`);
        
        // For call options, we need at least 100 shares
        if (!customTickers.has(ticker) && sharesOwned < 100) {
            console.log(`${ticker} has ${sharesOwned} shares, less than required for selling options`);
            insufficientSharesCount++;
            return customTickers.has(ticker); // Keep custom tickers regardless of shares
        }
        
        sufficientSharesCount++;
        return true;
    });
    
    // Create tabs for call and put options
    const tabsHTML = `
        <ul class="nav nav-tabs mb-3" id="options-tabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link ${putTabWasActive ? '' : 'active'}" id="call-options-tab" data-bs-toggle="tab" data-bs-target="#call-options-section" type="button" role="tab" aria-controls="call-options-section" aria-selected="${putTabWasActive ? 'false' : 'true'}">
                    ${tr('options.coveredCalls')}
                </button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link ${putTabWasActive ? 'active' : ''}" id="put-options-tab" data-bs-toggle="tab" data-bs-target="#put-options-section" type="button" role="tab" aria-controls="put-options-section" aria-selected="${putTabWasActive ? 'true' : 'false'}">
                    ${tr('options.cashSecuredPuts')}
                </button>
            </li>
        </ul>
        
        <div class="tab-content" id="options-tabs-content">
            <div class="tab-pane fade ${putTabWasActive ? '' : 'show active'}" id="call-options-section" role="tabpanel" aria-labelledby="call-options-tab">
                <div class="options-toolbar justify-content-end mb-2">
                    <button class="btn btn-sm btn-outline-success me-2" id="sell-all-calls">
                        <i class="bi bi-check2-all"></i> ${tr('common.addAll')}
                    </button>
                    <button class="btn btn-sm btn-outline-primary" id="refresh-all-calls">
                        <i class="bi bi-arrow-repeat"></i> ${tr('options.refreshAllCalls')}
                    </button>
                </div>
                <div class="table-responsive">
                    <table class="table table-striped table-hover table-sm options-opportunities-table" id="call-options-table">
                        <thead>
                            <tr>
                                <th>${tr('common.ticker')}</th>
                                <th>${tr('common.shares')}</th>
                                <th>${tr('options.stockPrice')}</th>
                                <th>${tr('options.otm')}</th>
                                <th>${tr('common.strike')}</th>
                                <th>${tr('common.expiration')}</th>
                                <th>${tr('options.midPrice')}</th>
                                <th>${tr('common.delta')}</th>
                                <th>${tr('common.iv')}</th>
                                <th>${tr('common.qty')}</th>
                                <th>${tr('options.totalPremium')}</th>
                                <th>${tr('common.action')}</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
            
            <div class="tab-pane fade ${putTabWasActive ? 'show active' : ''}" id="put-options-section" role="tabpanel" aria-labelledby="put-options-tab">
                <div class="options-toolbar justify-content-between mb-2">
                    <div class="option-search">
                        <div class="input-group input-group-sm">
                            <input type="text" class="form-control" id="custom-ticker-input" 
                                placeholder="${tr('options.addTickerPlaceholder')}" maxlength="5">
                            <button class="btn btn-outline-primary" id="add-custom-ticker">
                                <i class="bi bi-plus-circle"></i> ${tr('common.add')}
                            </button>
                        </div>
                    </div>
                    <div class="options-toolbar-actions">
                    <button class="btn btn-sm btn-outline-success me-2" id="sell-all-puts">
                        <i class="bi bi-check2-all"></i> ${tr('common.addAll')}
                    </button>
                    <button class="btn btn-sm btn-outline-primary" id="refresh-all-puts">
                        <i class="bi bi-arrow-repeat"></i> ${tr('options.refreshAllPuts')}
                    </button>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-striped table-hover table-sm options-opportunities-table" id="put-options-table">
                        <thead>
                            <tr>
                                <th>${tr('common.ticker')}</th>
                                <th>${tr('options.stockPrice')}</th>
                                <th>${tr('options.otm')}</th>
                                <th>${tr('common.strike')}</th>
                                <th>${tr('common.expiration')}</th>
                                <th>${tr('options.midPrice')}</th>
                                <th>${tr('common.delta')}</th>
                                <th>${tr('common.iv')}</th>
                                <th>${tr('common.qty')}</th>
                                <th>${tr('options.totalPremium')}</th>
                                <th>${tr('options.cashRequired')}</th>
                                <th>${tr('common.action')}</th>
                            </tr>
                        </thead>
                        <tbody></tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
    
    // Add the tabs and tables to the container
    optionsTableContainer.innerHTML = tabsHTML;
    
    // Build the tables with our buildOptionsTable function
    buildOptionsTable('call-options-table', 'CALL');
    buildOptionsTable('put-options-table', 'PUT');
    
    // Calculate and display earnings summary
    const earningsSummary = calculateEarningsSummary();
    displayEarningsSummary(earningsSummary);
    
    // Set up event listeners for custom ticker form
    setupCustomTickerEventListeners();
    
    // Set up event listeners for put quantity inputs
    addPutQtyInputEventListeners();
    addMidPriceInputEventListeners();

    initializeTooltips(optionsTableContainer);
}

/**
 * Add event listeners to the options table
 */
function addOptionsTableEventListeners() {
    // Get the container
    const container = document.getElementById('options-table-container');
    if (!container) return;
    
    // Initialize Bootstrap tabs if Bootstrap JS is available
    if (typeof bootstrap !== 'undefined') {
        const tabEls = document.querySelectorAll('#options-tabs button[data-bs-toggle="tab"]');
        tabEls.forEach(tabEl => {
            const tab = new bootstrap.Tab(tabEl);
            
            tabEl.addEventListener('click', event => {
                event.preventDefault();
                tab.show();
                console.log(`Tab ${tabEl.id} activated via Bootstrap Tab`);
        });
    });
    
        console.log('Bootstrap tabs initialized');
    } else {
        console.log('Bootstrap JS not available, using fallback tab switching');
        
        // Fallback tab switching (manual)
        const callTab = document.getElementById('call-options-tab');
        const putTab = document.getElementById('put-options-tab');
        const callSection = document.getElementById('call-options-section');
        const putSection = document.getElementById('put-options-section');
        
        if (callTab && putTab && callSection && putSection) {
            callTab.addEventListener('click', (e) => {
                e.preventDefault();
                callTab.classList.add('active');
                putTab.classList.remove('active');
                callSection.classList.add('show', 'active');
                putSection.classList.remove('show', 'active');
                console.log('Switched to call options tab (fallback)');
            });
            
            putTab.addEventListener('click', (e) => {
                e.preventDefault();
                callTab.classList.remove('active');
                putTab.classList.add('active');
                callSection.classList.remove('show', 'active');
                putSection.classList.add('show', 'active');
                console.log('Switched to put options tab (fallback)');
            });
        }
    }
    
    // Set up container event delegation if not already set up
    if (!containerEventListenersInitialized) {
        console.log('Initializing container event delegation');
    
    // Add event delegation for all buttons in the container
    container.addEventListener('click', async (event) => {
        // Handle refresh button click
            if (event.target.classList.contains('refresh-option') || 
                event.target.closest('.refresh-option')) {
            
                const button = event.target.classList.contains('refresh-option') ? 
                           event.target : 
                               event.target.closest('.refresh-option');
            
            const ticker = button.dataset.ticker;
                const optionType = button.dataset.type; // Get the option type (CALL or PUT)
                
            if (ticker) {
                button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${tr('common.loading')}`;
                button.disabled = true;
                
                try {
                        if (optionType) {
                            // If we have an option type, refresh just that type
                            await refreshOptionsForTickerByType(ticker, optionType, true);
                        } else {
                            // Otherwise refresh all options for this ticker
                            await refreshOptionsForTicker(ticker, true);
                        }
                        button.innerHTML = '<i class="bi bi-arrow-repeat"></i>';
                } catch (error) {
                    console.error('Error refreshing ticker:', error);
                } finally {
                    button.disabled = false;
                }
            }
        }
        
        // Handle OTM% refresh button click
        if (event.target.classList.contains('refresh-otm') || 
            event.target.closest('.refresh-otm')) {
            
            const button = event.target.classList.contains('refresh-otm') ? 
                           event.target : 
                           event.target.closest('.refresh-otm');
            
            const ticker = button.dataset.ticker;
            if (ticker) {
                button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
                button.disabled = true;
                
                try {
                    // Find the related input element
                    const inputGroup = button.closest('.input-group');
                    const otmInput = inputGroup.querySelector('.otm-input');
                    const otmPercentage = parseInt(otmInput.value, 10);
                    const optionType = otmInput.dataset.optionType || 'CALL'; // Get option type from data attribute
                    
                    // Find the selected expiration from the dropdown in the same row
                    const row = button.closest('tr');
                    let selectedExpiration = null;
                    if (row) {
                        const expirationSelect = row.querySelector('.expiration-select');
                        if (expirationSelect) {
                            selectedExpiration = expirationSelect.value;
                            console.log(`Using selected expiration: ${selectedExpiration} for ${ticker}`);
                        }
                    }
                    
                    // Update ticker's OTM percentage based on option type
                    if (tickersData[ticker]) {
                        if (optionType === 'CALL') {
                            tickersData[ticker].callOtmPercentage = otmPercentage;
                            console.log(`Updated ${ticker} call OTM% to ${otmPercentage}`);
                        } else {
                            tickersData[ticker].putOtmPercentage = otmPercentage;
                            console.log(`Updated ${ticker} put OTM% to ${otmPercentage}`);
                        }
                        
                        // Save OTM settings to localStorage
                        saveOtmSettings();

                        // Save the selected expiration to use for the API call
                        if (selectedExpiration) {
                            setSelectedExpiration(ticker, optionType, selectedExpiration);
                        }
                    }

                    // Refresh options with the new OTM percentage and selected expiration
                    if (selectedExpiration) {
                        // Fetch fresh data with the selected expiration
                        const optionData = await fetchOptionData(ticker, otmPercentage, optionType, selectedExpiration);

                        if (updateTickerOptionData(ticker, optionType, optionData)) {
                            // Update the UI
                            updateOptionsTable();
                            addOptionsTableEventListeners();
                        }
                    } else {
                        // If no expiration is selected, use the normal refresh function
                        await refreshOptionsForTickerByType(ticker, optionType, true);
                    }
                } catch (error) {
                    console.error(`Error refreshing ${ticker} with new OTM%:`, error);
                } finally {
                    button.innerHTML = '<i class="bi bi-arrow-repeat"></i>';
                    button.disabled = false;
                }
            }
        }
        
        // Handle sell option button click
        if (event.target.classList.contains('sell-option') || 
            event.target.closest('.sell-option')) {
            
            const button = event.target.classList.contains('sell-option') ? 
                           event.target : 
                           event.target.closest('.sell-option');
            
            // Prevent duplicate clicks
            if (button.disabled) {
                console.log('Button already clicked, ignoring');
                return;
            }
            
            const ticker = button.dataset.ticker;
            const optionType = button.dataset.optionType;
            const strike = button.dataset.strike;
            const expiration = button.dataset.expiration;
            
            if (ticker && optionType && strike && expiration) {
                const row = button.closest('tr');
                const defaultPremium = calculatePremium(button.dataset.bid, button.dataset.ask, button.dataset.last);
                const limitPrice = getRowLimitPrice(row, defaultPremium);

                // Create order data
                const orderData = {
                    ticker: ticker,
                    option_type: optionType,
                    strike: parseFloat(strike),
                    expiration: expiration,
                    action: 'SELL',
                    quantity: optionType === 'CALL' ? 
                        Math.floor(tickersData[ticker]?.data?.data?.[ticker]?.position / 100) || 1 :
                            (tickersData[ticker]?.putQuantity || 1),
                    // Include all price fields with proper fallbacks
                    bid: parseFloat(button.dataset.bid || 0),
                    ask: parseFloat(button.dataset.ask || 0),
                    last: parseFloat(button.dataset.last || 0),
                    premium: limitPrice,
                    delta: parseFloat(button.dataset.delta || 0),
                    gamma: parseFloat(button.dataset.gamma || 0),
                    theta: parseFloat(button.dataset.theta || 0),
                    vega: parseFloat(button.dataset.vega || 0),
                    implied_volatility: parseFloat(button.dataset.implied_volatility || 0),
                    // Add timestamp
                    timestamp: new Date().toISOString(),
                    // Add market data reference
                    stock_price: tickersData[ticker]?.data?.data?.[ticker]?.stock_price || 0
                };
                
                // Safety check for critical price fields
                if (orderData.bid <= 0 && button.closest('tr')) {
                    // Try to get data from the table row
                    const bidCell = row.querySelector('td[data-field="bid"]');
                    const askCell = row.querySelector('td[data-field="ask"]');
                    const lastCell = row.querySelector('td[data-field="last"]');
                    
                    if (bidCell) orderData.bid = parseFloat(bidCell.textContent) || orderData.bid;
                    if (askCell) orderData.ask = parseFloat(askCell.textContent) || orderData.ask;
                    if (lastCell) orderData.last = parseFloat(lastCell.textContent) || orderData.last;
                    
                    console.log(`Updated order price fields from table row - bid: ${orderData.bid}, ask: ${orderData.ask}, last: ${orderData.last}`);
                }
                
                // Final sanity check - ensure we have some price reference
                if (orderData.bid <= 0 && orderData.ask <= 0 && orderData.last <= 0 && orderData.premium <= 0) {
                    console.warn('No valid price information for order - using fallback minimum price');
                    // Use 1% of strike as a minimum
                    orderData.premium = Math.max(orderData.strike * 0.01, 0.05);
                }
                
                console.log('Submitting order with data:', orderData);
                
                try {
                    // Proceed directly without confirmation dialog
                    button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
                    button.disabled = true;
                    
                    // Save the order
                    const result = await saveOptionOrder(orderData);
                    
                    if (result && result.order_id) {
                        console.log(`Order saved successfully! Order ID: ${result.order_id}`);
                            // Trigger refresh of the pending orders table
                            await refreshPendingOrders();
                    } else {
                        console.error('Failed to save order');
        }
    } catch (error) {
                    console.error('Error saving order:', error);
                } finally {
                    button.innerHTML = tr('common.add');
                    button.disabled = false;
                }
            }
        }
            
            // Handle sell all calls button click using event delegation
            if (event.target.id === 'sell-all-calls' || 
                event.target.closest('#sell-all-calls')) {
                
                const button = event.target.id === 'sell-all-calls' ? 
                               event.target : 
                               event.target.closest('#sell-all-calls');
                
                // Prevent duplicate clicks
                if (button.disabled) {
                    console.log('Button already clicked, ignoring');
                    return;
                }
                
                console.log('Add all calls button clicked via delegation');
                try {
                    await sellAllOptions('CALL');
                    // Note: Button state and alerts are handled inside sellAllOptions
                } catch (error) {
                    console.error('Error in sell all calls handler:', error);
                }
            }
            
            // Handle sell all puts button click using event delegation
            if (event.target.id === 'sell-all-puts' || 
                event.target.closest('#sell-all-puts')) {
                
                const button = event.target.id === 'sell-all-puts' ? 
                               event.target : 
                               event.target.closest('#sell-all-puts');
                
                // Prevent duplicate clicks
                if (button.disabled) {
                    console.log('Button already clicked, ignoring');
                    return;
                }
                
                console.log('Add all puts button clicked via delegation');
                try {
                    await sellAllOptions('PUT');
                    // Note: Button state and alerts are handled inside sellAllOptions
                } catch (error) {
                    console.error('Error in sell all puts handler:', error);
                }
            }
            
            // Handle refresh all options button click using event delegation
            if (event.target.id === 'refresh-all-options' || 
                event.target.closest('#refresh-all-options')) {
                
                const button = event.target.id === 'refresh-all-options' ? 
                               event.target : 
                               event.target.closest('#refresh-all-options');
                
                // Prevent duplicate clicks
                if (button.disabled) {
                    console.log('Button already clicked, ignoring');
                    return;
                }
                
                console.log('Refresh all options button clicked via delegation');
                button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${tr('common.loading')}`;
                button.disabled = true;
                
                try {
                    await refreshAllOptions();
                } catch (error) {
                    console.error('Error refreshing all options:', error);
                } finally {
                    button.innerHTML = `<i class="bi bi-arrow-repeat"></i> ${tr('common.refresh')}`;
                    button.disabled = false;
                }
            }
            
            // Handle refresh all calls button click using event delegation
            if (event.target.id === 'refresh-all-calls' || 
                event.target.closest('#refresh-all-calls')) {
                
                const button = event.target.id === 'refresh-all-calls' ? 
                               event.target : 
                               event.target.closest('#refresh-all-calls');
                
                // Prevent duplicate clicks
                if (button.disabled) {
                    console.log('Button already clicked, ignoring');
                    return;
                }
                
                console.log('Refresh all calls button clicked via delegation');
                button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${tr('common.loading')}`;
                button.disabled = true;
                
                try {
                    await refreshAllOptions('CALL');
                } catch (error) {
                    console.error('Error refreshing all call options:', error);
                } finally {
                    button.innerHTML = `<i class="bi bi-arrow-repeat"></i> ${tr('options.refreshAllCalls')}`;
                    button.disabled = false;
                }
            }
            
            // Handle refresh all puts button click using event delegation
            if (event.target.id === 'refresh-all-puts' || 
                event.target.closest('#refresh-all-puts')) {
                
                const button = event.target.id === 'refresh-all-puts' ? 
                               event.target : 
                               event.target.closest('#refresh-all-puts');
                
                // Prevent duplicate clicks
                if (button.disabled) {
                    console.log('Button already clicked, ignoring');
                    return;
                }
                
                console.log('Refresh all puts button clicked via delegation');
                button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${tr('common.loading')}`;
                button.disabled = true;
                
                try {
                    await refreshAllOptions('PUT');
                } catch (error) {
                    console.error('Error refreshing all put options:', error);
                } finally {
                    button.innerHTML = `<i class="bi bi-arrow-repeat"></i> ${tr('options.refreshAllPuts')}`;
                    button.disabled = false;
                }
            }
            
            // Handle delete ticker button click
            if (event.target.classList.contains('delete-ticker') || 
                event.target.closest('.delete-ticker')) {
                
                const button = event.target.classList.contains('delete-ticker') ? 
                               event.target : 
                               event.target.closest('.delete-ticker');
                
                const ticker = button.dataset.ticker;
                if (ticker) {
                    console.log(`Delete ticker button clicked for ${ticker}`);
                    cleanupTooltips(button.closest('tr') || document);
                    removeTicker(ticker);
                }
            }
        });
        
        // Mark container event listeners as initialized
        containerEventListenersInitialized = true;
        console.log('Container event delegation initialized');
    }
    
    // Check if individual button event listeners are already initialized
    if (eventListenersInitialized) {
        console.log('Button event listeners already initialized, skipping');
        addOtmInputEventListeners();
        addExpirationSelectEventListeners();
        return;
    }
    
    console.log('Initializing individual button event listeners');
    
    // Register dedicated listeners for the various buttons
    
    // Refresh all button - REMOVED this button from UI, but keeping code with null check
    // for backward compatibility
    const refreshAllButton = document.getElementById('refresh-all-options');
    if (refreshAllButton) {
        refreshAllButton.addEventListener('click', async () => {
            refreshAllButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${tr('common.loading')}`;
            refreshAllButton.disabled = true;
            
            try {
                await refreshAllOptions();
    } catch (error) {
                console.error('Error refreshing all options:', error);
            } finally {
                refreshAllButton.innerHTML = `<i class="bi bi-arrow-repeat"></i> ${tr('common.refresh')}`;
                refreshAllButton.disabled = false;
            }
        });
    }

    // Refresh all calls button
    const refreshAllCallsButton = document.getElementById('refresh-all-calls');
    if (refreshAllCallsButton) {
        refreshAllCallsButton.addEventListener('click', async () => {
            refreshAllCallsButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${tr('common.loading')}`;
            refreshAllCallsButton.disabled = true;
            
            try {
                await refreshAllOptions('CALL');
            } catch (error) {
                console.error('Error refreshing all call options:', error);
            } finally {
                refreshAllCallsButton.innerHTML = `<i class="bi bi-arrow-repeat"></i> ${tr('options.refreshAllCalls')}`;
                refreshAllCallsButton.disabled = false;
            }
        });
    }

    // Refresh all puts button
    const refreshAllPutsButton = document.getElementById('refresh-all-puts');
    if (refreshAllPutsButton) {
        refreshAllPutsButton.addEventListener('click', async () => {
            refreshAllPutsButton.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${tr('common.loading')}`;
            refreshAllPutsButton.disabled = true;
            
            try {
                await refreshAllOptions('PUT');
        } catch (error) {
                console.error('Error refreshing all put options:', error);
            } finally {
                refreshAllPutsButton.innerHTML = `<i class="bi bi-arrow-repeat"></i> ${tr('options.refreshAllPuts')}`;
                refreshAllPutsButton.disabled = false;
            }
        });
    }
    
    // Note: We're removing direct event listeners for sell-all buttons
    // and using event delegation instead (defined above in the container click handler)
    
    // Mark the event listeners as initialized
    eventListenersInitialized = true;
    console.log('Individual button event listeners initialization complete');
    
    // Add input event listeners for OTM% inputs - these need to be added each time
    addOtmInputEventListeners();

    addExpirationSelectEventListeners();
}

function addExpirationSelectEventListeners() {
    const expirationSelects = document.querySelectorAll('.expiration-select');
    expirationSelects.forEach(select => {
        if (select.dataset.expirationListenerAttached === 'true') return;
        select.dataset.expirationListenerAttached = 'true';

        select.addEventListener('change', async function() {
            const ticker = this.getAttribute('data-ticker');
            const optionType = this.getAttribute('data-option-type');
            const selectedExpiration = this.value;
            
            console.log(`Expiration changed for ${ticker} ${optionType} to ${selectedExpiration}`);
            setSelectedExpiration(ticker, optionType, selectedExpiration);
            
            try {
                // Show loading indicator on the row
                const row = this.closest('tr');
                const cells = row.querySelectorAll('td');
                cells.forEach(cell => {
                    if (!cell.querySelector('select') && !cell.querySelector('input')) {
                        cell.innerHTML = '<div class="spinner-border spinner-border-sm text-secondary" role="status"></div>';
                    }
                });
                
                // Get OTM percentage
                const otmPercentage = optionType === 'CALL' 
                    ? tickersData[ticker]?.callOtmPercentage || 10 
                    : tickersData[ticker]?.putOtmPercentage || 10;
                
                // Fetch new option data with the selected expiration
                const optionData = await fetchOptionData(ticker, otmPercentage, optionType, selectedExpiration);
                
                if (updateTickerOptionData(ticker, optionType, optionData)) {
                    // Update the UI
                    updateOptionsTable();
                    
                    // Add event listeners again
                    addOptionsTableEventListeners();
                }
            } catch (error) {
                console.error(`Error updating options for new expiration: ${error.message}`);
                showAlert(`Error updating options: ${error.message}`, 'danger');
                
                // Refresh the table to restore original state
                updateOptionsTable();
                addOptionsTableEventListeners();
            }
        });
    });
}

/**
 * Add event listeners for OTM% inputs - these need to be added each time
 * the table is updated
 */
function addOtmInputEventListeners() {
    document.querySelectorAll('.otm-input').forEach(input => {
        if (input.dataset.otmListenerAttached === 'true') return;
        input.dataset.otmListenerAttached = 'true';

        input.addEventListener('change', function() {
            const ticker = this.dataset.ticker;
            const otmPercentage = parseInt(this.value, 10);
            const optionType = this.dataset.optionType || 'CALL'; // Get option type from data attribute
            
            // Update ticker's OTM percentage based on option type
            if (tickersData[ticker]) {
                if (optionType === 'CALL') {
                    tickersData[ticker].callOtmPercentage = otmPercentage;
                    console.log(`Updated ${ticker} call OTM% to ${otmPercentage}`);
                } else {
                    tickersData[ticker].putOtmPercentage = otmPercentage;
                    console.log(`Updated ${ticker} put OTM% to ${otmPercentage}`);
                }
                
                // Save OTM settings to localStorage
                saveOtmSettings();
            }
        });
    });
}

/**
 * Save OTM settings for all tickers to localStorage
 */
function saveOtmSettings() {
    try {
        const otmSettings = {};
        Object.keys(tickersData).forEach(ticker => {
            otmSettings[ticker] = {
                callOtmPercentage: tickersData[ticker].callOtmPercentage || 10,
                putOtmPercentage: tickersData[ticker].putOtmPercentage || 10,
                putQuantity: tickersData[ticker].putQuantity || 1
            };
        });
        
        localStorage.setItem('otmSettings', JSON.stringify(otmSettings));
        console.log('Saved OTM settings to localStorage:', otmSettings);
    } catch (error) {
        console.error('Error saving OTM settings:', error);
    }
}

/**
 * Add event listeners for put quantity inputs - these need to be added each time
 * the table is updated
 */
function addPutQtyInputEventListeners() {
    document.querySelectorAll('.put-qty-input').forEach(input => {
        if (input.dataset.putQtyListenerAttached === 'true') return;
        input.dataset.putQtyListenerAttached = 'true';

        input.addEventListener('change', function() {
            const ticker = this.dataset.ticker;
            const newQty = parseInt(this.value, 10);
            
            // Update ticker's putQuantity for persistence
            if (tickersData[ticker]) {
                tickersData[ticker].putQuantity = newQty;
                console.log(`Updated ${ticker} put quantity to ${newQty}`);
                
                // Save OTM settings to localStorage
                saveOtmSettings();
            }
            
            // Update the rest of the row
            const row = this.closest('tr');
            if (row) {
                row.dataset.contracts = newQty;
                const premiumPerContract = parseFloat(row.dataset.premium) || 0;
                const strike = parseFloat(row.dataset.strike) || 0;
                
                // Recalculate values
                const totalPremium = premiumPerContract * newQty;
                const cashRequired = strike * 100 * newQty;
                
                // Update cells
                const totalPremiumCell = row.querySelector('.total-premium');
                const cashRequiredCell = row.querySelector('.cash-required');
                
                if (totalPremiumCell) totalPremiumCell.textContent = formatCurrency(totalPremium);
                if (cashRequiredCell) cashRequiredCell.textContent = formatCurrency(cashRequired);
                
                // Also update the earnings summary since total premiums changed
                updateEarningsSummary();
            }
        });
    });
}

function addMidPriceInputEventListeners() {
    document.querySelectorAll('.mid-price-input').forEach(input => {
        if (input.dataset.midPriceListenerAttached === 'true') return;
        input.dataset.midPriceListenerAttached = 'true';

        const applyManualPrice = function() {
            const row = this.closest('tr');
            const ticker = this.dataset.ticker;
            const optionType = this.dataset.optionType;
            const price = Number.parseFloat(this.value);

            if (!row || !ticker || !optionType || !Number.isFinite(price) || price <= 0) {
                return;
            }

            setManualLimitPrice(ticker, optionType, getOptionFromRow(row), price);
            updateRowPremiumDisplay(row);
            updateEarningsSummary();
        };

        input.addEventListener('input', applyManualPrice);
        input.addEventListener('change', applyManualPrice);
    });

    document.querySelectorAll('.reset-mid-price').forEach(button => {
        if (button.dataset.resetMidListenerAttached === 'true') return;
        button.dataset.resetMidListenerAttached = 'true';

        button.addEventListener('click', function() {
            const row = this.closest('tr');
            const input = row?.querySelector('.mid-price-input');
            if (!row || !input) return;

            const defaultPrice = Number.parseFloat(input.dataset.defaultPrice || 0);
            if (Number.isFinite(defaultPrice) && defaultPrice > 0) {
                input.value = defaultPrice.toFixed(2);
            }

            clearManualLimitPrice(input.dataset.ticker, input.dataset.optionType);
            updateRowPremiumDisplay(row);
            updateEarningsSummary();
        });
    });
}

/**
 * Update the earnings summary without rebuilding the entire table
 */
function updateEarningsSummary() {
    // Calculate earnings summary
    const earningsSummary = calculateEarningsSummary(tickersData);
    
    // Find the earnings summary section
    const summarySection = document.querySelector('.card.shadow-sm.mt-4');
    if (!summarySection) return;
    
    // Update the weekly premium values
    const weeklyCallsPremiumCell = summarySection.querySelector('td:nth-child(2)');
    const weeklyPutsPremiumCell = summarySection.querySelector('td:nth-child(3)');
    const weeklyTotalPremiumCell = summarySection.querySelector('td:nth-child(4)');
    const weeklyReturnCell = summarySection.querySelector('td:nth-child(6)');
    const annualReturnCell = summarySection.querySelector('td:nth-child(7)');
    
    // Update second row cells
    const stockValueCell = summarySection.querySelector('tr:nth-child(2) td:nth-child(2)');
    const cashBalanceCell = summarySection.querySelector('tr:nth-child(2) td:nth-child(3)');
    const cspRequirementCell = summarySection.querySelector('tr:nth-child(2) td:nth-child(4)');
    const annualIncomeCell = summarySection.querySelector('tr:nth-child(2) td:nth-child(6)');
    
    // Update the cells if found
    if (weeklyCallsPremiumCell) weeklyCallsPremiumCell.textContent = `Calls: ${formatCurrency(earningsSummary.totalWeeklyCallPremium)}`;
    if (weeklyPutsPremiumCell) weeklyPutsPremiumCell.textContent = `Puts: ${formatCurrency(earningsSummary.totalWeeklyPutPremium)}`;
    if (weeklyTotalPremiumCell) weeklyTotalPremiumCell.textContent = `Total: ${formatCurrency(earningsSummary.totalWeeklyPremium)}`;
    if (weeklyReturnCell) weeklyReturnCell.textContent = formatPercentage(earningsSummary.weeklyReturn);
    if (annualReturnCell) annualReturnCell.textContent = `Annual: ${formatPercentage(earningsSummary.projectedAnnualReturn)}`;
    
    if (stockValueCell) stockValueCell.textContent = `Stock: ${formatCurrency(earningsSummary.portfolioValue)}`;
    if (cashBalanceCell) cashBalanceCell.textContent = `Cash: ${formatCurrency(earningsSummary.cashBalance)}`;
    if (cspRequirementCell) cspRequirementCell.textContent = `CSP Requirement: ${formatCurrency(earningsSummary.totalPutExerciseCost)}`;
    if (annualIncomeCell) annualIncomeCell.textContent = formatCurrency(earningsSummary.projectedAnnualEarnings);
}

/**
 * Refresh options data for a specific ticker
 * @param {string} ticker - The ticker symbol to refresh options for
 * @param {boolean} [updateUI=false] - Whether to update the UI after refreshing
 */
async function refreshOptionsForTicker(ticker, updateUI = false) {
    try {
        console.log(`Starting refresh of options for ticker: ${ticker}`);
        
        // Remember which tab was active before refreshing
        const putTabWasActive = document.querySelector('#put-options-tab.active') !== null ||
                               document.querySelector('#put-options-section.active') !== null;
        console.log(`Put tab was active before refreshing ${ticker}:`, putTabWasActive);
        
        // Initialize tickersData for this ticker if it doesn't exist yet
        const tickerState = ensureTickerData(ticker);
        tickerState.callOtmPercentage = tickerState.callOtmPercentage || 10;
        tickerState.putOtmPercentage = tickerState.putOtmPercentage || 10;
        tickerState.putQuantity = tickerState.putQuantity || 1;
        
        // Get OTM percentages for calls and puts
        const callOtmPercentage = tickersData[ticker]?.callOtmPercentage || 10;
        const putOtmPercentage = tickersData[ticker]?.putOtmPercentage || 10;
        
        console.log(`Refreshing options for ${ticker} with call OTM ${callOtmPercentage}% and put OTM ${putOtmPercentage}%`);

        let closestExpiration = null;
        let allExpirations = [];
        try {
            allExpirations = await getTickerExpirations(ticker);
            if (allExpirations.length > 0) {
                closestExpiration = getDefaultExpiration(allExpirations);
            }
        } catch (error) {
            console.error(`Error fetching expiration dates for ${ticker}:`, error);
        }

        const callExpiration = getSelectedExpiration(ticker, 'CALL', closestExpiration);
        const putExpiration = getSelectedExpiration(ticker, 'PUT', closestExpiration);
        setSelectedExpiration(ticker, 'CALL', callExpiration);
        setSelectedExpiration(ticker, 'PUT', putExpiration);
        
        const [callOptionData, putOptionData] = await Promise.all([
            fetchOptionData(ticker, callOtmPercentage, 'CALL', callExpiration),
            fetchOptionData(ticker, putOtmPercentage, 'PUT', putExpiration)
        ]);
        
        // Make sure tickersData is initialized for this ticker
        if (!tickersData[ticker]) {
            console.log(`Initializing data structure for ${ticker}`);
            tickersData[ticker] = {
            data: {
                data: {}
                },
                callOtmPercentage: callOtmPercentage,
                putOtmPercentage: putOtmPercentage,
                putQuantity: 1
        };
        
            // Initialize the ticker data structure
            tickersData[ticker].data.data[ticker] = {
            stock_price: 0,
            position: 0,
            calls: [],
            puts: []
        };
        }
        
        // Merge call and put option data
        if (callOptionData && callOptionData.data && callOptionData.data[ticker]) {
            // Create or update ticker data
            tickersData[ticker].data = tickersData[ticker].data || { data: {} };
            tickersData[ticker].data.data = tickersData[ticker].data.data || {};
            tickersData[ticker].data.data[ticker] = tickersData[ticker].data.data[ticker] || {};
            
            // Update stock price and position
            tickersData[ticker].data.data[ticker].stock_price = callOptionData.data[ticker].stock_price || 0;
            tickersData[ticker].data.data[ticker].position = callOptionData.data[ticker].position || 0;
            
            // Update call options
            tickersData[ticker].data.data[ticker].calls = callOptionData.data[ticker].calls || [];
            
            console.log(`Updated CALL data for ${ticker}`);
        } else {
            console.log(`No valid CALL data received for ${ticker}`);
        }
        
        // Add put options data
        if (putOptionData && putOptionData.data && putOptionData.data[ticker]) {
            // Update put options
            tickersData[ticker].data.data[ticker].puts = putOptionData.data[ticker].puts || [];
            console.log(`Updated PUT data for ${ticker}`);
        } else {
            console.log(`No valid PUT data received for ${ticker}`);
        }
        
        console.log(`Completed data update for ${ticker}:`, JSON.stringify(tickersData[ticker]));
        
        // Only update the UI if requested - we'll avoid doing this when refreshing all tickers
        // to prevent the table from being rebuilt multiple times
        if (updateUI) {
            // If the PUT tab was active before, set it back to active
            if (putTabWasActive) {
                const putTab = document.getElementById('put-options-tab');
                const putSection = document.getElementById('put-options-section');
                const callTab = document.getElementById('call-options-tab');
                const callSection = document.getElementById('call-options-section');
                
                // Manually set the PUT tab as active if it exists
                if (putTab && putSection && callTab && callSection) {
                    putTab.classList.add('active');
                    putSection.classList.add('show', 'active');
                    callTab.classList.remove('active');
                    callSection.classList.remove('show', 'active');
                }
            }
        
        // Update the UI
        updateOptionsTable();
        
        // Make sure event listeners are added
        addOptionsTableEventListeners();
        }
        
    } catch (error) {
        console.error(`Error refreshing options for ${ticker}:`, error);
        showAlert(`Error refreshing options for ${ticker}: ${error.message}`, 'danger');
    }
}

/**
 * Refresh options data for all tickers
 * @param {string} [optionType] - Optional option type ('CALL' or 'PUT') to refresh only that type
 */
async function refreshAllOptions(optionType) {
    // Show a loading message
    const optionsTableContainer = document.getElementById('options-table-container');
    if (!optionsTableContainer) {
        console.error('Options table container not found');
        return;
    }
    
    try {
        // Remember which tab was active before refreshing
        const putTabWasActive = document.querySelector('#put-options-tab.active') !== null ||
                               document.querySelector('#put-options-section.active') !== null;
        console.log("Put tab was active before refresh:", putTabWasActive);
        
        // Get list of tickers to refresh
        let allTickers = Object.keys(tickersData);
        if (allTickers.length === 0) {
            const tickersResult = await fetchTickers();
            if (tickersResult && tickersResult.tickers) {
                allTickers.push(...tickersResult.tickers);
            }
        }
        
        // Get the correct table and button based on optionType
        let tableId, buttonId;
        if (optionType === 'CALL') {
            tableId = 'call-options-table';
            buttonId = 'refresh-all-calls';
        } else if (optionType === 'PUT') {
            tableId = 'put-options-table';
            buttonId = 'refresh-all-puts';
        } else {
            tableId = 'call-options-table'; // Default to call table for display purposes
            buttonId = 'refresh-all-options';
        }

        // Filter tickers based on the table type
        let tickersToRefresh = [];
        
        // Load excluded position tickers for PUT options
        const excludedTickers = loadExcludedTickers();
        
        if (optionType === 'CALL') {
            // For call options, only include tickers with sufficient shares
            tickersToRefresh = allTickers.filter(ticker => {
                const sharesOwned = tickersData[ticker]?.data?.data?.[ticker]?.position || 0;
                return sharesOwned >= 100;
            });
            console.log(`Filtered tickers for CALL options: ${tickersToRefresh.length} out of ${allTickers.length}`);
        } else if (optionType === 'PUT') {
            // For put options, include custom tickers and tickers with shares that aren't excluded
            tickersToRefresh = allTickers.filter(ticker => {
                const sharesOwned = tickersData[ticker]?.data?.data?.[ticker]?.position || 0;
                return customTickers.has(ticker) || 
                       (sharesOwned >= 100 && !excludedTickers.includes(ticker));
            });
            console.log(`Filtered tickers for PUT options: ${tickersToRefresh.length} out of ${allTickers.length}`);
        } else {
            // If no specific option type, refresh all tickers
            tickersToRefresh = allTickers;
        }
        
        console.log(`Refreshing ${optionType || 'all'} options for ${tickersToRefresh.length} tickers`);
        
        const refreshTasks = tickersToRefresh.flatMap(ticker => {
            const optionTypes = optionType ? [optionType] : ['CALL', 'PUT'];
            return optionTypes.map(type => ({ ticker, optionType: type }));
        });
        let completedTasks = 0;

        await runWithConcurrency(refreshTasks, REFRESH_CONCURRENCY, async task => {
            await refreshOptionsForTickerByType(task.ticker, task.optionType, false);
            completedTasks += 1;

            const button = document.getElementById(buttonId);
            if (button) {
                const progressText = tr('options.loadingTicker', {
                    ticker: task.ticker,
                    current: completedTasks,
                    total: refreshTasks.length
                });
                button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${progressText}`;
            }
        });
        
        // If we're refreshing PUT options specifically, set the PUT tab as active before updating
        if (optionType === 'PUT') {
            const putTab = document.getElementById('put-options-tab');
            const putSection = document.getElementById('put-options-section');
            const callTab = document.getElementById('call-options-tab');
            const callSection = document.getElementById('call-options-section');
            
            // Manually set the PUT tab as active if it exists
            if (putTab && putSection && callTab && callSection) {
                putTab.classList.add('active');
                putSection.classList.add('show', 'active');
                callTab.classList.remove('active');
                callSection.classList.remove('show', 'active');
            }
        } else if (putTabWasActive) {
            // If the PUT tab was active before and we're doing a general refresh, set it back to active
            const putTab = document.getElementById('put-options-tab');
            const putSection = document.getElementById('put-options-section');
            const callTab = document.getElementById('call-options-tab');
            const callSection = document.getElementById('call-options-section');
            
            // Manually set the PUT tab as active if it exists
            if (putTab && putSection && callTab && callSection) {
                putTab.classList.add('active');
                putSection.classList.add('show', 'active');
                callTab.classList.remove('active');
                callSection.classList.remove('show', 'active');
            }
        }
        
        // Final UI update after all tickers are refreshed
        updateOptionsTable();
        
        // Make sure event listeners are added
        addOptionsTableEventListeners();
        
    } catch (error) {
        console.error(`Error refreshing ${optionType || 'all'} options:`, error);
        showAlert(`Error refreshing options: ${error.message}`, 'danger');
        
        // Reset to empty UI in case of error
        updateOptionsTable();
    }
}

/**
 * Refresh options data for a specific ticker and option type
 * @param {string} ticker - The ticker symbol to refresh options for
 * @param {string} optionType - The option type to refresh ('CALL' or 'PUT')
 * @param {boolean} [updateUI=false] - Whether to update the UI after refreshing
 */
async function refreshOptionsForTickerByType(ticker, optionType, updateUI = false) {
    try {
        const tickerState = ensureTickerData(ticker);
        tickerState.callOtmPercentage = tickerState.callOtmPercentage || 10;
        tickerState.putOtmPercentage = tickerState.putOtmPercentage || 10;
        tickerState.putQuantity = tickerState.putQuantity || 1;

        // Get the appropriate OTM percentage based on option type
        let otmPercentage;
        if (optionType === 'CALL') {
            otmPercentage = tickerState.callOtmPercentage;
        } else {
            otmPercentage = tickerState.putOtmPercentage;
        }
        
        console.log(`Refreshing ${optionType} options for ${ticker} with OTM ${otmPercentage}%`);
        
        let closestExpiration = null;
        let allExpirations = [];
        try {
            allExpirations = await getTickerExpirations(ticker);
            if (allExpirations.length > 0) {
                closestExpiration = getDefaultExpiration(allExpirations);
            }
        } catch (error) {
            console.error(`Error fetching expiration dates for ${ticker}:`, error);
        }

        const selectedExpiration = getSelectedExpiration(ticker, optionType, closestExpiration);
        setSelectedExpiration(ticker, optionType, selectedExpiration);
        
        // Make API call for specific option type with the selected expiration
        console.log(`Fetching ${optionType} options for ${ticker} with OTM ${otmPercentage}% and expiration ${selectedExpiration || 'default'}`);
        const optionData = await fetchOptionData(ticker, otmPercentage, optionType, selectedExpiration);
        
        console.log(`${optionType} data for ${ticker}:`, optionData);
        
        // Update only the specific option type data
        updateTickerOptionData(ticker, optionType, optionData);
        
        console.log(`Updated ${optionType} data for ${ticker}:`, tickersData[ticker]);
        
        // Only update the UI if requested - we'll avoid doing this when refreshing all tickers
        // to prevent the table from being rebuilt multiple times
        if (updateUI) {
            // If this is a PUT refresh, explicitly set the PUT tab to active before updating
            if (optionType === 'PUT') {
                const putTab = document.getElementById('put-options-tab');
                const putSection = document.getElementById('put-options-section');
                const callTab = document.getElementById('call-options-tab');
                const callSection = document.getElementById('call-options-section');
                
                // Manually set the PUT tab as active if it exists
                if (putTab && putSection && callTab && callSection) {
                    putTab.classList.add('active');
                    putSection.classList.add('show', 'active');
                    callTab.classList.remove('active');
                    callSection.classList.remove('show', 'active');
                }
            }
            
            // Update the UI
            updateOptionsTable();
            
            // Make sure event listeners are added
            addOptionsTableEventListeners();
        }
        
    } catch (error) {
        console.error(`Error refreshing ${optionType} options for ${ticker}:`, error);
        showAlert(`Error refreshing ${optionType} options for ${ticker}: ${error.message}`, 'danger');
    }
}

/**
 * Add all available options of a specific type
 * @param {string} optionType - The option type ('CALL' or 'PUT')
 * @returns {Promise<number>} - Number of successfully created orders
 */
async function sellAllOptions(optionType) {
    console.log(`Starting sellAllOptions for ${optionType} options`);
    
    const successOrders = [];
    const failedOrders = [];
    
    // Process each ticker
    const tickers = Object.keys(tickersData);
    console.log(`Processing ${tickers.length} tickers for ${optionType} options`);
    
    // Show progress in the button
    const buttonId = optionType === 'CALL' ? 'sell-all-calls' : 'sell-all-puts';
    const button = document.getElementById(buttonId);
    if (button) {
        button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${tr('common.loading')}`;
        button.disabled = true;
    }
    
    try {
    for (const ticker of tickers) {
        const tickerData = tickersData[ticker];
        
        // Skip tickers without data
        if (!tickerData || !tickerData.data || !tickerData.data.data || !tickerData.data.data[ticker]) {
            console.log(`Skipping ticker ${ticker} - missing or invalid data`);
            continue;
        }
        
        const optionData = tickerData.data.data[ticker];
        
            // For CALL options, skip positions with less than 100 shares (can't sell covered calls)
        const sharesOwned = optionData.position || 0;
            if (optionType === 'CALL' && sharesOwned < 100) {
                console.log(`Skipping ticker ${ticker} - insufficient shares for calls: ${sharesOwned}`);
            continue;
        }
        
        // Get the options based on type
        let options = [];
        if (optionType === 'CALL' && optionData.calls && optionData.calls.length > 0) {
            options = optionData.calls;
            console.log(`Found ${options.length} CALL options for ${ticker}`);
        } else if (optionType === 'PUT' && optionData.puts && optionData.puts.length > 0) {
            options = optionData.puts;
            console.log(`Found ${options.length} PUT options for ${ticker}`);
        } else {
            console.log(`No ${optionType} options found for ${ticker}`);
            continue;
        }
        
        // Skip if no options available
        if (options.length === 0) {
            console.log(`No ${optionType} options available for ${ticker}`);
            continue;
        }
        
        // Use the first option (best match)
        const option = options[0];
        if (!option) {
            console.log(`Invalid option data for ${ticker}`);
            continue;
        }
            
            // Update UI with current ticker
            if (button) {
                button.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${tr('options.processingTicker', { ticker })}`;
            }
        
        console.log(`Processing order for ${ticker} ${optionType} option: ${option.strike} ${option.expiration}`);
        const defaultPremium = calculatePremium(option.bid, option.ask, option.last);
        const manualPremium = getManualLimitPrice(ticker, optionType, option);
        
        // Create order data
        const orderData = {
            ticker: ticker,
            option_type: optionType,
            strike: parseFloat(option.strike),
            expiration: option.expiration,
            action: 'SELL',
            quantity: optionType === 'CALL' ? 
                Math.floor(sharesOwned / 100) : 
                    (tickerData.putQuantity || 1),
            // Get price data from the option object instead of button.dataset
            bid: parseFloat(option.bid || 0),
            ask: parseFloat(option.ask || 0),
            last: parseFloat(option.last || 0),
            premium: manualPremium ?? defaultPremium,
            delta: parseFloat(option.delta || 0),
            gamma: parseFloat(option.gamma || 0),
            theta: parseFloat(option.theta || 0),
            vega: parseFloat(option.vega || 0),
            implied_volatility: parseFloat(option.implied_volatility || 0),
            // Add timestamp
            timestamp: new Date().toISOString(),
            // Add market data reference
            stock_price: tickersData[ticker]?.data?.data?.[ticker]?.stock_price || 0
        };
        
        // Safety check for critical price fields - this shouldn't be needed now but keeping as fallback
        if (orderData.bid <= 0 && button.closest('tr')) {
            // Try to get data directly from option object again
            orderData.bid = parseFloat(option.bid || 0);
            orderData.ask = parseFloat(option.ask || 0);
            orderData.last = parseFloat(option.last || 0);
            orderData.premium = manualPremium ?? defaultPremium;
            
            console.log(`Updated order price fields from option object - bid: ${orderData.bid}, ask: ${orderData.ask}, last: ${orderData.last}, premium: ${orderData.premium}`);
        }
        
        // Final sanity check - ensure we have some price reference
        if (orderData.bid <= 0 && orderData.ask <= 0 && orderData.last <= 0 && orderData.premium <= 0) {
            console.warn('No valid price information for order - using fallback minimum price');
            // Use 1% of strike as a minimum
            orderData.premium = Math.max(orderData.strike * 0.01, 0.05);
        }
        
        console.log('Submitting order with data:', orderData);
        
        try {
            // Proceed directly without confirmation dialog
            button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';
            button.disabled = true;
            
            // Save the order
            const result = await saveOptionOrder(orderData);
            
            if (result && result.order_id) {
                console.log(`Order saved successfully for ${ticker} ${optionType} ${option.strike} ${option.expiration}! Order ID: ${result.order_id}`);
                successOrders.push(`${ticker} ${optionType} ${option.strike} ${option.expiration}`);
            } else {
                console.error(`Failed to save order for ${ticker} ${optionType} ${option.strike} ${option.expiration}`);
                failedOrders.push(`${ticker} ${optionType} ${option.strike} ${option.expiration}`);
            }
        } catch (error) {
            console.error(`Error saving order for ${ticker}:`, error);
            failedOrders.push(`${ticker} ${optionType} ${option.strike} ${option.expiration}`);
        }
            
            // Small delay to prevent overwhelming the server
            await new Promise(resolve => setTimeout(resolve, 100));
    }
    
    // Log results
    console.log(`Add all ${optionType} orders results:`, {
        successful: successOrders.length,
        failed: failedOrders.length,
        successDetails: successOrders,
        failDetails: failedOrders
    });
    
    if (failedOrders.length > 0) {
        console.error(`${failedOrders.length} orders failed to be created`);
    }
        
        // Reset the button state
        if (button) {
            button.innerHTML = `<i class="bi bi-check2-all"></i> ${tr('common.addAll')}`;
            button.disabled = false;
        }
        
        // Show a summary alert
        if (successOrders.length > 0) {
            showAlert(`Successfully created ${successOrders.length} ${optionType.toLowerCase()} option orders`, 'success');
            
            // Ensure the pending orders table is refreshed after successful orders
            console.log('Refreshing pending orders table after successful add all operation');
            
            // Make multiple attempts to refresh pending orders to ensure it works
            // First immediate refresh
            await refreshPendingOrders();
            
            // Second delayed refresh (after a short delay)
            setTimeout(async () => {
                console.log('Executing delayed refresh of pending orders');
                await refreshPendingOrders();
            }, 500);
            
            // Third refresh with a longer delay (to catch any async operations)
            setTimeout(async () => {
                console.log('Executing final refresh of pending orders');
                await refreshPendingOrders();
            }, 1500);
        } else {
            showAlert(`No ${optionType.toLowerCase()} option orders were created`, 'warning');
        }
    
    return successOrders.length;
    } catch (error) {
        console.error(`Error in sellAllOptions for ${optionType}:`, error);
        
        // Reset the button state
        if (button) {
            button.innerHTML = `<i class="bi bi-check2-all"></i> ${tr('common.addAll')}`;
            button.disabled = false;
        }
        
        // Show error alert
        showAlert(`Error adding ${optionType.toLowerCase()} options: ${error.message}`, 'danger');
        
        return 0;
    }
}

// Add an event listener for the custom ticker form
function setupCustomTickerEventListeners() {
    console.log('Setting up custom ticker event listeners, already initialized:', customTickerListenersInitialized);
    
    // Reset flag to force initialization (temp fix for debugging)
    customTickerListenersInitialized = false;
    
    if (customTickerListenersInitialized) return;
    
    const addCustomTickerBtn = document.getElementById('add-custom-ticker');
    const customTickerInput = document.getElementById('custom-ticker-input');
    
    console.log('Custom ticker elements:', {
        button: addCustomTickerBtn,
        input: customTickerInput
    });
    
    if (addCustomTickerBtn && customTickerInput) {
        addCustomTickerBtn.addEventListener('click', async () => {
            console.log('Add custom ticker button clicked');
            const ticker = customTickerInput.value.trim().toUpperCase();
            if (!ticker) {
                console.log('No ticker entered');
                return;
            }
            
            console.log('Processing ticker:', ticker);
            
            if (customTickers.has(ticker)) {
                console.log('Ticker already exists in custom tickers');
                showToast('warning', tr('options.tickerAlreadyAdded'), tr('options.tickerAlreadyAddedMessage', { ticker }));
                return;
            }
            
            // Show loading indicator
            addCustomTickerBtn.disabled = true;
            addCustomTickerBtn.innerHTML = `<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> ${tr('common.loading')}`;
            
            try {
                console.log('Fetching expiration dates for ticker:', ticker);
                
                // Get OTM percent from UI or use default - only setting this up in data structure, not fetching options yet
                let otmPercent = 5; // Default

                // First try to get from the dedicated OTM% selector in the options table header
                const otmPercentSelect = document.getElementById('otm-percent');
                if (otmPercentSelect) {
                    otmPercent = parseInt(otmPercentSelect.value, 10);
                    console.log('Found OTM percent selector with value:', otmPercent);
                }
                
                // 1. Fetch expiration dates first
                const expirationData = await fetchOptionExpirations(ticker);
                console.log('Received expiration data:', expirationData);
                
                if (!expirationData || !expirationData.expirations || expirationData.expirations.length === 0) {
                    console.error('No expiration dates found for ticker:', ticker);
                    showToast('error', tr('options.dataError'), tr('options.noExpirationForTicker', { ticker }));
                    return;
                }
                
                // 2. Add to custom tickers set without fetching options data yet
                customTickers.add(ticker);
                console.log('Added to custom tickers, new set:', [...customTickers]);
                
                // 3. Initialize ticker data structure with expirations and basic info, but no options data yet
                if (!tickersData[ticker]) {
                    console.log('Creating new ticker data structure for', ticker);
                    tickersData[ticker] = {
                        data: {
                            data: {}
                        },
                        callOtmPercentage: parseInt(otmPercent, 10),
                        putOtmPercentage: parseInt(otmPercent, 10),
                        putQuantity: 1,
                        expirations: expirationData.expirations // Store the expirations
                    };
                    
                    // Add minimal structure needed for rendering
                    tickersData[ticker].data.data[ticker] = {
                        stock_price: 0, // Will be filled when actually fetching options
                        position: 0,    // No shares for custom tickers
                        calls: [],
                        puts: []        // Empty puts array until user selects expiration and refreshes
                    };
                    
                    // Try to get stock price separately without options data
                    try {
                        const stockPriceData = await fetchStockPrices([ticker]);
                        if (stockPriceData && stockPriceData.data && stockPriceData.data[ticker]) {
                            tickersData[ticker].data.data[ticker].stock_price = stockPriceData.data[ticker];
                        }
                    } catch (priceError) {
                        console.error('Error fetching stock price:', priceError);
                        // Continue anyway - price will be updated when user refreshes
                    }
                }
                
                // 4. Save custom tickers to localStorage
                localStorage.setItem('customTickers', JSON.stringify([...customTickers]));
                
                // 5. Update the table to show the new ticker with expiration dropdown but no options data yet
                console.log('Updating options table with new ticker and expiration dropdown');
                updateOptionsTable();
                
                // 6. Make sure event listeners are attached
                addOptionsTableEventListeners();
                
                // 7. Clear the input field
                customTickerInput.value = '';
                
                showToast('success', tr('options.tickerAdded'), tr('options.tickerAddedMessage', { ticker }));
            } catch (error) {
                console.error('Error adding custom ticker:', error);
                showToast('error', tr('options.error'), tr('options.failedAddTicker', { ticker, message: error.message }));
            } finally {
                // Reset button state
                addCustomTickerBtn.disabled = false;
                addCustomTickerBtn.innerHTML = `<i class="bi bi-plus-circle"></i> ${tr('common.add')}`;
            }
        });
        
        // Add event listener for Enter key
        customTickerInput.addEventListener('keypress', (event) => {
            console.log('Key pressed in input:', event.key);
            if (event.key === 'Enter') {
                event.preventDefault();
                console.log('Enter key pressed, triggering click');
                addCustomTickerBtn.click();
            }
        });
        
        console.log('Event listeners for custom ticker successfully initialized');
        customTickerListenersInitialized = true;
    } else {
        console.error('Could not find custom ticker elements in the DOM');
    }
}

// Function to remove a custom ticker
function removeCustomTicker(ticker) {
    if (customTickers.has(ticker)) {
        customTickers.delete(ticker);
        localStorage.setItem('customTickers', JSON.stringify([...customTickers]));
        
        // If the ticker exists in tickersData, remove its data
        if (tickersData[ticker]) {
            delete tickersData[ticker];
        }
        
        // Save updated OTM settings to localStorage
        saveOtmSettings();
        
        // Update the table
        updateOptionsTable();
        showToast('info', tr('options.tickerRemoved'), tr('options.tickerRemovedMessage', { ticker }));
    }
}

// Function to exclude a position ticker from PUT options table
function excludePositionTicker(ticker) {
    // Store excluded position tickers in localStorage
    let excludedTickers = [];
    try {
        const savedExcluded = localStorage.getItem('excludedPositionTickers');
        if (savedExcluded) {
            excludedTickers = JSON.parse(savedExcluded);
        }
    } catch (error) {
        console.error('Error loading excluded tickers:', error);
    }
    
    // Add to excluded list if not already there
    if (!excludedTickers.includes(ticker)) {
        excludedTickers.push(ticker);
        localStorage.setItem('excludedPositionTickers', JSON.stringify(excludedTickers));
    }
    
    // If the ticker exists in tickersData, remove its data
    if (tickersData[ticker]) {
        delete tickersData[ticker];
    }
    
    // Save updated OTM settings to localStorage
    saveOtmSettings();
    
    // Update the table
    updateOptionsTable();
    showToast('info', tr('options.tickerExcluded'), tr('options.tickerExcludedMessage', { ticker }));
}

// Function to handle ticker removal (both custom and position-based)
function removeTicker(ticker) {
    cleanupTooltips();

    if (customTickers.has(ticker)) {
        removeCustomTicker(ticker);
    } else {
        excludePositionTicker(ticker);
    }
}

// Load excluded position tickers from localStorage
function loadExcludedTickers() {
    try {
        const savedExcluded = localStorage.getItem('excludedPositionTickers');
        if (savedExcluded) {
            return JSON.parse(savedExcluded);
        }
    } catch (error) {
        console.error('Error loading excluded tickers:', error);
    }
    return [];
}

// Load custom tickers from localStorage
function loadCustomTickers() {
    try {
        const savedTickers = localStorage.getItem('customTickers');
        if (savedTickers) {
            const tickersArray = JSON.parse(savedTickers);
            customTickers = new Set(tickersArray);
        }
    } catch (error) {
        console.error('Error loading custom tickers:', error);
    }
}

// Helper function to show toast notifications
function showToast(type, title, message) {
    let toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'position-fixed bottom-0 end-0 p-3';
        container.style.zIndex = '5';
        document.body.appendChild(container);
        toastContainer = container;
    }
    
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type === 'success' ? 'success' : type === 'warning' ? 'warning' : type === 'error' ? 'danger' : 'primary'}`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');
    
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">
                <strong>${title}</strong>: ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;
    
    toastContainer.appendChild(toast);
    
    const bsToast = new bootstrap.Toast(toast, { autohide: true, delay: 3000 });
    bsToast.show();
    
    // Auto-remove the toast element after it's hidden
    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
    });
}

// Now in the initialize function, we need to load custom tickers
function initialize() {
    loadCustomTickers();
    loadOtmSettings();
}

/**
 * Add a single ticker row to the options table
 * @param {string} tableId - The ID of the table to add the row to
 * @param {string} optionType - The option type ('CALL' or 'PUT')
 * @param {string} ticker - The ticker symbol
 * @returns {boolean} - Whether a row was added
 */
function addTickerRowToTable(tableId, optionType, ticker) {
    console.log(`Adding ${optionType} row for ticker ${ticker} to table ${tableId}`);
    
    const table = document.getElementById(tableId);
    if (!table) {
        console.error(`Table with ID ${tableId} not found in the DOM`);
        return false;
    }
    
    const tbody = table.querySelector('tbody');
    if (!tbody) {
        console.error(`Table body not found in table with ID ${tableId}`);
        return false;
    }

    const tickerData = tickersData[ticker];
    if (!tickerData) {
        console.log(`No data for ticker ${ticker}, skipping`);
        return false;
    }
    
    // Load excluded position tickers for PUT options
    const excludedTickers = loadExcludedTickers();
    
    // For calls, only show if shares owned
    // For puts, show if it's in customTickers or has shares 
    if (optionType === 'CALL') {
        // Get position data safely (handles nested structure)
        const sharesOwned = tickerData.data?.data?.[ticker]?.position || 0;
        
        if (sharesOwned < 100) {
            console.log(`Skipping ${ticker} for CALL options - insufficient shares: ${sharesOwned}`);
            return false;
        }
    } else if (optionType === 'PUT') {
        // For PUT options, check if it's a custom ticker or has sufficient shares
        const sharesOwned = tickerData.data?.data?.[ticker]?.position || 0;
        
        // Skip excluded position tickers
        if (excludedTickers.includes(ticker) && !customTickers.has(ticker)) {
            console.log(`Skipping ${ticker} for PUT options - in excluded list`);
            return false;
        }
        
        if (!customTickers.has(ticker) && sharesOwned < 100) {
            console.log(`Skipping ${ticker} for PUT options - not a custom ticker and insufficient shares: ${sharesOwned}`);
            return false;
        }
        
        console.log(`Including ${ticker} for PUT options - custom: ${customTickers.has(ticker)}, shares: ${sharesOwned}`);
    }
    
    // Check if we have valid option data
    let optionData, options;
    
    if (tickerData.data?.data?.[ticker]) {
        optionData = tickerData.data.data[ticker];
        options = optionType === 'CALL' ? optionData.calls : optionData.puts;
        
        console.log(`Option data for ${ticker}: ${JSON.stringify(optionData)}`);
        console.log(`${optionType} options for ${ticker}: ${options ? options.length : 0} options`);
    } else {
        console.log(`No proper data structure for ${ticker}`);
        options = [];
    }
    
    // Create a row for the ticker, even if no options data
    const row = document.createElement('tr');
    
    // Store row data attributes for recalculation
    row.dataset.ticker = ticker;
    
    // Get stock price and shares owned safely
    const stockPrice = optionData?.stock_price || 0;
    const sharesOwned = optionData?.position || 0;
    
    if (!options || options.length === 0) {
        // Instead of a warning message row with colSpan, create a row with empty data cells
        if (optionType === 'CALL') {
            const maxContracts = Math.floor(sharesOwned / 100);
            
            // Create expiration dropdown options even for empty row
            let expirationOptionsHtml = '';
            const expirations = tickersData[ticker].expirations || [];
            if (expirations.length > 0) {
                const selectedExpiration = getSelectedExpiration(
                    ticker,
                    'CALL',
                    getDefaultExpiration(expirations)
                );
                expirations.forEach(exp => {
                    const selected = exp.value === selectedExpiration ? 'selected' : '';
                    expirationOptionsHtml += `<option value="${exp.value}" ${selected}>${exp.label}</option>`;
                });
            } else {
                expirationOptionsHtml = `<option value="">${tr('options.noExpirations')}</option>`;
            }
            
            row.innerHTML = `
                <td class="align-middle">${ticker}</td>
                <td class="align-middle">${sharesOwned}</td>
                <td class="align-middle">${stockPrice ? '$ ' + stockPrice.toFixed(2) : 'N/A'}</td>
                <td class="align-middle">
                    <div class="input-group input-group-sm">
                        <input type="number" class="form-control form-control-sm otm-input" 
                            data-ticker="${ticker}" 
                            data-option-type="CALL"
                            min="1" max="50" step="1" 
                            value="${tickerData.callOtmPercentage || 10}">
                        <button class="btn btn-outline-secondary btn-sm refresh-otm" data-ticker="${ticker}">
                            <i class="bi bi-arrow-repeat"></i>
                        </button>
                    </div>
                </td>
                <td class="align-middle">-</td>
                <td class="align-middle">
                    <select class="form-select form-select-sm expiration-select" data-ticker="${ticker}" data-option-type="CALL">
                        ${expirationOptionsHtml}
                    </select>
                </td>
                <td class="align-middle">-</td>
                <td class="align-middle">-</td>
                <td class="align-middle">-</td>
                <td class="align-middle">${maxContracts}</td>
                <td class="align-middle">$ 0.00</td>
                <td class="align-middle">
                    <button class="btn btn-sm btn-outline-secondary refresh-option" 
                        data-ticker="${ticker}" 
                        data-type="CALL">
                        <i class="bi bi-arrow-repeat"></i> ${tr('common.refresh')}
                    </button>
                </td>
            `;
        } else {
            // PUT option empty row
            const putQuantity = tickerData.putQuantity || 1;
            
            // Create expiration dropdown options even for empty row
            let expirationOptionsHtml = '';
            const expirations = tickersData[ticker].expirations || [];
            if (expirations.length > 0) {
                const selectedExpiration = getSelectedExpiration(
                    ticker,
                    'PUT',
                    getDefaultExpiration(expirations)
                );
                expirations.forEach(exp => {
                    const selected = exp.value === selectedExpiration ? 'selected' : '';
                    expirationOptionsHtml += `<option value="${exp.value}" ${selected}>${exp.label}</option>`;
                });
            } else {
                expirationOptionsHtml = `<option value="">${tr('options.noExpirations')}</option>`;
            }
            
            row.innerHTML = `
                <td class="align-middle">${ticker}</td>
                <td class="align-middle">${stockPrice ? '$ ' + stockPrice.toFixed(2) : 'N/A'}</td>
                <td class="align-middle">
                    <div class="input-group input-group-sm">
                        <input type="number" class="form-control form-control-sm otm-input" 
                            data-ticker="${ticker}" 
                            data-option-type="PUT"
                            min="1" max="50" step="1" 
                            value="${tickerData.putOtmPercentage || 10}">
                        <button class="btn btn-outline-secondary btn-sm refresh-otm" data-ticker="${ticker}">
                            <i class="bi bi-arrow-repeat"></i>
                        </button>
                    </div>
                </td>
                <td class="align-middle">-</td>
                <td class="align-middle">
                    <select class="form-select form-select-sm expiration-select" data-ticker="${ticker}" data-option-type="PUT">
                        ${expirationOptionsHtml}
                    </select>
                </td>
                <td class="align-middle">-</td>
                <td class="align-middle">-</td>
                <td class="align-middle">-</td>
                <td class="align-middle">
                    <input type="number" class="form-control form-control-sm put-qty-input" 
                        data-ticker="${ticker}" 
                        value="${putQuantity}" 
                        min="1" max="100" step="1" style="width: 70px;">
                </td>
                <td class="align-middle total-premium">$ 0.00</td>
                <td class="align-middle cash-required">$ 0.00</td>
                <td class="align-middle">
                    <div class="option-actions">
                        <button class="btn btn-sm btn-outline-secondary refresh-option" 
                            data-ticker="${ticker}" 
                            data-type="PUT"
                            data-bs-toggle="tooltip"
                            title="${tr('common.refresh')}">
                            <i class="bi bi-arrow-repeat"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger delete-ticker" 
                            data-ticker="${ticker}" 
                            data-bs-toggle="tooltip" 
                            title="${tr('options.removeTicker')}">
                            <i class="bi bi-x"></i>
                        </button>
                    </div>
                </td>
            `;
        }
        
        console.log(`Added empty ${optionType} row for ${ticker} - no options data found`);
        tbody.appendChild(row);
        return true;
    }
    
    const option = options[0]; // Get the first option
    if (!option) {
        console.log(`No option found for ${ticker}`);
        return false;
    }
    
    console.log(`Creating row for ${ticker} with option: ${JSON.stringify(option)}`);
    const optionMidPrice = calculatePremium(option.bid, option.ask, option.last);
    const manualPrice = getManualLimitPrice(ticker, optionType, option);
    const displayedLimitPrice = manualPrice ?? optionMidPrice;
    
    // Update row data attributes
    row.dataset.premium = displayedLimitPrice * 100;
    row.dataset.defaultPremium = optionMidPrice;
    row.dataset.strike = option.strike || 0;
    row.dataset.expiration = option.expiration || '';
    row.dataset.optionType = optionType;
    
    // Format IV% value
    const ivPercent = option.implied_volatility ? option.implied_volatility.toFixed(2) : 'N/A';
    
    // For CALL options
    if (optionType === 'CALL') {
        const maxContracts = Math.floor(sharesOwned / 100);
        
        // Calculate premium and return values
        const midPrice = displayedLimitPrice;
        const premiumPerContract = midPrice * 100; // Use midPrice instead of option.ask
        const totalPremium = premiumPerContract * maxContracts;
        row.dataset.contracts = maxContracts;
        
        // Calculate return on capital
        const returnOnCapital = option.strike > 0 ? ((totalPremium / (stockPrice * 100 * maxContracts)) * 100) : 0;
        
        // Create expiration dropdown options
        let expirationOptionsHtml = '';
        const expirations = tickersData[ticker].expirations || [];
        if (expirations.length > 0) {
            expirations.forEach(exp => {
                const selected = exp.value === option.expiration ? 'selected' : '';
                expirationOptionsHtml += `<option value="${exp.value}" ${selected}>${exp.label}</option>`;
            });
        } else {
            // If no expiration data is available, just show the current one
            expirationOptionsHtml = `<option value="${option.expiration}" selected>${option.expiration}</option>`;
        }
        
        row.innerHTML = `
            <td class="align-middle">
                ${ticker}
            </td>
            <td class="align-middle">${sharesOwned}</td>
            <td class="align-middle">${stockPrice ? '$ ' + stockPrice.toFixed(2) : 'N/A'}</td>
            <td class="align-middle">
                <div class="input-group input-group-sm">
                    <input type="number" class="form-control form-control-sm otm-input" 
                        data-ticker="${ticker}" 
                        data-option-type="CALL"
                        min="1" max="50" step="1" 
                        value="${tickerData.callOtmPercentage || 10}">
                    <button class="btn btn-outline-secondary btn-sm refresh-otm" data-ticker="${ticker}">
                        <i class="bi bi-arrow-repeat"></i>
                    </button>
                </div>
            </td>
            <td class="align-middle">${option.strike ? '$ ' + option.strike.toFixed(2) : 'N/A'}</td>
            <td class="align-middle">
                <select class="form-select form-select-sm expiration-select" data-ticker="${ticker}" data-option-type="CALL">
                    ${expirationOptionsHtml}
                </select>
            </td>
            <td class="align-middle" data-field="mid-price">${buildLimitPriceControl(ticker, 'CALL', option, midPrice, optionMidPrice)}</td>
            <td class="align-middle">${option.delta ? option.delta.toFixed(2) : 'N/A'}</td>
            <td class="align-middle">${ivPercent}%</td>
            <td class="align-middle">${maxContracts}</td>
            <td class="align-middle total-premium">$ ${totalPremium.toFixed(2)}</td>
            <td class="align-middle">
                <div class="option-actions">
                    <button class="btn btn-sm btn-outline-success sell-option" 
                        data-ticker="${ticker}" 
                        data-option-type="CALL" 
                        data-strike="${option.strike || 0}" 
                        data-expiration="${option.expiration || ''}"
                        data-bid="${option.bid || 0}"
                        data-ask="${option.ask || 0}"
                        data-last="${option.last || 0}"
                        data-delta="${option.delta || 0}"
                        data-gamma="${option.gamma || 0}"
                        data-theta="${option.theta || 0}"
                        data-vega="${option.vega || 0}"
                        data-implied-volatility="${option.implied_volatility || 0}"
                        data-volume="${option.volume || 0}"
                        data-open-interest="${option.open_interest || 0}">
                        <i class="bi bi-check-circle"></i> ${tr('common.add')}
                    </button>
                    <button class="btn btn-sm btn-outline-danger delete-ticker" 
                        data-ticker="${ticker}" 
                        data-bs-toggle="tooltip" 
                        title="${tr('options.removeTicker')}">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </td>
        `;
        
        console.log(`Added CALL option row for ${ticker} with ${maxContracts} potential contracts`);
    }
    // For PUT options
    else {
        const putQuantity = tickerData.putQuantity || 1;
        
        // Calculate mid price between bid and ask
        const midPrice = displayedLimitPrice;
        row.dataset.contracts = putQuantity;
        
        // Create expiration dropdown options
        let expirationOptionsHtml = '';
        const expirations = tickersData[ticker].expirations || [];
        if (expirations.length > 0) {
            expirations.forEach(exp => {
                const selected = exp.value === option.expiration ? 'selected' : '';
                expirationOptionsHtml += `<option value="${exp.value}" ${selected}>${exp.label}</option>`;
            });
        } else {
            // If no expiration data is available, just show the current one
            expirationOptionsHtml = `<option value="${option.expiration}" selected>${option.expiration}</option>`;
        }
        
        row.innerHTML = `
            <td class="align-middle">
                ${ticker}
            </td>
            <td class="align-middle">${stockPrice ? '$ ' + stockPrice.toFixed(2) : 'N/A'}</td>
            <td class="align-middle">
                <div class="input-group input-group-sm">
                    <input type="number" class="form-control form-control-sm otm-input" 
                        data-ticker="${ticker}" 
                        data-option-type="PUT"
                        min="1" max="50" step="1" 
                        value="${tickerData.putOtmPercentage || 10}">
                    <button class="btn btn-outline-secondary btn-sm refresh-otm" data-ticker="${ticker}">
                        <i class="bi bi-arrow-repeat"></i>
                    </button>
                </div>
            </td>
            <td class="align-middle">${option.strike ? '$ ' + option.strike.toFixed(2) : 'N/A'}</td>
            <td class="align-middle">
                <select class="form-select form-select-sm expiration-select" data-ticker="${ticker}" data-option-type="PUT">
                    ${expirationOptionsHtml}
                </select>
            </td>
            <td class="align-middle" data-field="mid-price">${buildLimitPriceControl(ticker, 'PUT', option, midPrice, optionMidPrice)}</td>
            <td class="align-middle">${option.delta ? option.delta.toFixed(2) : 'N/A'}</td>
            <td class="align-middle">${ivPercent}%</td>
            <td class="align-middle">
                <input type="number" class="form-control form-control-sm put-qty-input" 
                    data-ticker="${ticker}" 
                    value="${putQuantity}" 
                    min="1" max="100" step="1" style="width: 70px;">
            </td>
            <td class="align-middle total-premium">
                $ ${(midPrice * 100 * putQuantity).toFixed(2)}
            </td>
            <td class="align-middle cash-required">
                $ ${((option.strike || 0) * 100 * putQuantity).toFixed(2)}
            </td>
            <td class="align-middle">
                <div class="option-actions">
                    <button class="btn btn-sm btn-outline-success sell-option" 
                        data-ticker="${ticker}" 
                        data-option-type="PUT" 
                        data-strike="${option.strike || 0}" 
                        data-expiration="${option.expiration || ''}"
                        data-bid="${option.bid || 0}"
                        data-ask="${option.ask || 0}"
                        data-last="${option.last || 0}"
                        data-delta="${option.delta || 0}"
                        data-gamma="${option.gamma || 0}"
                        data-theta="${option.theta || 0}"
                        data-vega="${option.vega || 0}"
                        data-implied-volatility="${option.implied_volatility || 0}"
                        data-volume="${option.volume || 0}"
                        data-open-interest="${option.open_interest || 0}">
                        <i class="bi bi-check-circle"></i> ${tr('common.add')}
                    </button>
                    <button class="btn btn-sm btn-outline-danger delete-ticker" 
                        data-ticker="${ticker}" 
                        data-bs-toggle="tooltip" 
                        title="${tr('options.removeTicker')}">
                        <i class="bi bi-x"></i>
                    </button>
                </div>
            </td>
        `;
        
        console.log(`Added PUT option row for ${ticker}`);
    }
    
    // Add the row to the table
    tbody.appendChild(row);
    return true;
}

// Modify the buildOptionsTable function to use the new addTickerRowToTable function
function buildOptionsTable(tableId, optionType) {
    console.log(`Building ${optionType} options table with ID: ${tableId}`);
    
    const table = document.getElementById(tableId);
    if (!table) {
        console.error(`Table with ID ${tableId} not found in the DOM`);
        return;
    }
    
    const tbody = table.querySelector('tbody');
    if (!tbody) {
        console.error(`Table body not found in table with ID ${tableId}`);
        return;
    }
    
    // Update the table headers to include IV%
    const thead = table.querySelector('thead');
    if (thead && thead.querySelector('tr')) {
        const headerRow = thead.querySelector('tr');
        // Check if the IV% column already exists to avoid duplicates
        const existingIvHeader = Array.from(headerRow.querySelectorAll('th')).find(th => th.textContent === 'IV%');
        if (!existingIvHeader) {
            // Find where we want to insert the IV% column (after Delta)
            const deltaHeader = Array.from(headerRow.querySelectorAll('th')).find(th => th.textContent === 'Delta');
            if (deltaHeader) {
                // Create and insert the IV% header after Delta
                const ivHeader = document.createElement('th');
                ivHeader.textContent = 'IV%';
                deltaHeader.after(ivHeader);
            }
        }
    }
    
    cleanupTooltips(tbody);
    tbody.innerHTML = '';
    
    let atLeastOneRowAdded = false;
    
    console.log(`Processing ${Object.keys(tickersData).length} tickers for ${optionType} table`);
    console.log('Custom tickers:', [...customTickers]);
    
    // Process each ticker
    Object.keys(tickersData).forEach(ticker => {
        if (addTickerRowToTable(tableId, optionType, ticker)) {
            atLeastOneRowAdded = true;
        }
    });
    
    // If no rows were added, show a "no data" message
    if (!atLeastOneRowAdded) {
        console.log(`No ${optionType} rows added to the table`);
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="13" class="text-center p-3">
                <div class="alert alert-info m-0">
                    ${optionType === 'CALL' ? tr('options.noCoveredCalls') : tr('options.noCashSecuredPuts')}
                    ${optionType === 'PUT' ? tr('options.addTickerHint') : ''}
                </div>
            </td>
        `;
        tbody.appendChild(row);
    }

    initializeTooltips(tbody);
}

/**
 * Fetch all tickers and their data with progressive UI updates
 */
async function loadTickers() {
    // Load custom tickers from localStorage
    try {
        const savedTickers = localStorage.getItem('customTickers');
        if (savedTickers) {
            const tickersArray = JSON.parse(savedTickers);
            customTickers = new Set(tickersArray);
            console.log(`Loaded ${customTickers.size} custom tickers:`, [...customTickers]);
        }
    } catch (error) {
        console.error('Error loading custom tickers:', error);
    }
    
    // Load saved OTM settings
    loadOtmSettings();

    // Initialize the table structure first
    const optionsTableContainer = document.getElementById('options-table-container');
    if (!optionsTableContainer) {
        console.error("Options table container not found");
        return;
    }
    
    // Remember which tab was active
    const putTabWasActive = document.querySelector('#put-options-tab.active') !== null ||
                           document.querySelector('#put-options-section.active') !== null;
    
    // Set up the basic table structure with tabs
    const tabsHTML = `
        <ul class="nav nav-tabs mb-3" id="options-tabs" role="tablist">
            <li class="nav-item" role="presentation">
                <button class="nav-link ${putTabWasActive ? '' : 'active'}" id="call-options-tab" data-bs-toggle="tab" data-bs-target="#call-options-section" type="button" role="tab" aria-controls="call-options-section" aria-selected="${putTabWasActive ? 'false' : 'true'}">
                    ${tr('options.coveredCalls')}
                </button>
            </li>
            <li class="nav-item" role="presentation">
                <button class="nav-link ${putTabWasActive ? 'active' : ''}" id="put-options-tab" data-bs-toggle="tab" data-bs-target="#put-options-section" type="button" role="tab" aria-controls="put-options-section" aria-selected="${putTabWasActive ? 'true' : 'false'}">
                    ${tr('options.cashSecuredPuts')}
                </button>
            </li>
        </ul>
        
        <div class="tab-content" id="options-tabs-content">
            <div class="tab-pane fade ${putTabWasActive ? '' : 'show active'}" id="call-options-section" role="tabpanel" aria-labelledby="call-options-tab">
                <div class="options-toolbar justify-content-end mb-2">
                    <button class="btn btn-sm btn-outline-success me-2" id="sell-all-calls">
                        <i class="bi bi-check2-all"></i> ${tr('common.addAll')}
                    </button>
                    <button class="btn btn-sm btn-outline-primary" id="refresh-all-calls">
                        <i class="bi bi-arrow-repeat"></i> ${tr('options.refreshAllCalls')}
                    </button>
                </div>
                <div class="table-responsive">
                    <table class="table table-striped table-hover table-sm options-opportunities-table" id="call-options-table">
                        <thead>
                            <tr>
                                <th>${tr('common.ticker')}</th>
                                <th>${tr('common.shares')}</th>
                                <th>${tr('options.stockPrice')}</th>
                                <th>${tr('options.otm')}</th>
                                <th>${tr('common.strike')}</th>
                                <th>${tr('common.expiration')}</th>
                                <th>${tr('options.midPrice')}</th>
                                <th>${tr('common.delta')}</th>
                                <th>${tr('common.iv')}</th>
                                <th>${tr('common.qty')}</th>
                                <th>${tr('options.totalPremium')}</th>
                                <th>${tr('common.action')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td colspan="12" class="text-center p-3">
                                    <div class="spinner-border text-primary" role="status"></div>
                                    <p class="mt-2">${tr('options.loading')}</p>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            
            <div class="tab-pane fade ${putTabWasActive ? 'show active' : ''}" id="put-options-section" role="tabpanel" aria-labelledby="put-options-tab">
                <div class="options-toolbar justify-content-between mb-2">
                    <div class="option-search">
                        <div class="input-group input-group-sm">
                            <input type="text" class="form-control" id="custom-ticker-input" 
                                placeholder="${tr('options.addTickerPlaceholder')}" maxlength="5">
                            <button class="btn btn-outline-primary" id="add-custom-ticker">
                                <i class="bi bi-plus-circle"></i> ${tr('common.add')}
                            </button>
                        </div>
                    </div>
                    <div class="options-toolbar-actions">
                    <button class="btn btn-sm btn-outline-success me-2" id="sell-all-puts">
                        <i class="bi bi-check2-all"></i> ${tr('common.addAll')}
                    </button>
                    <button class="btn btn-sm btn-outline-primary" id="refresh-all-puts">
                        <i class="bi bi-arrow-repeat"></i> ${tr('options.refreshAllPuts')}
                    </button>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-striped table-hover table-sm options-opportunities-table" id="put-options-table">
                        <thead>
                            <tr>
                                <th>${tr('common.ticker')}</th>
                                <th>${tr('options.stockPrice')}</th>
                                <th>${tr('options.otm')}</th>
                                <th>${tr('common.strike')}</th>
                                <th>${tr('common.expiration')}</th>
                                <th>${tr('options.midPrice')}</th>
                                <th>${tr('common.delta')}</th>
                                <th>${tr('common.iv')}</th>
                                <th>${tr('common.qty')}</th>
                                <th>${tr('options.totalPremium')}</th>
                                <th>${tr('options.cashRequired')}</th>
                                <th>${tr('common.action')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr>
                                <td colspan="12" class="text-center p-3">
                                    <div class="spinner-border text-primary" role="status"></div>
                                    <p class="mt-2">${tr('options.loading')}</p>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    `;
    
    // Add the tabs and tables to the container
    optionsTableContainer.innerHTML = tabsHTML;
    
    // Set up event listeners
    addOptionsTableEventListeners();
    setupCustomTickerEventListeners();
    
    // Fetch portfolio data first to get latest cash balance
    try {
        portfolioSummary = await fetchAccountData();
        console.log("Portfolio summary:", portfolioSummary);
    } catch (error) {
        console.error('Error fetching portfolio data:', error);
    }
    
    // Fetch tickers
    const data = await fetchTickers();
    let portfolioTickers = [];
    
    if (data && data.tickers) {
        portfolioTickers = data.tickers;
        console.log(`Fetched ${portfolioTickers.length} portfolio tickers, loading their data...`);
    } else {
        console.log("No portfolio tickers fetched");
    }
    
    // Create a combined list of all tickers (portfolio + custom)
    const allTickers = [...new Set([...portfolioTickers, ...customTickers])];
    console.log(`Total tickers to load: ${allTickers.length} (portfolio: ${portfolioTickers.length}, custom: ${customTickers.size})`);
    
    // Clear initial loading message from tables
    document.querySelector('#call-options-table tbody').innerHTML = '';
    document.querySelector('#put-options-table tbody').innerHTML = '';
    
    // Load a small number of tickers concurrently and render each as it finishes.
    const totalTickers = allTickers.length;
    await runWithConcurrency(allTickers, REFRESH_CONCURRENCY, async (ticker, i) => {
        
        // Initialize ticker data structure if not exists
        if (!tickersData[ticker]) {
            console.log(`Initializing data structure for ticker ${ticker}`);
            tickersData[ticker] = {
                data: {
                    data: {}
                },
                callOtmPercentage: 10, // Default OTM percentage for calls
                putOtmPercentage: 10, // Default OTM percentage for puts
                putQuantity: 1 // Default put quantity
            };
            
            // Initialize nested structure for this ticker
            tickersData[ticker].data.data[ticker] = {
                stock_price: 0,
                position: 0,
                calls: [],
                puts: []
            };
        }
        
        // Show loading message for current ticker
        const progressMessage = tr('options.loadingTicker', {
            ticker,
            current: i + 1,
            total: totalTickers
        });
        const callStatusRow = document.createElement('tr');
        callStatusRow.id = `call-status-${ticker}`;
        callStatusRow.innerHTML = `
            <td colspan="13" class="text-center">
                <div class="d-flex align-items-center justify-content-center">
                    <div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>
                    <span>${progressMessage}</span>
                </div>
            </td>
        `;
        document.querySelector('#call-options-table tbody').appendChild(callStatusRow);
        
        const putStatusRow = document.createElement('tr');
        putStatusRow.id = `put-status-${ticker}`;
        putStatusRow.innerHTML = `
            <td colspan="13" class="text-center">
                <div class="d-flex align-items-center justify-content-center">
                    <div class="spinner-border spinner-border-sm text-primary me-2" role="status"></div>
                    <span>${progressMessage}</span>
                </div>
            </td>
        `;
        document.querySelector('#put-options-table tbody').appendChild(putStatusRow);
        
        // Fetch data for the current ticker
        try {
            await refreshOptionsForTicker(ticker, false);
            console.log(`Successfully loaded data for ticker: ${ticker}`);
            
            // Remove status rows
            document.getElementById(`call-status-${ticker}`)?.remove();
            document.getElementById(`put-status-${ticker}`)?.remove();
            
            // Add ticker rows to both tables if applicable
            addTickerRowToTable('call-options-table', 'CALL', ticker);
            addTickerRowToTable('put-options-table', 'PUT', ticker);
            
            // Add event listeners for the newly added rows
            addOtmInputEventListeners();
            addExpirationSelectEventListeners();
            addPutQtyInputEventListeners();
            addMidPriceInputEventListeners();
            
        } catch (error) {
            console.error(`Error loading data for ticker ${ticker}:`, error);
            
            // Update status rows to show error
            const errorMessage = tr('options.errorLoadingTicker', { ticker, message: error.message });
            if (document.getElementById(`call-status-${ticker}`)) {
                document.getElementById(`call-status-${ticker}`).innerHTML = `
                    <td colspan="13" class="text-center text-danger">
                        <i class="bi bi-exclamation-triangle"></i> ${errorMessage}
                    </td>
                `;
            }
            if (document.getElementById(`put-status-${ticker}`)) {
                document.getElementById(`put-status-${ticker}`).innerHTML = `
                    <td colspan="13" class="text-center text-danger">
                        <i class="bi bi-exclamation-triangle"></i> ${errorMessage}
                    </td>
                `;
            }
            
            // Remove error messages after a delay
            setTimeout(() => {
                document.getElementById(`call-status-${ticker}`)?.remove();
                document.getElementById(`put-status-${ticker}`)?.remove();
            }, 3000);
        }
        
        // Calculate and update earnings summary after each ticker is processed
        const earningsSummary = calculateEarningsSummary();
        displayEarningsSummary(earningsSummary);
    });
    
    // Clean up any remaining status rows
    document.querySelectorAll('tr[id^="call-status-"], tr[id^="put-status-"]').forEach(row => row.remove());
    
    // Check if any rows were added, if not show "no data" message
    if (document.querySelector('#call-options-table tbody').children.length === 0) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="13" class="text-center p-3">
                <div class="alert alert-info m-0">
                    ${tr('options.noCoveredCalls')}
                </div>
            </td>
        `;
        document.querySelector('#call-options-table tbody').appendChild(row);
    }
    
    if (document.querySelector('#put-options-table tbody').children.length === 0) {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td colspan="13" class="text-center p-3">
                <div class="alert alert-info m-0">
                    ${tr('options.noCashSecuredPuts')}
                    ${tr('options.addTickerHint')}
                </div>
            </td>
        `;
        document.querySelector('#put-options-table tbody').appendChild(row);
    }
    
    // Calculate and display earnings summary once after all tickers are processed
    const earningsSummary = calculateEarningsSummary();
    displayEarningsSummary(earningsSummary);
    
    console.log("All ticker data loaded and table updated incrementally");
}

document.addEventListener('languageChanged', () => {
    const optionsTableContainer = document.getElementById('options-table-container');
    if (!optionsTableContainer || Object.keys(tickersData).length === 0) return;

    updateOptionsTable();
    addOptionsTableEventListeners();
});

// Export functions
export {
    loadTickers,
    refreshOptionsForTicker,
    refreshOptionsForTickerByType,
    refreshAllOptions,
    sellAllOptions
}; 

/**
 * Display the earnings summary in a compact format
 * @param {Object} summary - The earnings summary to display
 */
function displayEarningsSummary(summary) {
    const optionsTableContainer = document.getElementById('options-table-container');
    if (!optionsTableContainer) return;
    
    // Remove any existing earnings summary to prevent duplicates
    const existingSummary = optionsTableContainer.querySelector('.card.shadow-sm.mt-4');
    if (existingSummary) {
        existingSummary.remove();
    }
    
    // Create a new, more compact earnings summary table
    const earningsSummaryHTML = `
        <div class="card shadow-sm mt-4">
            <div class="card-header d-flex justify-content-between align-items-center bg-light py-2">
                <h6 class="mb-0">${tr('earnings.estimatedSummary')}</h6>
            </div>
            <div class="card-body py-2">
                <table class="table table-sm table-borderless mb-0">
                    <tbody>
                        <tr>
                            <td width="14%" class="fw-bold">${tr('earnings.weeklyPremium')}</td>
                            <td width="14%">${tr('earnings.calls')} ${formatCurrency(summary.totalWeeklyCallPremium)}</td>
                            <td width="14%">${tr('earnings.puts')} ${formatCurrency(summary.totalWeeklyPutPremium)}</td>
                            <td width="18%" class="fw-bold">${tr('earnings.total')} ${formatCurrency(summary.totalWeeklyPremium)}</td>
                            <td width="14%" class="fw-bold">${tr('earnings.weeklyReturn')}</td>
                            <td width="12%">${formatPercentage(summary.weeklyReturn)}</td>
                            <td width="14%" class="fw-bold text-success">${tr('earnings.annual')} ${formatPercentage(summary.projectedAnnualReturn)}</td>
                        </tr>
                        <tr>
                            <td class="fw-bold">${tr('earnings.projectedIncome')}</td>
                            <td colspan="6">${formatCurrency(summary.projectedAnnualEarnings)}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            <div class="card-footer py-1">
                <small class="text-muted">${tr('earnings.projectedNote')}</small>
            </div>
        </div>
    `;
    
    // Append the earnings summary to the options table container
    optionsTableContainer.insertAdjacentHTML('beforeend', earningsSummaryHTML);
}

/**
 * Load OTM settings from localStorage
 */
function loadOtmSettings() {
    try {
        const savedSettings = localStorage.getItem('otmSettings');
        if (savedSettings) {
            const settings = JSON.parse(savedSettings);
            console.log('Loaded OTM settings from localStorage:', settings);
            
            // Apply settings to tickersData
            Object.keys(settings).forEach(ticker => {
                if (!tickersData[ticker]) {
                    tickersData[ticker] = {};
                }
                
                tickersData[ticker].callOtmPercentage = settings[ticker].callOtmPercentage || 10;
                tickersData[ticker].putOtmPercentage = settings[ticker].putOtmPercentage || 10;
                tickersData[ticker].putQuantity = settings[ticker].putQuantity || 1;
                
                console.log(`Applied saved settings for ${ticker}: Call OTM=${tickersData[ticker].callOtmPercentage}%, Put OTM=${tickersData[ticker].putOtmPercentage}%, Put Qty=${tickersData[ticker].putQuantity}`);
            });
        }
    } catch (error) {
        console.error('Error loading OTM settings:', error);
    }
} 
