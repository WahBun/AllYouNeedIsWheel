# Paper acceptance for extended-hours equity options

Start with one NVDA single-leg equity option. QQQ and SPY are separate candidates. PR #243 covers stock and ETF shares. This draft covers option contracts and can be tested independently of the December stock-hours rollout.

## What Wheel sends today

| Entry point | Offline result on main at `2e87882` |
| --- | --- |
| Superchart standalone NVDA limit entry | Choosing GTC produces a SMART option order with `tif=GTC` and `outsideRth=False`. |
| iPhone Trade → Orders, newly staged NVDA opening limit | The default produces `tif=DAY` and `outsideRth=False`. An explicit GTC opening request reaches Wheel's validation and is rejected before broker submission. The native staged-order path has separate opening (DAY) and closing (GTC) defaults. |

The staged-order check exercises the service and its real order builder behind the native screen. Changing the TIF of an **already working** chart order uses another path. Preserve those edits when adding a session choice. The proposed ticket keeps DAY/GTC independent of a per-order extended-hours opt-in, with regular hours as the default.

## Broker session check

On a regular trading day C1 offers a 07:30–09:25 New York premarket session for these three classes. The first planned opportunity is Monday, November 30, 2026, 20:30–22:25 Shanghai time. Use premarket for all three. NVDA also has a 16:00–16:15 Curb session. For QQQ and SPY, a trade between 16:00 and 16:15 can fall within regular option hours. Check the trading calendar and the selected series for each run. C1 accepts limit orders in these extended sessions. [Cboe launch notice](https://www.cboe.com/notices/content/?id=62164) · [Cboe session FAQ](https://www.cboe.com/document/tech-spec/document/technical-specifications/equity-options-extended-trading-hours-faq/) · [Holiday calendar](https://www.cboe.com/about/hours/us-options/)

1. Qualify one exact option on the Paper connection and record its expiry, strike, right, conId, requested route, trading and liquid hours with their time zone. Confirm a current two-sided option quote in the intended session. Listing, a stock quote or the contract schedule alone cannot establish eligibility for this account and route.
2. For a broker write, get approval covering the Paper contract, side, quantity, initial and amended limit, and cancellation. Use a contract without an existing Paper position or working order. From the Paper API, submit one standalone SMART limit with the approved terms, GTC and `outsideRth=True`. Record the request time and the matching broker `openOrder` echo, status, warnings and any execution time. Keep account and order identifiers private. IBKR documents warning 2109 when a destination or order type ignores the flag. [IBKR error codes](https://www.interactivebrokers.com/docs/tws-api/doc/error/codes)
3. If the original order is still working and its identity and remaining quantity match, amend its limit once. Re-read the acknowledged limit, TIF and outside-hours flag on that same order. Cancel any unfilled remainder before the session ends and read the terminal state. On a timeout or disconnect, reconcile open orders and executions before further action. If filled, record that outcome and leave the resulting Paper position for the operator.
4. Record the verdict separately for routing, execution and order management. An echoed flag and `Submitted` show acknowledgement. An execution timestamp inside the target session demonstrates a **Paper** fill. If Paper only queues the order, record execution as unverified. A rejection or ignored flag leaves the route unverified for this feature. Confirm availability with IBKR before offering an inconclusive route. [IBKR Outside RTH setting](https://www.interactivebrokers.com/support/faq/content/27271538)

| Class | Paper route and flag | Premarket execution | Amend and cancel |
| --- | --- | --- | --- |
| NVDA | Pending | Pending | Pending |
| QQQ | Pending | Pending | Pending |
| SPY | Pending | Pending | Pending |

## Wheel acceptance after broker verification

Exercise both the web chart ticket and native iPhone Trade → Orders. For each verified route, check a new standalone limit with and without the opt-in, and both DAY and GTC. Read the working order from the other client. A price, quantity or TIF-only edit must preserve the broker-confirmed session and concurrent changes to untouched fields. Cancel only the remaining quantity on the same order. Include an ineligible option such as TSLL as a regular-hours control, and an existing order created before the change. Repeat broker writes only within the approved Paper scope.
