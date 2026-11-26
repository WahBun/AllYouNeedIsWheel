# Wheel: v1.9.3

Web **1.9.3** · iPhone and Apple Watch **1.9.3 (9)**

## Apple Watch and allocation

- Holdings shows NetLiq inside a clockwise ring of positive assets, largest first. Tap a slice or symbol for its details. Stocks show the IBKR-reported average cost and report date when available. The account mode fits beside the two tabs, and the active tab is identified by its text color. [#229](https://github.com/WahBun/AllYouNeedIsWheel/pull/229) · [#232](https://github.com/WahBun/AllYouNeedIsWheel/pull/232) · [#234](https://github.com/WahBun/AllYouNeedIsWheel/pull/234) · [#239](https://github.com/WahBun/AllYouNeedIsWheel/pull/239)
- NVDA, QQQ and QQQM use a flowing teal-to-apricot gradient. SGOV has its own gold gradient. TQQQ, QLD and UPRO use the Ben signature colors, with double-struck lettering for TQQQ. Ordinary assets have distinct static allocation colors, and cash is coral. [#230](https://github.com/WahBun/AllYouNeedIsWheel/pull/230) · [#231](https://github.com/WahBun/AllYouNeedIsWheel/pull/231) · [#235](https://github.com/WahBun/AllYouNeedIsWheel/pull/235)
- Quotes pins VIX above QQQ, SPY, MES and MNQ. An older VIX sample shows its own time. The footer uses the newest timestamp among all rows with a price. [#235](https://github.com/WahBun/AllYouNeedIsWheel/pull/235) · [#236](https://github.com/WahBun/AllYouNeedIsWheel/pull/236)

## Charts and options

- Search for VIX or VXN on web and iPhone to open an index chart. Daily change uses the previous trading session’s close for the displayed sample. [#234](https://github.com/WahBun/AllYouNeedIsWheel/pull/234) · [#238](https://github.com/WahBun/AllYouNeedIsWheel/pull/238)
- In web Supercharts, press and hold a favorite, then drag it into place. The order is saved to the shared favorites list. [#237](https://github.com/WahBun/AllYouNeedIsWheel/pull/237)
- iPhone Portfolio and Trade show each option contract’s open interest when IB provides it, using compact numbers such as `41.6K`. [#233](https://github.com/WahBun/AllYouNeedIsWheel/pull/233)

## Updating

1. On the backend host, deploy this release with **Deploy & Restart Backend**, then refresh the web page. This loads the index, option and Watch data changes.
2. Build Wheel from this release to update the iPhone and its paired Watch. The **iPhone Renew** shortcut can sign both apps in one build and install them when both devices are reachable and unlocked. If either is unavailable, reconnect the devices and run the shortcut again. [Setup](../ios/README.md#pro-shortcut-iphone-renew) · [#240](https://github.com/WahBun/AllYouNeedIsWheel/pull/240)

These changes follow the [final 1.9.2 source snapshot](https://github.com/WahBun/AllYouNeedIsWheel/commit/1e67b302507c6ecd09b9496f69e110aa8a9298e8).
