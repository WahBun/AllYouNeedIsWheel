// Calendar days in the exchange timezone, independent of the viewing device.
export function daysToExpiration(expiration, now = new Date()) {
    const match = String(expiration || '').match(/^(\d{4})-?(\d{2})-?(\d{2})$/);
    if (!match) return null;
    const [, year, month, day] = match;
    const expiry = Date.UTC(Number(year), Number(month) - 1, Number(day));
    const date = new Date(expiry);
    if (date.getUTCFullYear() !== Number(year) || date.getUTCMonth() !== Number(month) - 1 || date.getUTCDate() !== Number(day)) return null;
    const parts = Object.fromEntries(new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit'
    }).formatToParts(now).map(part => [part.type, part.value]));
    return (expiry - Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day))) / 86400000;
}

export function annualizedPremium(legs, now = new Date()) {
    let total = 0;
    for (const leg of legs) {
        if (!Number.isFinite(leg.premium) || leg.premium < 0) return null;
        if (leg.premium === 0) continue;
        const days = daysToExpiration(leg.expiration, now);
        // Same-day and invalid dates cannot yield a meaningful annualization.
        if (days === null || days <= 0) return null;
        total += leg.premium * 365 / days;
    }
    return total;
}
