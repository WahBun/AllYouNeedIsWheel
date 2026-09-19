export const ORDER_CONFIRMATION_STORAGE_KEY = 'confirmBeforeOrderExecution';

export function isOrderConfirmationEnabled(storedValue) {
    return storedValue !== 'false';
}

export function readOrderConfirmationPreference(storage = window.localStorage) {
    try {
        return isOrderConfirmationEnabled(storage.getItem(ORDER_CONFIRMATION_STORAGE_KEY));
    } catch (error) {
        return true;
    }
}

export function saveOrderConfirmationPreference(enabled, storage = window.localStorage) {
    storage.setItem(ORDER_CONFIRMATION_STORAGE_KEY, enabled ? 'true' : 'false');
    return enabled;
}
