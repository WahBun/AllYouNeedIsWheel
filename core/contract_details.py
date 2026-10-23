"""Ignore orphan contract-detail callbacks without reviving completed requests."""
from functools import wraps


def install_contract_details_guard(ib):
    wrapper = ib.wrapper
    original = wrapper.contractDetails
    if getattr(original, '_wheel_late_details_guard', False):
        return

    @wraps(original)
    def contract_details(req_id, detail):
        # ib_async 2.1.0 indexes this slot directly. A late callback after
        # request completion or connection reset must not recreate a result,
        # contaminate another request, or change the already reported outcome.
        if req_id not in wrapper._futures or req_id not in wrapper._results:
            wrapper._logger.warning('Ignoring contract details for inactive request %s', req_id)
            return
        return original(req_id, detail)

    contract_details._wheel_late_details_guard = True
    wrapper.contractDetails = contract_details
