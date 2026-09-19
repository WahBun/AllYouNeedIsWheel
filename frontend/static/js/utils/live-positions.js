export function getPositionKey(position = {}) {
    const securityType = String(
        position.security_type || position.securityType || position.sec_type || ''
    ).toUpperCase();
    const symbol = String(position.symbol || '');
    if (securityType !== 'OPT') return `STK:${symbol}`;

    const conId = Number(position.con_id || 0);
    if (conId > 0) return `OPT:${conId}`;

    return [
        'OPT',
        symbol,
        position.expiration || '',
        Number(position.strike || 0),
        position.option_type || ''
    ].join(':');
}

export function haveSamePositionSet(current = [], incoming = []) {
    if (current.length !== incoming.length) return false;
    const currentKeys = new Set(current.map(getPositionKey));
    return incoming.every(position => currentKeys.has(getPositionKey(position)));
}

export function getPriceDirection(previousPrice, nextPrice) {
    if (!Number.isFinite(previousPrice) || !Number.isFinite(nextPrice)) return null;
    if (nextPrice > previousPrice) return 'up';
    if (nextPrice < previousPrice) return 'down';
    return null;
}
