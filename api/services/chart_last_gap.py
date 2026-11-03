"""Bounded diagnostics for non-option Last subscriptions on the IB owner thread."""
import logging
import time


class LastTradeGap:
    def __init__(self, con_id):
        self.con_id = con_id
        self.last_accept = time.monotonic()
        self.next_log = 0
        self.reported = False
        self.bid_ask = self.level1_last = self.level1_different = 0
        self.future = self.out_of_order = self.before_tail = self.invalid = 0

    def observe(self, accepted):
        now = time.monotonic()
        gap = now - self.last_accept
        if gap >= 4 and ((not self.reported and now >= self.next_log) or (self.reported and accepted)):
            logging.getLogger('autotrader.api').info(
                'chart_last_gap con_id=%s phase=%s gap_ms=%.0f accepted_batch=%s '
                'future=%s out_of_order=%s before_tail=%s invalid=%s bid_ask=%s level1_last=%s level1_different=%s',
                self.con_id, 'resumed' if accepted else 'waiting', gap * 1000, accepted,
                self.future, self.out_of_order, self.before_tail, self.invalid, self.bid_ask, self.level1_last, self.level1_different)
            self.next_log = now + 60
            self.reported = True
        if accepted:
            self.last_accept = now
            self.reported = False
            self.bid_ask = self.level1_last = self.level1_different = 0
            self.future = self.out_of_order = self.before_tail = self.invalid = 0
