"""Keep IB operations on one thread while web pages remain independently responsive."""

from concurrent.futures import ThreadPoolExecutor
from threading import RLock, BoundedSemaphore, Event, Thread
import logging
import time

from flask import copy_current_request_context, jsonify, request


def install_api_dispatcher(app):
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ib-api')
    # Leave HTTP threads available for navigation even when IB is slow.
    slots = BoundedSemaphore(4)
    lock = RLock()
    pending_reads = {}
    original_dispatch = app.dispatch_request
    app.extensions['ib_api_executor'] = executor
    stop_background = Event()
    app.extensions['ib_background_stop'] = stop_background

    def background_loop():
        # One outstanding background job at most, sharing HTTP admission and executor.
        outstanding = None
        while not stop_background.wait(10):
            if app.testing or (outstanding is not None and not outstanding.done()):
                continue
            with lock:
                if pending_reads or not slots.acquire(blocking=False):
                    continue
                def synchronize():
                    try:
                        with app.app_context():
                            app.extensions['ib_background_sync']()
                    except Exception as error:
                        logging.getLogger('autotrader.api').warning(
                            'Background fill sync unavailable: %s', type(error).__name__)
                try:
                    outstanding = executor.submit(synchronize)
                except RuntimeError:
                    slots.release()
                    return
                outstanding.add_done_callback(lambda done: slots.release())

    if app.extensions.get('ib_background_sync') and not app.testing:
        Thread(target=background_loop, name='fill-sync-scheduler', daemon=True).start()


    def dispatch():
        if not request.path.startswith('/api/') or (request.method == 'GET' and request.path == '/api/options/market-session'):
            return original_dispatch()
        key = None
        # The HTTP context owns the diagnostic ID; copied worker contexts have their own g.
        from flask import g
        request_id = getattr(g, 'wheel_request_id', 'untracked')
        queued_at = time.monotonic()
        logger = logging.getLogger('autotrader.api')
        if request.method == 'GET':
            args = tuple(sorted(
                (name, value) for name, value in request.args.items(multi=True)
                if name not in {'t', '_'}
            ))
            key = (request.path, args)

        @copy_current_request_context
        def run():
            started = time.monotonic()
            logger.debug('ib_job_start id=%s queue_ms=%.1f', request_id, (started - queued_at) * 1000)
            try:
                response = app.make_response(original_dispatch())
            except Exception as error:
                logger.warning('ib_job_failed id=%s exception_type=%s', request_id, type(error).__name__)
                raise
            finally:
                logger.debug('ib_job_end id=%s work_ms=%.1f', request_id, (time.monotonic() - started) * 1000)
            # Each waiting HTTP request gets its own response object.
            return response.get_data(), response.status_code, list(response.headers)

        with lock:
            future = pending_reads.get(key) if key is not None else None
            if future is not None:
                logger.debug('ib_job_shared id=%s owner=%s', request_id, getattr(future, 'wheel_job_id', 'untracked'))
            if future is None:
                # Capacity counts IB jobs, not clients sharing the same read.
                if not slots.acquire(blocking=False):
                    logger.warning('ib_queue_full id=%s', request_id)
                    response = jsonify(error='IB requests are busy; please retry shortly')
                    response.status_code = 503
                    response.headers['Retry-After'] = '2'
                    return response
                try:
                    future = executor.submit(run)
                    future.wheel_job_id = request_id
                except Exception:
                    slots.release()
                    raise
                if key is not None:
                    pending_reads[key] = future

                def completed(done):
                    # Jobs retain their slots even when HTTP clients disconnect.
                    with lock:
                        if key is not None and pending_reads.get(key) is done:
                            pending_reads.pop(key, None)
                        slots.release()

                future.add_done_callback(completed)
        body, status, headers = future.result()
        return app.response_class(body, status=status, headers=headers)

    app.dispatch_request = dispatch
