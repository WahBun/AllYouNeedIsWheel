/**
 * Orders module for handling pending orders
 */
import { fetchPendingOrders, cancelOrder, executeOrder, checkOrderStatus, fetchWeeklyOptionIncome } from './api.js?v=safety-1';
import { showAlert, getBadgeColor } from '../utils/alerts.js?v=close-position-1';
import { formatCurrency } from './account.js?v=close-position-1';

// Store orders data
let pendingOrdersData = [];
let weeklyOptionIncomeData = {}; // Changed from filledOrdersData

// Auto-refresh timer
let autoRefreshTimer = null;
const AUTO_REFRESH_INTERVAL = 10000; // 10 seconds
const ACTIVE_ORDER_STATUSES = ['pending', 'submitting', 'processing', 'canceling', 'unknown'];
const TRACKED_ORDER_STATUSES = ['submitting', 'processing', 'canceling', 'unknown'];
const TERMINAL_ORDER_STATUSES = ['executed', 'canceled', 'rejected'];
const orderExecutionInFlight = new Set();

function tr(key, replacements = {}) {
    return window.t ? window.t(key, replacements) : key;
}

/**
 * Format date for display
 * @param {string|number} dateString - The date string or timestamp to format
 * @returns {string} The formatted date
 */
function formatDate(dateString) {
    if (!dateString) return '';
    
    // Handle Unix timestamp (seconds since epoch)
    if (typeof dateString === 'number' || !isNaN(parseInt(dateString))) {
        // Convert to milliseconds if it's in seconds
        const timestamp = parseInt(dateString) * (dateString.toString().length <= 10 ? 1000 : 1);
        
        // Check if this is a Unix epoch date (Jan 1, 1970) or very close to it
        if (timestamp < 86400000) { // Less than 1 day from epoch
            return ''; // Return empty string instead of showing 1970/1/1
        }
        
        return new Date(timestamp).toLocaleString();
    }
    
    // Handle regular date string
    const date = new Date(dateString);
    
    // Check if this is a valid date and not Jan 1, 1970
    if (isNaN(date.getTime()) || date.getFullYear() === 1970) {
        return '';
    }
    
    return date.toLocaleString();
}

/**
 * Check if a date is within the current week
 * @param {Date|string|number} date - The date to check
 * @returns {boolean} True if the date is within the current week
 */
function isWithinCurrentWeek(date) {
    if (!date) return false;
    
    // Convert to Date object if it's not already
    const dateObj = typeof date === 'object' ? date : new Date(date);
    
    // If date is invalid, return false
    if (isNaN(dateObj.getTime())) return false;
    
    const now = new Date();
    
    // Get the first day of the current week (Sunday)
    const firstDayOfWeek = new Date(now);
    firstDayOfWeek.setDate(now.getDate() - now.getDay());
    firstDayOfWeek.setHours(0, 0, 0, 0);
    
    // Get the last day of the current week (Saturday)
    const lastDayOfWeek = new Date(firstDayOfWeek);
    lastDayOfWeek.setDate(firstDayOfWeek.getDate() + 6);
    lastDayOfWeek.setHours(23, 59, 59, 999);
    
    // Check if the date is within the current week
    return dateObj >= firstDayOfWeek && dateObj <= lastDayOfWeek;
}

/**
 * Update the pending orders table with data
 */
function updatePendingOrdersTable() {
    const pendingOrdersTable = document.getElementById('pending-orders-table');
    if (!pendingOrdersTable) return;
    
    // Clear the table
    pendingOrdersTable.innerHTML = '';
    
    const visibleOrders = pendingOrdersData.filter(order => ACTIVE_ORDER_STATUSES.includes(order.status));
    
    if (visibleOrders.length === 0) {
        pendingOrdersTable.innerHTML = `<tr><td colspan="8" class="text-center">${tr('orders.noPending')}</td></tr>`;
        return;
    }
    
    // Sort orders by timestamp (newest first)
    visibleOrders.sort((a, b) => {
        // Handle different timestamp formats
        const timestampA = a.timestamp || a.created_at;
        const timestampB = b.timestamp || b.created_at;
        
        if (typeof timestampA === 'number' && typeof timestampB === 'number') {
            return timestampB - timestampA;
        } else {
            return new Date(timestampB) - new Date(timestampA);
        }
    });
    
    // Add each order to the table
    visibleOrders.forEach(order => {
        const row = document.createElement('tr');
        
        // Format the strike price
        const strike = order.strike ? `$${order.strike}` : 'N/A';
        
        // Format the premium
        const premium = order.premium ? formatCurrency(order.premium) : 'N/A';
        
        // Format the created date
        const createdAt = formatDate(order.timestamp || order.created_at);
        
        // Get the badge color for status
        const badgeColor = getBadgeColor(order.status);
        
        // IB order information
        const ibOrderId = order.ib_order_id || 'Not sent';
        const ibStatus = order.ib_status || '-';
        const errorMessage = order.error_message || order.error || '';
        
        // Format execution price if available
        const avgFillPrice = order.avg_fill_price ? formatCurrency(order.avg_fill_price) : '-';
        const commission = order.commission ? formatCurrency(order.commission) : '-';
        
        // Set quantity or default to 1
        const quantity = order.quantity || 1;
        const intent = String(order.intent || 'OPEN').toUpperCase();
        const orderSide = intent === 'CLOSE'
            ? (order.action === 'BUY' ? tr('close.buyToClose') : tr('close.sellToClose'))
            : (order.action === 'SELL' ? tr('orders.sellToOpen') : tr('orders.buyToOpen'));
        const typeHtml = `
            <div>${order.option_type}</div>
            <small class="${intent === 'CLOSE' ? 'text-primary' : 'text-muted'}">${orderSide}</small>
        `;
        
        // Status area with IB info
        let statusHtml = `
            <span class="badge bg-${badgeColor}">${order.status}</span>
        `;
        
        // Add date only if it's not empty
        if (createdAt) {
            statusHtml += `
                <br>
                <small class="text-muted">${createdAt}</small>
            `;
        }
        
        // Add IB info if order has been executed
        if (order.status !== 'pending') {
            statusHtml += `
                <br>
                <small class="text-muted mt-1">
                    <strong>${tr('orders.ibId')}</strong> ${ibOrderId}
                </small>
                <br>
                <small class="text-muted">
                    <strong>${tr('orders.ibStatus')}</strong> ${ibStatus}
                </small>
            `;
            
            // Add fill price and commission if order is executed
            if (order.status === 'executed' && order.avg_fill_price) {
                statusHtml += `
                    <br>
                    <small class="text-muted">
                        <strong>${tr('orders.fillPrice')}</strong> ${avgFillPrice}
                    </small>
                `;
                
                if (order.commission) {
                    statusHtml += `
                        <br>
                        <small class="text-muted">
                            <strong>${tr('orders.commission')}</strong> ${commission}
                        </small>
                    `;
                }
            }

            if (errorMessage) {
                statusHtml += `
                    <br>
                    <small class="text-danger">
                        ${errorMessage}
                    </small>
                `;
            }
        }
        
        // Create quantity input or display based on order status
        const quantityCell = order.status === 'pending' && intent !== 'CLOSE'
            ? `<input type="number" class="form-control form-control-sm quantity-input" data-order-id="${order.id}" value="${quantity}" min="1" max="100">`
            : `${quantity}`;
        
        // Create the row HTML
        row.innerHTML = `
            <td>${order.ticker}</td>
            <td>${typeHtml}</td>
            <td>${strike}</td>
            <td>${order.expiration || 'N/A'}</td>
            <td>${premium}</td>
            <td>${quantityCell}</td>
            <td>${statusHtml}</td>
            <td>
                <div class="btn-group btn-group-sm">
                    <button class="btn btn-outline-primary execute-order" data-order-id="${order.id}" ${order.status !== 'pending' ? 'disabled' : ''}>
                        <i class="bi bi-play-fill"></i> ${tr('common.execute')}
                    </button>
                    <button class="btn btn-outline-danger cancel-order" data-order-id="${order.id}" ${TERMINAL_ORDER_STATUSES.includes(order.status) ? 'disabled' : ''}>
                        <i class="bi bi-x-circle"></i> ${tr('common.cancel')}
                    </button>
                </div>
            </td>
        `;
        
        pendingOrdersTable.appendChild(row);
    });
    
    // Add event listeners
    addOrdersTableEventListeners();
    
    // Also update the filled orders if any order was executed
    updateFilledOrdersTable();
}

/**
 * Update the filled orders table and calculate weekly earnings
 */
function updateFilledOrdersTable() {
    const filledOrdersTable = document.getElementById('filled-orders-table');
    if (!filledOrdersTable) {
        console.error('Could not find filled-orders-table element in the DOM');
        return;
    }
    
    console.log(`Updating weekly option income table with ${weeklyOptionIncomeData.positions ? weeklyOptionIncomeData.positions.length : 0} positions`);
    
    // Clear the table
    filledOrdersTable.innerHTML = '';
    
    // Check if we have positions data
    if (!weeklyOptionIncomeData.positions || weeklyOptionIncomeData.positions.length === 0) {
        console.log('No weekly option income data to display');
        filledOrdersTable.innerHTML = `<tr><td colspan="9" class="text-center">${tr('orders.noWeekly')}</td></tr>`;
        
        // Update summary with zeros
        updateWeeklyEarningsSummary([], 0, 0);
        return;
    }
    
    // Get the positions array
    const positions = weeklyOptionIncomeData.positions;
    
    // Add debug logging to see what we received
    console.log('Weekly options data received:', weeklyOptionIncomeData);
    
    // Group positions by option type - supporting both formats (C/P and CALL/PUT)
    const callPositions = positions.filter(p => 
        p.option_type === 'C' || p.option_type === 'CALL' || p.option_type === 'Call');
    const putPositions = positions.filter(p => 
        p.option_type === 'P' || p.option_type === 'PUT' || p.option_type === 'Put');
    
    // Log what we filtered
    console.log(`Filtered ${callPositions.length} call options and ${putPositions.length} put options`);
    if (callPositions.length + putPositions.length === 0) {
        console.warn('No positions matched our filtering criteria. Original option types:', 
            positions.map(p => p.option_type));
        filledOrdersTable.innerHTML = `<tr><td colspan="9" class="text-center">${tr('orders.noWeekly')}</td></tr>`;
        return;
    }
    
    // Add header for CALL options if there are any
    if (callPositions.length > 0) {
        const callHeader = document.createElement('tr');
        callHeader.className = 'table-primary';
        callHeader.innerHTML = `<td colspan="9" class="fw-bold">${tr('orders.callOptions')} (${callPositions.length})</td>`;
        filledOrdersTable.appendChild(callHeader);
        
        // Add each CALL position
        addPositionsToTable(callPositions, filledOrdersTable);
    }
    
    // Add header for PUT options if there are any
    if (putPositions.length > 0) {
        const putHeader = document.createElement('tr');
        putHeader.className = 'table-warning';
        putHeader.innerHTML = `<td colspan="9" class="fw-bold">${tr('orders.putOptions')} (${putPositions.length})</td>`;
        filledOrdersTable.appendChild(putHeader);
        
        // Add each PUT position
        addPositionsToTable(putPositions, filledOrdersTable);
    }
    
    // Update the weekly earnings summary
    updateWeeklyEarningsSummary(positions, weeklyOptionIncomeData.total_income || 0, weeklyOptionIncomeData.total_put_notional || 0);
}

/**
 * Update the weekly earnings summary display
 * @param {Array} positions - Array of positions expiring this coming Friday
 * @param {number} totalIncome - Total income from these positions
 * @param {number} totalPutNotional - Total notional value if all PUTs are assigned
 */
function updateWeeklyEarningsSummary(positions, totalIncome, totalPutNotional) {
    const positionCount = positions.length;
    const averageIncome = positionCount > 0 ? totalIncome / positionCount : 0;
    
    // Update the display elements
    document.getElementById('weekly-earnings-total').textContent = formatCurrency(totalIncome);
    document.getElementById('weekly-order-count').textContent = positionCount;
    document.getElementById('weekly-average-premium').textContent = formatCurrency(averageIncome);
    document.getElementById('weekly-notional-value').textContent = formatCurrency(totalPutNotional);
    
    // Add footer info about next Friday expiration date
    const footerInfo = document.getElementById('weekly-income-footer');
    if (footerInfo && weeklyOptionIncomeData.this_friday) {
        footerInfo.textContent = tr('orders.weeklyFooterWithDate', {
            date: weeklyOptionIncomeData.this_friday,
            notional: formatCurrency(totalPutNotional)
        });
    }
}

/**
 * Add event listeners to the orders table
 */
function addOrdersTableEventListeners() {
    // Add event listeners to Execute buttons
    const executeButtons = document.querySelectorAll('.execute-order');
    executeButtons.forEach(button => {
        button.addEventListener('click', event => {
            if (button.disabled) return;
            const orderId = event.target.dataset.orderId || event.target.closest('button').dataset.orderId;
            confirmOrderExecution(orderId, button);
        });
    });
    
    // Add event listeners to Cancel buttons
    const cancelButtons = document.querySelectorAll('.cancel-order');
    cancelButtons.forEach(button => {
        button.addEventListener('click', event => {
            if (button.disabled) return;
            const orderId = event.target.dataset.orderId || event.target.closest('button').dataset.orderId;
            cancelOrderById(orderId);
        });
    });
    
    // Add event listeners to quantity inputs
    const quantityInputs = document.querySelectorAll('.quantity-input');
    quantityInputs.forEach(input => {
        // Handle input change
        input.addEventListener('change', event => {
            const orderId = event.target.dataset.orderId;
            const newQuantity = parseInt(event.target.value, 10);
            if (orderId && !isNaN(newQuantity) && newQuantity > 0) {
                updateOrderQuantity(orderId, newQuantity);
            } else {
                // Reset to previous value if invalid
                const order = pendingOrdersData.find(o => o.id === parseInt(orderId, 10));
                if (order) {
                    event.target.value = order.quantity || 1;
                }
            }
        });
        
        // Handle blur event (when losing focus)
        input.addEventListener('blur', event => {
            const orderId = event.target.dataset.orderId;
            const newQuantity = parseInt(event.target.value, 10);
            if (orderId && !isNaN(newQuantity) && newQuantity > 0) {
                updateOrderQuantity(orderId, newQuantity);
            } else {
                // Reset to previous value if invalid
                const order = pendingOrdersData.find(o => o.id === parseInt(orderId, 10));
                if (order) {
                    event.target.value = order.quantity || 1;
                }
            }
        });
    });
    
    // Add listener to refresh pending orders button
    const refreshPendingOrdersButton = document.getElementById('refresh-pending-orders');
    if (refreshPendingOrdersButton) {
        refreshPendingOrdersButton.addEventListener('click', loadPendingOrders);
    }
    
    // Add listener to cancel all pending orders button
    const cancelAllPendingOrdersButton = document.getElementById('cancel-all-pending-orders');
    if (cancelAllPendingOrdersButton) {
        cancelAllPendingOrdersButton.addEventListener('click', cancelAllPendingOrders);
    }
    
    // Add listener to refresh filled orders button
    const refreshFilledOrdersButton = document.getElementById('refresh-filled-orders');
    if (refreshFilledOrdersButton) {
        refreshFilledOrdersButton.addEventListener('click', loadFilledOrders);
    }
}

function confirmOrderExecution(orderId, sourceButton) {
    const order = pendingOrdersData.find(item => item.id === parseInt(orderId, 10));
    if (!order || order.status !== 'pending') {
        showAlert('Only pending orders can be executed', 'warning');
        return;
    }

    const quantity = Number(order.quantity || 1);
    const price = Number(order.premium || 0);
    const multiplier = Number(order.contract_multiplier || 100);
    const total = price * multiplier * quantity;
    const intent = String(order.intent || 'OPEN').toUpperCase();
    const orderSide = intent === 'CLOSE'
        ? (order.action === 'BUY' ? tr('close.buyToClose') : tr('close.sellToClose'))
        : (order.action === 'SELL' ? tr('orders.sellToOpen') : tr('orders.buyToOpen'));
    const accountSuffix = order.account_id ? String(order.account_id).slice(-4) : '-';
    const summary = [
        `${tr('common.action')}: ${orderSide}`,
        `${tr('common.ticker')}: ${order.ticker} ${order.option_type}`,
        `${tr('common.strike')}: ${formatCurrency(order.strike)}`,
        `${tr('common.expiration')}: ${order.expiration}`,
        `${tr('common.quantity')}: ${quantity}`,
        `${tr('common.limitPrice')}: ${formatCurrency(price)} / share`,
        `${tr('close.orderTotal')}: ${formatCurrency(total)}`,
        ...(intent === 'CLOSE' ? [`${tr('close.account')}: •••• ${accountSuffix}`] : [])
    ].join('\n');

    const modalElement = document.getElementById('confirmOrderModal');
    const confirmButton = document.getElementById('confirmOrderModal-confirm');
    if (!modalElement || !confirmButton || !window.bootstrap?.Modal) {
        if (window.confirm(summary)) {
            executeOrderById(orderId, sourceButton);
        }
        return;
    }

    const modalBody = modalElement.querySelector('.modal-body');
    modalBody.textContent = summary;
    modalBody.style.whiteSpace = 'pre-line';
    const modal = bootstrap.Modal.getOrCreateInstance(modalElement);

    confirmButton.onclick = async () => {
        confirmButton.disabled = true;
        sourceButton.disabled = true;
        modal.hide();
        try {
            await executeOrderById(orderId, sourceButton);
        } finally {
            confirmButton.disabled = false;
        }
    };
    modal.show();
}

/**
 * Execute an order by ID
 * @param {string} orderId - The order ID to execute
 */
async function executeOrderById(orderId, sourceButton = null) {
    if (orderExecutionInFlight.has(orderId)) return;
    orderExecutionInFlight.add(orderId);
    if (sourceButton) sourceButton.disabled = true;

    try {
        // Execute the order
        const result = await executeOrder(orderId);
        const details = result.execution_details || {};
        
        // Update the order in pendingOrdersData with the IB information
        const orderIndex = pendingOrdersData.findIndex(order => order.id == orderId);
        if (orderIndex !== -1) {
            // Update the order with execution details
            pendingOrdersData[orderIndex].status = result.status || (result.success ? "processing" : "rejected");
            pendingOrdersData[orderIndex].executed = !ACTIVE_ORDER_STATUSES.includes(pendingOrdersData[orderIndex].status);
            
            // Add IB details from the response
            if (result.execution_details) {
                pendingOrdersData[orderIndex].ib_order_id = details.ib_order_id;
                pendingOrdersData[orderIndex].ib_status = details.ib_status;
                pendingOrdersData[orderIndex].error_code = details.error_code;
                pendingOrdersData[orderIndex].error_message = details.error_message;
                pendingOrdersData[orderIndex].filled = details.filled;
                pendingOrdersData[orderIndex].remaining = details.remaining;
                pendingOrdersData[orderIndex].avg_fill_price = details.avg_fill_price;
            } else {
                // Fallback if execution_details is not present
                pendingOrdersData[orderIndex].ib_order_id = result.ib_order_id || 'Unknown';
                pendingOrdersData[orderIndex].ib_status = 'Submitted';
            }
            
            // Update the table immediately
            updatePendingOrdersTable();
        }

        if (!result.success) {
            showAlert(result.error || result.message || 'Order rejected by IB', 'warning');
            await loadPendingOrders();
            return;
        }
        
        // Show success message
        showAlert(`Order sent to TWS (IB Order ID: ${result.ib_order_id || details.ib_order_id || '-'})`, 'success');
        
        // Start auto-refresh if not already running to track this order's status
        if ((result.status || 'processing') === 'processing') {
            startAutoRefresh();
        } else {
            await loadPendingOrders();
        }
    } catch (error) {
        console.error('Error executing order:', error);
        showAlert(`Error executing order: ${error.message}`, 'danger');
    } finally {
        orderExecutionInFlight.delete(orderId);
        if (sourceButton?.isConnected) sourceButton.disabled = false;
    }
}

/**
 * Cancel an order by ID
 * @param {string} orderId - The order ID to cancel
 */
async function cancelOrderById(orderId) {
    try {
        // Use the improved cancel order endpoint
        const result = await cancelOrder(orderId);
        
        // Update the order in pendingOrdersData
        const orderIndex = pendingOrdersData.findIndex(order => order.id == orderId);
        if (orderIndex !== -1) {
            pendingOrdersData[orderIndex].status = result.status || pendingOrdersData[orderIndex].status;
            
            // Add IB details if available
            if (result.ib_status) {
                pendingOrdersData[orderIndex].ib_status = result.ib_status;
            }
            
            // Update the table immediately
            updatePendingOrdersTable();
        }
        
        showAlert(result.message || 'Order cancellation requested', 'success');
        if (TRACKED_ORDER_STATUSES.includes(result.status)) {
            startAutoRefresh();
        } else {
            await loadPendingOrders();
        }
    } catch (error) {
        console.error('Error cancelling order:', error);
        showAlert(`Error cancelling order: ${error.message}`, 'danger');
        await loadPendingOrders();
    }
}

/**
 * Load pending orders from API
 */
async function loadPendingOrders() {
    try {
        // Fetch pending orders
        const pendingData = await fetchPendingOrders(false);
        if (pendingData && pendingData.orders) {
            pendingOrdersData = pendingData.orders;
            console.log(`Loaded ${pendingOrdersData.length} pending orders`);
            updatePendingOrdersTable();
            if (pendingOrdersData.some(order => TRACKED_ORDER_STATUSES.includes(order.status))) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        }
        
        if (document.getElementById('filled-orders-table')) {
            await loadFilledOrders();
        }
    } catch (error) {
        console.error('Error loading pending orders:', error);
        showAlert('Error loading pending orders', 'danger');
    }
}

/**
 * Load executed/filled orders from API
 */
async function loadFilledOrders() {
    try {
        // Fetch weekly option income data instead of executed orders
        const incomeData = await fetchWeeklyOptionIncome();
        if (incomeData) {
            console.log(`Received weekly option income data: ${incomeData.positions_count} positions`);
            
            // Store the data
            weeklyOptionIncomeData = incomeData;
            
            // Update the table
            updateFilledOrdersTable();
        } else {
            console.warn('No weekly option income data received from API');
        }
    } catch (error) {
        console.error('Error loading weekly option income:', error);
        showAlert(`Error loading weekly income data: ${error.message}`, 'danger');
    }
}

/**
 * Check for order status updates with TWS
 */
async function checkOrdersStatus() {
    try {
        // Track every state that may still change at IB.
        const hasProcessingOrders = pendingOrdersData.some(order => 
            TRACKED_ORDER_STATUSES.includes(order.status));
            
        if (hasProcessingOrders) {
            const result = await checkOrderStatus();
            
            if (result && result.success && result.updated_orders && result.updated_orders.length > 0) {
                console.log(`Received ${result.updated_orders.length} updated orders from status check`);
                
                // Track if any order's status changed to executed
                let orderWasExecuted = false;
                
                // Update the orders that changed
                result.updated_orders.forEach(updatedOrder => {
                    const orderIndex = pendingOrdersData.findIndex(order => order.id == updatedOrder.id);
                    if (orderIndex !== -1) {
                        // Check if this order is newly executed
                        if (pendingOrdersData[orderIndex].status !== 'executed' && 
                            updatedOrder.status === 'executed') {
                            orderWasExecuted = true;
                        }
                        
                        // Update the order with new status and details
                        pendingOrdersData[orderIndex] = {
                            ...pendingOrdersData[orderIndex],
                            ...updatedOrder
                        };
                    }
                });
                
                // Update the pending orders table
                updatePendingOrdersTable();
                
                // If any order was executed, reload the filled orders
                if (orderWasExecuted) {
                    console.log('An order was executed, refreshing filled orders');
                    await loadFilledOrders();
                }
                
                // If no more processing orders, stop auto-refresh
                const stillHasProcessingOrders = pendingOrdersData.some(order => 
                    TRACKED_ORDER_STATUSES.includes(order.status));
                    
                if (!stillHasProcessingOrders) {
                    stopAutoRefresh();
                }
            }
        } else {
            // No processing orders, no need for auto-refresh
            stopAutoRefresh();
        }
    } catch (error) {
        console.error('Error checking order status:', error);
        // Don't show alert for this routine operation
    }
}

/**
 * Start the auto-refresh timer for order status
 */
function startAutoRefresh() {
    // Don't create multiple timers
    if (autoRefreshTimer) {
        return;
    }
    
    // Create a new timer
    autoRefreshTimer = setInterval(checkOrdersStatus, AUTO_REFRESH_INTERVAL);
    console.log('Auto-refresh started');
}

/**
 * Stop the auto-refresh timer
 */
function stopAutoRefresh() {
    if (autoRefreshTimer) {
        clearInterval(autoRefreshTimer);
        autoRefreshTimer = null;
        console.log('Auto-refresh stopped');
    }
}

/**
 * Update the quantity for an order
 * @param {string|number} orderId - The ID of the order to update
 * @param {number} quantity - The new quantity value
 */
async function updateOrderQuantity(orderId, quantity) {
    try {
        // Find the order in our local data
        const orderIndex = pendingOrdersData.findIndex(o => o.id === parseInt(orderId, 10));
        if (orderIndex === -1) {
            console.error(`Order with ID ${orderId} not found in local data`);
            return;
        }
        
        // Update the quantity in our local data
        pendingOrdersData[orderIndex].quantity = quantity;
        
        // Update the quantity in the database via API
        // (This requires a new API endpoint to be implemented)
        const response = await fetch(`/api/options/order/${orderId}/quantity`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'X-All-You-Need-Is-Wheel': '1',
            },
            body: JSON.stringify({ quantity })
        });
        
        if (!response.ok) {
            console.error(`Error updating quantity: HTTP ${response.status}`);
            const responseText = await response.text();
            console.error(`Response: ${responseText}`);
            // Show error message
            showAlert(`Failed to update quantity: ${response.statusText}`, 'danger');
            return;
        }
        
        const result = await response.json();
        console.log(`Quantity updated for order ${orderId}:`, result);
        
        // Show success message
        showAlert(`Quantity updated to ${quantity}`, 'success');
        
    } catch (error) {
        console.error(`Error updating quantity for order ${orderId}:`, error);
        showAlert(`Error updating quantity: ${error.message}`, 'danger');
    }
}

// Set up event listener for the custom ordersUpdated event
document.addEventListener('ordersUpdated', loadPendingOrders);
document.addEventListener('languageChanged', () => {
    updatePendingOrdersTable();
    updateFilledOrdersTable();
});

// Make sure auto-refresh is stopped when the page is unloaded
window.addEventListener('beforeunload', stopAutoRefresh);

// Expose loadPendingOrders function globally
window.loadPendingOrders = loadPendingOrders;

// Export functions
export {
    loadPendingOrders,
    loadFilledOrders,
    executeOrderById,
    cancelOrderById
};

function addPositionsToTable(positions, table) {
    positions.forEach(position => {
        const row = document.createElement('tr');
        row.className = 'table-success'; // Highlight all rows
        
        // Format the strike price
        const strike = position.strike ? `$${position.strike}` : 'N/A';
        
        // Calculate premiums - use premium_per_contract if available, fall back to avg_cost
        const fillPrice = position.premium_per_contract || position.avg_cost || 0;
        const income = position.income || 0;
        
        // Format values for display
        const fillPriceFormatted = formatCurrency(fillPrice);
        const incomeFormatted = formatCurrency(income);
        
        // Get option type full name
        let optionType = position.option_type;
        // Normalize option type to standard display format
        if (optionType === 'C' || optionType === 'CALL' || optionType === 'Call') {
            optionType = 'CALL';
        } else if (optionType === 'P' || optionType === 'PUT' || optionType === 'Put') {
            optionType = 'PUT';
        }
        
        // Calculate and format notional value for PUT options
        let notionalValue = '-';
        if ((optionType === 'PUT' || optionType === 'P') && position.notional_value) {
            notionalValue = formatCurrency(position.notional_value);
        }
        
        // Create the row HTML without the status column
        row.innerHTML = `
            <td>${position.symbol}</td>
            <td>${optionType}</td>
            <td>${strike}</td>
            <td>${position.expiration || 'N/A'}</td>
            <td>${fillPriceFormatted}</td>
            <td>${position.position}</td>
            <td>${incomeFormatted}</td>
            <td>${notionalValue}</td>
        `;
        
        table.appendChild(row);
    });
}

/**
 * Handle canceling all pending orders
 */
async function cancelAllPendingOrders() {
    try {
        // Filter only pending orders
        const pendingOrders = pendingOrdersData.filter(order => order.status === 'pending');
        
        if (pendingOrders.length === 0) {
            showAlert(tr('orders.noPendingToCancel'), 'info');
            return;
        }
        
        // Confirm with the user
        if (!confirm(tr('orders.confirmCancelAll', { count: pendingOrders.length }))) {
            return;
        }
        
        // Show a loading alert
        showAlert(tr('orders.cancelingOrders', { count: pendingOrders.length }), 'info');
        
        // Create an array of promises for all the cancel operations
        const cancelPromises = pendingOrders.map(order => cancelOrder(order.id));
        
        // Wait for all cancellations to complete
        await Promise.all(cancelPromises);
        
        // Refresh the orders table
        await loadPendingOrders();
        
        // Show success message
        showAlert(tr('orders.canceledOrders', { count: pendingOrders.length }), 'success');
    } catch (error) {
        console.error('Error canceling all orders:', error);
        showAlert('Error canceling all orders: ' + error.message, 'danger');
    }
} 
