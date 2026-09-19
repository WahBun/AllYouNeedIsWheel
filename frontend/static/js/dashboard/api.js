/**
 * API interaction module for dashboard
 * Handles all data fetching and API calls
 */
import { showAlert } from '../utils/alerts.js';

async function fetchJsonWithTimeout(url, timeoutMs = 8000) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
    try {
        const response = await fetch(url, {
            cache: 'no-store',
            signal: controller.signal,
            headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache'
            }
        });
        if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            throw new Error(payload.error || `HTTP error ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        if (error.name === 'AbortError') {
            throw new Error('Request timed out');
        }
        throw error;
    } finally {
        window.clearTimeout(timeout);
    }
}

/**
 * Fetch account and portfolio data
 * @returns {Promise} Promise with account data
 */
async function fetchAccountData() {
    try {
        const response = await fetch('/api/portfolio');
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching account data:', error);
        showAlert(`Error fetching account data: ${error.message}`, 'danger');
        return null;
    }
}

/**
 * Fetch positions data
 * @returns {Promise} Promise with positions data
 */
async function fetchPositions() {
    try {
        const response = await fetch('/api/portfolio/positions');
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching positions:', error);
        showAlert(`Error fetching positions: ${error.message}`, 'danger');
        return null;
    }
}

async function fetchPortfolioBootstrap() {
    return fetchJsonWithTimeout('/api/portfolio/bootstrap', 10000);
}

async function fetchLivePositions() {
    return fetchJsonWithTimeout('/api/portfolio/live', 3500);
}

/**
 * Fetch weekly option income data
 * @returns {Promise} Promise with weekly income data from short options expiring this coming Friday
 */
async function fetchWeeklyOptionIncome() {
    try {
        const response = await fetch('/api/portfolio/weekly-income');
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        return await response.json();
    } catch (error) {
        console.error('Error fetching weekly option income:', error);
        showAlert(`Error fetching weekly income data: ${error.message}`, 'danger');
        return {
            positions: [],
            total_income: 0,
            positions_count: 0,
            error: error.message
        };
    }
}

/**
 * Fetch option data for a ticker
 * @param {string} ticker - The stock symbol
 * @param {number} otmPercentage - The OTM percentage value (default: 10)
 * @param {string} optionType - The option type to filter by ('CALL' or 'PUT')
 * @param {string} expiration - The specific expiration date to filter by
 * @returns {Promise} Promise with option data
 */
async function fetchOptionData(ticker, otmPercentage = 10, optionType = null, expiration = null) {
    try {
        const timestamp = new Date().getTime();
        let url = `/api/options/otm?tickers=${encodeURIComponent(ticker)}&otm=${otmPercentage}&real_time=true&options_only=true&t=${timestamp}`;
        
        // Add option type to URL if provided
        if (optionType) {
            url += `&optionType=${optionType}`;
        }
        
        // Add expiration date to URL if provided
        if (expiration) {
            url += `&expiration=${encodeURIComponent(expiration)}`;
        }
        
        const response = await fetch(url, {
            headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        
        // Get response as text first to fix any NaN values
        const responseText = await response.text();
        
        // Replace any NaN values with null (or 0) for proper JSON parsing
        let sanitizedResponse = responseText
            .replace(/:NaN/g, ':null')
            .replace(/=NaN/g, '=null')
            .replace(/: NaN/g, ': null');
            
        console.log(`Sanitized response for ${ticker} to fix NaN values`);
        
        // Parse the sanitized JSON
        try {
            return JSON.parse(sanitizedResponse);
        } catch (parseError) {
            console.error(`JSON parse error for ${ticker} even after sanitizing:`, parseError);
            console.error('Response text:', sanitizedResponse.substring(0, 200) + '...');
            throw parseError;
        }
    } catch (error) {
        console.error(`Error fetching options for ${ticker}:`, error);
        showAlert(`Error fetching options for ${ticker}: ${error.message}`, 'danger');
        
        // Return a fallback empty structure to prevent further errors
        return {
            status: "error",
            message: error.message,
            data: {
                [ticker]: {
                    stock_price: 0,
                    position: 0,
                    calls: [],
                    puts: []
                }
            }
        };
    }
}

/**
 * Fetch all tickers for stock positions only
 * @returns {Promise} Promise with tickers data
 */
async function fetchTickers() {
    try {
        // Only fetch stock positions by using the type=STK filter
        const response = await fetch('/api/portfolio/positions?type=STK');
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const positionsData = await response.json();
        
        // Extract unique ticker symbols from stock positions
        const tickers = positionsData.map(position => position.symbol);
        
        return { tickers: tickers };
    } catch (error) {
        console.error('Error fetching tickers:', error);
        showAlert(`Error fetching tickers: ${error.message}`, 'danger');
        return { tickers: [] };
    }
}

/**
 * Fetch pending orders from the API
 * @param {boolean} executed - Whether to fetch executed orders (true) or pending orders (false)
 * @param {boolean} isRollover - Whether to fetch only rollover orders
 * @returns {Promise<Object>} Pending orders data
 */
async function fetchPendingOrders(executed = false, isRollover = false) {
    try {
        // Construct the URL with query parameters
        let url = `/api/options/pending-orders?executed=${executed}`;
        
        // Add isRollover parameter if specified
        if (isRollover) {
            url += `&isRollover=true`;
        }
        
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        console.log('Pending orders API response:', data);
        return data;
    } catch (error) {
        console.error('Error fetching pending orders:', error);
        return null;
    }
}

/**
 * Save an option order
 * @param {Object} orderData - The order data
 * @returns {Promise} Promise with the saved order
 */
async function saveOptionOrder(orderData) {
    try {
        const response = await fetch('/api/options/order', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-All-You-Need-Is-Wheel': '1',
            },
            body: JSON.stringify(orderData)
        });
        
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            return {
                success: false,
                error: data.error || data.message || `HTTP error ${response.status}`,
                status: data.status,
                execution_details: data.execution_details
            };
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error saving order:', error);
        showAlert(`Error saving order: ${error.message}`, 'danger');
        throw error;
    }
}

/**
 * Cancel an order
 * @param {string} orderId - The order ID to cancel
 * @returns {Promise} Promise with the cancelled order
 */
async function cancelOrder(orderId) {
    try {
        // Use the new cancellation endpoint for active orders
        const response = await fetch(`/api/options/cancel/${orderId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-All-You-Need-Is-Wheel': '1'
            }
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to cancel order');
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error cancelling order:', error);
        showAlert(`Error cancelling order: ${error.message}`, 'danger');
        throw error;
    }
}

/**
 * Update the limit price of an order that has not yet been sent to IB.
 */
async function updatePendingOrderPremium(orderId, premium) {
    const response = await fetch(`/api/options/order/${orderId}/premium`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'X-All-You-Need-Is-Wheel': '1'
        },
        body: JSON.stringify({ premium })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || `HTTP error ${response.status}`);
    }
    return data;
}

/**
 * Check status of pending/processing orders with TWS
 * @returns {Promise} Promise with updated orders
 */
async function checkOrderStatus(forceDiscovery = false) {
    try {
        const response = await fetch('/api/options/check-orders', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-All-You-Need-Is-Wheel': '1'
            },
            body: JSON.stringify({ force_discovery: forceDiscovery })
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to check order status');
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error checking order status:', error);
        // Don't show alert for this regular background operation
        throw error;
    }
}

/**
 * Execute an order
 * @param {number} orderId - The order ID to execute
 * @returns {Promise<Object>} Result object with success/error info
 */
async function executeOrder(orderId) {
    try {
        const response = await fetch(`/api/options/execute/${orderId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-All-You-Need-Is-Wheel': '1',
            }
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            return {
                success: false,
                error: data.error || data.message || `HTTP error ${response.status}`,
                status: data.status,
                execution_details: data.execution_details
            };
        }

        return data;
    } catch (error) {
        console.error('Error executing order:', error);
        return { success: false, error: error.message };
    }
}

/**
 * Fetch stock prices for one or more tickers
 * @param {Array|string} tickers - Array of ticker symbols or comma-separated string
 * @returns {Promise} Promise with stock prices data
 */
async function fetchStockPrices(tickers) {
    try {
        // Format tickers parameter
        let tickersParam = '';
        if (Array.isArray(tickers)) {
            tickersParam = tickers.join(',');
        } else {
            tickersParam = tickers;
        }
        
        if (!tickersParam) {
            throw new Error('No tickers provided');
        }
        
        // Add timestamp to avoid caching
        const timestamp = new Date().getTime();
        const url = `/api/options/stock-price?tickers=${encodeURIComponent(tickersParam)}&t=${timestamp}`;
        
        const response = await fetch(url, {
            headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.status === 'success' && result.data) {
            return result.data;
        } else {
            throw new Error(result.error || 'Failed to fetch stock prices');
        }
    } catch (error) {
        console.error('Error fetching stock prices:', error);
        return {};
    }
}

/**
 * Fetch available option expiration dates for a ticker
 * @param {string} ticker - The ticker symbol
 * @returns {Promise<Object>} - Promise resolving to an object with expiration dates
 */
async function fetchOptionExpirations(ticker) {
    try {
        const url = `/api/options/expirations?ticker=${encodeURIComponent(ticker)}`;
        const response = await fetch(url);
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Failed to fetch option expirations: ${errorText}`);
        }
        
        return await response.json();
    } catch (error) {
        console.error('Error fetching option expirations:', error);
        throw error;
    }
}

// Export all API functions
export {
    fetchAccountData,
    fetchPositions,
    fetchPortfolioBootstrap,
    fetchLivePositions,
    fetchWeeklyOptionIncome,
    fetchOptionData,
    fetchTickers,
    fetchPendingOrders,
    saveOptionOrder,
    cancelOrder,
    updatePendingOrderPremium,
    executeOrder,
    checkOrderStatus,
    fetchStockPrices,
    fetchOptionExpirations
}; 
