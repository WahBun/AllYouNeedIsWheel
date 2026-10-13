# Optional Gateway proxy routing

Status: prepared, not deployed. The running Gateway remains on its original route.

`ops/gateway-proxy.override.yml` adds JVM SOCKS settings to both Live and Paper
through `_JAVA_OPTIONS`. No image, shared launcher, account profile or broker
permission changes are required. The installed Gateway JVM accepted these
properties in a separate `-XshowSettings:properties -version` process. That check
is not end-to-end broker validation. API loopback addresses are excluded.

Set `WHEEL_GATEWAY_PROXY_HOST` and `WHEEL_GATEWAY_PROXY_PORT` only in private
machine configuration. Values must describe the proxy reachable from inside the
container, not the host's loopback address. Existing `_JAVA_OPTIONS`, if present,
need review before applying this override; do not overwrite unrelated JVM flags.

This override alone does not force a smart-mode proxy to tunnel IB IP addresses.
The proxy must support a durable rule for the actual IB destinations. Verify
routing with sockets as well as live broker data. Never equate SOCKS negotiation
success with remote delivery or faster market data. Failure of the proxy can
interrupt both Gateway sessions; no automatic direct fallback is provided.

## Current Veee limitation

The installed application's extracted renderer reads `proxy.ip` from its `vPac`
rule data and forwards it as `proxyIPs`; the main process forwards the field to
its proxy engine. The renderer refreshes `vPac` from `/Desktop/rule` when the
rule version changes. The user-visible custom rule page offered domain rules,
not an IP selector. No supported durable local IP-rule interface has been
established. Do not patch the application or overwrite its live rule cache.

REA ASAR analysis retained evidence
`ev_f54889b23733ab675dc49b3bfe06d2d0ff4f29b9b4d67a5d5bdf1a102edc3de0`;
semantic coverage was partial. The rule dataflow above was corroborated by
focused reads of the extracted shipped main and renderer bundles, not inferred
from complete runtime coverage. Application SHA-256:
`d33b9a172b8b6902e20263cc07a5a034038eb081a209dd3311b2657a96caf484`.

## Activation and rollback gates

Before activation, preserve the current compose inputs and image digest, inspect
existing JVM options, and verify proxy rules and access from the container.
Obtain the required service-restart authorization. Read broker positions and all
open orders and inspect disconnect behavior; stop if risks cannot be isolated.
Keep existing account configuration, database, image, API ports and volumes.
Recreate only the authorized Gateway service with the optional override included.
Verify both account identities, unchanged positions/order state, historical and
streaming data, four-chart updates and restart recovery. Never send orders for
network verification. Login or compilation alone is insufficient.

Rollback removes this override from the exact original compose invocation and
recreates the authorized service with original private inputs. Verify identities,
positions, orders and chart recovery again. Do not leave a temporary experiment
launcher or global proxy switch as the permanent deployment.
