"""Retain the broker P&L value before ib_async turns UNSET_DOUBLE into zero."""
import math


def install_realized_pnl_capture(ib):
    wrapper = ib.wrapper
    original = wrapper.commissionReport

    def capture(report):
        fill = wrapper.fills.get(report.execId)
        if fill is not None:
            value = report.realizedPNL
            valid = (isinstance(value, (int, float)) and not isinstance(value, bool)
                     and math.isfinite(value) and abs(value) < 1e100)
            # dataclassUpdate preserves this attribute; set before downstream events.
            fill.commissionReport._wheel_realized_pnl = value if valid else None
        return original(report)

    wrapper.commissionReport = capture
