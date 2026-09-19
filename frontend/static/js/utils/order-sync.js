export const ORDER_STATUS_SYNC_INTERVAL_MS = 1000;
export const ORDER_DISCOVERY_INTERVAL_MS = 2000;

export const TRACKED_ORDER_STATUSES = Object.freeze([
    'submitting',
    'processing',
    'canceling',
    'unknown'
]);

export const CANCELABLE_ORDER_STATUSES = Object.freeze([
    'pending',
    ...TRACKED_ORDER_STATUSES
]);

export function hasTrackedOrders(orders = []) {
    return orders.some(order => TRACKED_ORDER_STATUSES.includes(order.status));
}

export function getOrderTimeInForce(order = {}) {
    const explicitTif = String(order.tif || '').trim().toUpperCase();
    if (explicitTif) {
        return explicitTif;
    }
    return String(order.intent || 'OPEN').toUpperCase() === 'CLOSE' ? 'GTC' : 'DAY';
}

export function getOrderSyncInterval(orders = []) {
    return hasTrackedOrders(orders)
        ? ORDER_STATUS_SYNC_INTERVAL_MS
        : ORDER_DISCOVERY_INTERVAL_MS;
}

export function shouldForceOrderDiscovery(orders = []) {
    return !hasTrackedOrders(orders) || orders.some(order => order.external_ib);
}

export function getCancelableWebOrders(orders = []) {
    return orders.filter(order => (
        !order.external_ib && CANCELABLE_ORDER_STATUSES.includes(order.status)
    ));
}

export function getActiveExternalOrders(orders = []) {
    return orders.filter(order => (
        order.external_ib && CANCELABLE_ORDER_STATUSES.includes(order.status)
    ));
}
