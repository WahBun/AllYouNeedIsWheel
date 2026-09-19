// Serialize requests for a row, skipping selections superseded while waiting.
export function createLatestRequestQueue() {
    const current = new Map();
    const tails = new Map();
    return {
        async run(key, task) {
            const token = {};
            current.set(key, token);
            const previous = tails.get(key) || Promise.resolve();
            const isCurrent = () => current.get(key) === token;
            const request = previous.catch(() => {}).then(async () => {
                if (!isCurrent()) return null;
                try {
                    const result = await task(isCurrent);
                    return isCurrent() ? result : null;
                } catch (error) {
                    if (isCurrent()) throw error;
                    return null;
                }
            });
            tails.set(key, request);
            try {
                return await request;
            } finally {
                if (isCurrent()) current.delete(key);
                if (tails.get(key) === request) tails.delete(key);
            }
        }
    };
}
