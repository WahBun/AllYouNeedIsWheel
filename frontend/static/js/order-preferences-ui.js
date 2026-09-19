import {
    readOrderConfirmationPreference,
    saveOrderConfirmationPreference
} from './utils/order-preferences.js?v=execution-pref-1';

window.shouldConfirmOrderExecution = () => readOrderConfirmationPreference();

function syncConfirmationPreferenceUI() {
    const toggle = document.getElementById('confirm-order-execution-toggle');
    const state = document.getElementById('confirm-order-execution-state');
    if (!toggle) return;

    const enabled = readOrderConfirmationPreference();
    toggle.checked = enabled;
    if (state) {
        state.textContent = window.t
            ? window.t(enabled ? 'settings.confirmEnabled' : 'settings.confirmDisabled')
            : (enabled ? 'On' : 'Off');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const toggle = document.getElementById('confirm-order-execution-toggle');
    syncConfirmationPreferenceUI();
    if (toggle) {
        toggle.addEventListener('change', () => {
            saveOrderConfirmationPreference(toggle.checked);
            syncConfirmationPreferenceUI();
            document.dispatchEvent(new CustomEvent('orderConfirmationChanged', {
                detail: { enabled: toggle.checked }
            }));
        });
    }
});

document.addEventListener('languageChanged', syncConfirmationPreferenceUI);
