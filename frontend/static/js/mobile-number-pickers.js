import { numberChoices } from './utils/number-choices.js';

const attached = new WeakMap();
export function refreshNumberPickers() {
    if (!matchMedia('(max-width: 575.98px)').matches) {
        document.querySelectorAll('.mobile-number-picker').forEach(select => select.remove());
        return;
    }
    document.querySelectorAll('.options-opportunities-table input:is(.otm-input, .call-qty-input, .put-qty-input, .mid-price-input)').forEach(input => {
        let state = attached.get(input);
        if (!state?.select.isConnected) {
            const select = document.createElement('select');
            select.className = 'form-select mobile-number-picker';
            input.after(select);
            select.addEventListener('change', () => {
                if (input.disabled || !select.value) return;
                input.value = select.value;
                input.dispatchEvent(new Event('input', {bubbles: true}));
                input.dispatchEvent(new Event('change', {bubbles: true}));
            });
            state = {select, signature: ''};
            attached.set(input, state);
        }
        const label = input.closest('td')?.dataset.mobileLabel || '';
        const price = input.classList.contains('mid-price-input');
        const min = input.min === '' ? (price ? 0.01 : 1) : Number(input.min);
        const max = input.max === '' ? (price ? Infinity : 100) : Number(input.max);
        const signature = JSON.stringify([input.value, min, max, input.disabled, label]);
        if (signature === state.signature) return;
        state.signature = signature;
        const values = numberChoices(input.value, min, max, price);
        const selected = price ? Number(input.value).toFixed(2) : input.value;
        state.select.replaceChildren(...values.map(value => new Option(
            price ? `$${value}` : input.classList.contains('otm-input') ? `${value}%` : value,
            value, false, value === selected
        )));
        state.select.value = selected;
        state.select.disabled = input.disabled || values.length === 0;
        state.select.setAttribute('aria-label', label);
        state.select.title = label;
    });
}
