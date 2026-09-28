# Explicit UTC execution format compatibility fix

IB documents UTC notation as YYYYMMDD-HH:MM:SS:
https://ibkrcampus.com/campus/trading-lessons/requesting-market-data/

The installed ib_async parseIBDatetime strips the hyphen in this format and returns
a naive datetime. Decoder.execDetails subsequently applies TimezoneTWS or the host
local timezone. Tests reproduced 20260928-15:02:00 -> 07:02:00Z on Asia/Shanghai,
instead of 15:02:00Z. This is an independently confirmed parser defect. The original
real-time packet for the affected production trade is not available, so its causal
link to this particular record is still an inference, not captured evidence.

A per-instance execution handler adapter converts only this exact explicit UTC
notation to the equivalent timezone-qualified string before passing it to the
original decoder. Legacy space-separated timestamps, named timezones, and all other
fields remain unchanged. This does not set TimezoneTWS, shift historical rows or
patch the library globally. Diagnostics install outside this adapter so raw_time
still contains the actual unmodified broker string. No extra broker requests,
connections, submissions or cancellations are introduced.

169 Python tests passed. The new real-decoder tests reproduce the old eight-hour
error, confirm independence from host/TWS zones, retain named-zone summer/winter
and legacy behavior, verify original packets unchanged and diagnostics raw capture.

Mini rollout: back up config and consistent SQLite first. Pull, run tests, and
restart only the backend once at a safe submission boundary using the existing
single worker/client. Leave Gateway and execution_timezone unchanged. Capture the
affected order by exact reference using the optional diagnostic and compare its
execId/permId/IB ID and broker timestamp before any narrowly targeted historical
correction. Do not bulk-shift historical times. Verify normal read responses and
order/config preservation. Pro has not deployed this patch remotely.
