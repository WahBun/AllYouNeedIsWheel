function positivePrice(value) {
    const price = Number.parseFloat(value);
    return Number.isFinite(price) && price > 0 ? price : null;
}

function calculateMidPrice(bid, ask) {
    const bidPrice = positivePrice(bid);
    const askPrice = positivePrice(ask);
    if (bidPrice === null || askPrice === null || askPrice < bidPrice) return null;
    return (bidPrice + askPrice) / 2;
}

function calculateSpreadPercentage(bid, ask) {
    const mid = calculateMidPrice(bid, ask);
    if (mid === null) return null;
    return ((Number(ask) - Number(bid)) / mid) * 100;
}

function roundLimitPrice(value) {
    const price = positivePrice(value);
    if (price === null) return null;
    return Math.round((price + Number.EPSILON) * 100) / 100;
}

export { positivePrice, calculateMidPrice, calculateSpreadPercentage, roundLimitPrice };
