"""Opt-in, per-connection execution timestamp evidence; never changes decoding."""
import json
import re
from datetime import datetime, timezone
from importlib.metadata import version


def install_execution_time_diagnostic(ib, account, order_ref, logger):
    if not account or not re.fullmatch(r'AYNIW-\d+', order_ref or ''):
        raise ValueError('Execution diagnostic requires an account and AYNIW order reference')
    decoder = ib.client.decoder
    original = decoder.handlers[11]
    if getattr(original, '__name__', '') != 'execDetails':
        raise ValueError('Unsupported execution decoder; diagnostic not installed')
    seen = set()

    def capture(fields):
        # ib_async execution packet layout. Verify identities again against the
        # actual decoded object before treating these fields as evidence.
        if len(fields) < 31 or fields[16] != account or fields[26] != order_ref:
            return original(fields)
        raw_time, raw_id = fields[15], fields[14]
        callback = decoder.wrapper.execDetails

        def observe(req_id, contract, execution):
            # The production callback runs exactly once, with unchanged objects.
            result = callback(req_id, contract, execution)
            try:
                if (execution.acctNumber != account or execution.orderRef != order_ref
                        or execution.execId != raw_id):
                    return result
                key = (raw_id, raw_time, execution.time.isoformat())
                if key in seen or len(seen) >= 16:
                    return result
                record = dict(order_ref=order_ref, exec_id=execution.execId,
                    perm_id=execution.permId, ib_order_id=execution.orderId,
                    raw_time=raw_time, parsed_time=execution.time.isoformat(),
                    parsed_utc=execution.time.astimezone(timezone.utc).isoformat(),
                    observed_utc=datetime.now(timezone.utc).isoformat(),
                    timezone_tws=ib.TimezoneTWS or '(unset: host local fallback)',
                    server_version=decoder.serverVersion, ib_async_version=version('ib_async'))
                logger.info('EXECUTION_TIME_DIAGNOSTIC %s', json.dumps(record))
                seen.add(key)
            except Exception:
                # Diagnostics must not interrupt broker callbacks or log packets
                # containing account information when an unexpected format arrives.
                logger.warning('Execution time diagnostic could not record target timestamp')
            return result

        decoder.wrapper.execDetails = observe
        try:
            return original(fields)
        finally:
            decoder.wrapper.execDetails = callback

    decoder.handlers[11] = capture
