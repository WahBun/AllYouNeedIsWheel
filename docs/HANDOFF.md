# Project Handoff

## Workflow

The web version is the primary iteration target. Desktop App/DMG updates are
separate releases, made only after an explicit request. The interface starts in
English unless a language was manually selected; theme and language preferences
are stored per browser.

The deployment model is one always-on Mac mini running the web application and
IB Gateway, accessed locally or from trusted devices through Tailscale Serve.
Do not assume another computer has the same paths, Python environment, credentials
or uncommitted changes. Pull Git updates and inspect the current host first.

## Architecture Invariants

- Flask/Jinja frontend with JavaScript modules; Python `ib_async` backend and SQLite.
- One Gunicorn process, eight HTTP threads, one dedicated API execution thread.
  `api/request_dispatcher.py` owns serialized API dispatch and preserves IB event-loop
  thread ownership. Identical in-flight GET requests share work. Writes never do.
- Four concurrent API waiters are admitted; excess requests receive 503 and
  Retry-After. HTML, static assets and health checks do not enter the IB queue.
- Order staging is separate from Execute. Execution confirmation is configurable.
- An atomic database claim guards duplicate execution of the same staged order.
  Execution rechecks the configured account, contract and position capacity.
- Readonly is enforced by both service and connection code, not just the IB library.
- Portfolio reads target a two-second start-to-start cadence, without overlapping
  requests or catch-up bursts. Failed reads back off; hidden tabs pause.
- Quote selection serializes work per row and discards superseded results. Old
  prices are removed while loading. Invalid manual prices cannot fall back silently.
- Expiration checks use the New York date, not the host's local calendar date.

## Verification

```sh
python -m unittest discover -s tests
node --test tests/*.js
git diff --check
```

The September 19, 2026 verification passed 97 Python and 29 JavaScript tests.
Browser checks covered Dashboard, Portfolio, Rollover, rapid expiry changes,
failed quotes, invalid manual prices, mobile table scrolling, settings and dialogs.
Widths tested: 320, 390, 430 and 1440 pixels, including English/Chinese and
light/dark combinations. These checks are not live-trade or real-iPhone certification.

No real order was submitted or canceled during verification. Use mocked broker
responses for order tests; a populated portfolio alone does not prove a paper account.

## Known Limitations

- The market-hours helper lacks exchange holidays and early-close calendars.
- Earnings projections still assume weekly repetition rather than the selected
  monthly contract's time to expiration.
- Cold IB contract qualification and unavailable quotes can take seconds. API
  operations still serialize for consistency, although navigation is independent.
- Tailnet membership is the access boundary; there is no separate per-user web
  login. Limit device/user access with Tailnet policy. Do not publish via Funnel.
- Live fills, upstream outages and every broker-side rejection cannot be proven
  by local regression tests. Unknown submission outcomes require reconciliation.

See `MAC_MINI_TAILSCALE.md` for installation, access and restart procedures.
