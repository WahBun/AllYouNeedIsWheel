export function ensureTickerState(store, ticker) {
    if (!store[ticker]) {
        store[ticker] = {};
    }

    const tickerState = store[ticker];
    tickerState.data ||= {};
    tickerState.data.data ||= {};
    tickerState.data.data[ticker] ||= {
        stock_price: 0,
        position: 0,
        calls: [],
        puts: []
    };
    tickerState.callOtmPercentage ||= 10;
    tickerState.putOtmPercentage ||= 10;
    tickerState.putQuantity ||= 1;
    return tickerState;
}
