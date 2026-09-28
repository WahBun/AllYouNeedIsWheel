"""Preserve IB's explicitly UTC hyphen timestamp before ib_async drops the marker."""
import re
from functools import wraps


def install_execution_utc_format(ib):
    decoder = ib.client.decoder
    original = decoder.handlers[11]

    @wraps(original)
    def decode(fields):
        # IB API 10.18: YYYYMMDD-HH:MM:SS is UTC. The library strips the
        # hyphen, leaving a naive datetime which otherwise uses host/TWS timezone.
        # Do not reinterpret legacy space-separated or timezone-qualified input.
        if len(fields) >= 31 and re.fullmatch(r'\d{8}-\d{2}:\d{2}:\d{2}', fields[15]):
            fields = list(fields)
            fields[15] = fields[15].replace('-', ' ', 1) + ' UTC'
        return original(fields)

    decoder.handlers[11] = decode
