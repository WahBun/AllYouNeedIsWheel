"""Keep IB operations on one thread while web pages remain independently responsive."""

from concurrent.futures import ThreadPoolExecutor
from threading import RLock, BoundedSemaphore

from flask import copy_current_request_context, jsonify, request


def install_api_dispatcher(app):
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ib-api')
    # Leave HTTP threads available for navigation even when IB is slow.
    slots = BoundedSemaphore(4)
    lock = RLock()
    pending_reads = {}
    original_dispatch = app.dispatch_request
    app.extensions['ib_api_executor'] = executor

    def dispatch():
        if not request.path.startswith('/api/'):
            return original_dispatch()
        if not slots.acquire(blocking=False):
            response = jsonify(error='IB requests are busy; please retry shortly')
            response.status_code = 503
            response.headers['Retry-After'] = '2'
            return response

        key = None
        future = None
        try:
            if request.method == 'GET':
                args = tuple(sorted(
                    (name, value) for name, value in request.args.items(multi=True)
                    if name not in {'t', '_'}
                ))
                key = (request.path, args)

            @copy_current_request_context
            def run():
                response = app.make_response(original_dispatch())
                # Each waiting HTTP request gets its own response object.
                return response.get_data(), response.status_code, list(response.headers)

            with lock:
                future = pending_reads.get(key) if key is not None else None
                if future is None:
                    future = executor.submit(run)
                    if key is not None:
                        pending_reads[key] = future
            body, status, headers = future.result()
            return app.response_class(body, status=status, headers=headers)
        finally:
            with lock:
                if key is not None and pending_reads.get(key) is future:
                    pending_reads.pop(key, None)
            slots.release()

    app.dispatch_request = dispatch
