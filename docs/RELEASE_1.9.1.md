# Wheel: v1.9.1

iPhone **1.9.1 (7)** · Web **1.9.1** · Branch **`Ben/wheel-1.8`**

## Alerts

- MoonShine monitors QQQ, ES, NQ and SPY during their regular sessions. Each instrument uses its own opening range. QQQ and NQ share the configured Nasdaq volatility source, and ES and SPY share the S&P source.
- A price alert can fire when a qualifying live trade lands exactly on its level. A directional alert requires evidence of the side it approached from. Repeated trades at the level do not create repeated touches. Stock and futures chart alerts use the broker timestamp to check freshness. Option alerts also handle a first qualifying last trade at the target.

## Orders and iPhone

- An archived flat order group can be reconciled using its confirmed fills and cancellations. After the broker confirms the current order and its identity, the chart can resume editing the original order. A ready main chart can expose trading controls while a peer pane is still loading.
- On iPhone, edit or remove an individual candidate contract, or hide the ticker group. Orders displays a confirmed realized P&L subtotal while history is incomplete and keeps the history warning visible.
- Order details, Supercharts and the instrument picker use compact option names. The picker looks up expirations by underlying and preserves the selected contract's identity.

## Mac tools and updating

- The signing shortcut builds from the configured GitHub branch. The Pro sync helper can fast-forward the Xcode checkout after a confirmed merge. The three project READMEs include the Mac preview and layout editor instructions.
- On Mini, choose **Deploy & Restart Backend** to load the alert changes, then refresh the web page. This restarts the Wheel backend and leaves IB Gateway running.
- Build and Run the iPhone app from the release commit. Settings shows **1.9.1 (7)** after installation.
