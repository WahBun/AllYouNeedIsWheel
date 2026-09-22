"""Correlate API failures without recording accounts, query strings or bodies."""

import logging
import re
import time
import uuid

from flask import g, request

logger = logging.getLogger('autotrader.api')


def install_request_diagnostics(app):
    @app.before_request
    def start():
        if not request.path.startswith('/api/'):
            return
        supplied = request.headers.get('X-Wheel-Request-ID', '')
        g.wheel_request_id = supplied if re.fullmatch(r'[a-f0-9]{32}', supplied) else uuid.uuid4().hex
        g.wheel_started = time.monotonic()
        # Use the route template, never the concrete URL or query parameters.
        g.wheel_route = str(request.url_rule) if request.url_rule else 'unmatched'
        logger.debug('api_start id=%s method=%s route=%s', g.wheel_request_id, request.method, g.wheel_route)

    @app.after_request
    def finish(response):
        if not hasattr(g, 'wheel_request_id'):
            return response
        elapsed = (time.monotonic() - g.wheel_started) * 1000
        response.headers['X-Wheel-Request-ID'] = g.wheel_request_id
        response.headers['X-Wheel-Response-Origin'] = 'application'
        emit = logger.warning if response.status_code >= 400 or elapsed >= 1000 else logger.debug
        payload = response.get_json(silent=True) if response.is_json and response.status_code >= 400 else None
        state = payload.get('status') if isinstance(payload, dict) else None
        state = state if isinstance(state, str) and state in {'unknown', 'pending', 'processing', 'canceling', 'canceled', 'rejected', 'executed'} else 'unspecified'
        emit('api_end id=%s method=%s route=%s status=%s elapsed_ms=%.1f order_state=%s',
             g.wheel_request_id, request.method, g.wheel_route, response.status_code, elapsed, state)
        return response
