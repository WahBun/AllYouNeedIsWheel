export function numberChoices(value, min, max, price = false) {
    const current = Number(value);
    if (price) {
        if (!Number.isFinite(current) || current <= 0) return [];
        const center = Math.round(current * 100);
        return Array.from({length: 41}, (_, i) => center - 20 + i)
            .filter(cents => cents > 0 && cents / 100 >= min && cents / 100 <= max)
            .map(cents => (cents / 100).toFixed(2));
    }
    const lower = Math.max(0, Math.ceil(min));
    const upper = Math.min(100, Math.floor(max));
    return Array.from({length: Math.max(0, upper - lower + 1)}, (_, i) => String(lower + i));
}
