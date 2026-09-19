# Project Working Agreements

Read `docs/HANDOFF.md` and `docs/MAC_MINI_TAILSCALE.md` before deployment changes.

- Iterate the web version first. Build or update the Mac App/DMG only when explicitly requested.
- Preserve local connection configuration, databases, pending orders and user changes.
- Never commit account IDs, credentials, local databases, logs or device-specific network addresses.
- Treat deployments as potentially live trading. Test with mocks and read-only requests; do not place, modify or cancel real orders for verification.
- Keep one server process and one stable IB client identity. HTTP threads are safe only with the dedicated serialized API dispatcher in place.
- Do not automatically retry trading writes or interpret an unknown order status as canceled.
- Verify account routing, exact contracts, quantities and prices when changing execution code.
- Check mobile and desktop layouts, English/Chinese and light/dark themes for UI changes.
- Run the relevant tests and record material limitations. Do not promise bug-free trading or guaranteed fills.
- Conversation history is not a source of deployed state: inspect Git, local configuration and service status on the current host.
