export function mergeOptionResponse(currentData, optionType, freshData) {
    if (freshData.stock_price !== undefined && freshData.stock_price !== null) {
        currentData.stock_price = freshData.stock_price;
    }
    if (freshData.position !== undefined && freshData.position !== null) {
        currentData.position = freshData.position;
    }

    if (optionType === 'CALL') {
        if (
            freshData.covered_call_capacity !== undefined &&
            freshData.covered_call_capacity !== null
        ) {
            currentData.covered_call_capacity = freshData.covered_call_capacity;
        }
        currentData.calls = freshData.calls || [];
    } else {
        currentData.puts = freshData.puts || [];
    }

    return currentData;
}

export function getCoveredCallContracts(optionData) {
    const sharesCapacity = Math.floor(Number(optionData?.position || 0) / 100);
    const serverCapacity = Number(optionData?.covered_call_capacity);
    if (!Number.isFinite(serverCapacity)) return Math.max(0, sharesCapacity);
    return Math.max(0, Math.min(sharesCapacity, Math.floor(serverCapacity)));
}

export function getCoveredCallOrderQuantity(optionData, requestedQuantity) {
    const capacity = getCoveredCallContracts(optionData);
    if (capacity < 1) return 0;

    const requested = Number.parseInt(requestedQuantity, 10);
    if (!Number.isFinite(requested) || requested < 1) return capacity;
    return Math.min(requested, capacity);
}
