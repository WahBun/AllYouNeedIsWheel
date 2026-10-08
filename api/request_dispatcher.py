"""Keep IB operations on one thread while web pages remain independently responsive."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError, CancelledError
from threading import RLock, BoundedSemaphore, Event, Thread
import logging
import time

from flask import copy_current_request_context, jsonify, request


def install_api_dispatcher(app):
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ib-api')
    # Leave HTTP threads available for navigation even when IB is slow.
    slots = BoundedSemaphore(4)
    # Read polling/background work cannot occupy the last admission slot.
    # Execution remains serialized; this reserves capacity, not write retries.
    read_slots = BoundedSemaphore(3)

    def acquire_slot(read_only):
        if read_only and not read_slots.acquire(blocking=False):
            return False
        if slots.acquire(blocking=False):
            return True
        if read_only:
            read_slots.release()
        return False

    def release_slot(read_only):
        slots.release()
        if read_only:
            read_slots.release()

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
                if pending_reads or not acquire_slot(True):
                    continue
                def synchronize():
                    try:
                        with app.app_context():
                            from api.routes.portfolio import portfolio_service
                            from api.services.paper_chart import PaperChart
                            conn=portfolio_service.connection
                            if conn and conn.is_connected() and str(conn.account_id).startswith('DU') and not conn.readonly:
                                PaperChart(portfolio_service.config.get('db_path')).cancel_trims_after_stop(conn)
                            app.extensions['ib_background_sync']()
                    except Exception as error:
                        logging.getLogger('autotrader.api').warning(
                            'Background fill sync unavailable: %s', type(error).__name__)
                try:
                    outstanding = executor.submit(synchronize)
                except RuntimeError:
                    release_slot(True)
                    return
                outstanding.add_done_callback(lambda done: release_slot(True))

    if app.extensions.get('ib_background_sync') and not app.testing:
        Thread(target=background_loop, name='fill-sync-scheduler', daemon=True).start()


    def chart_loop():
        from api.services.chart_stream import streams
        from api.services.chart_latest import latest_charts
        outstanding = None
        while not stop_background.wait(.005):
            if (not streams.clients and not latest_charts.contexts()) or (outstanding is not None and not outstanding.done()):
                continue
            def pulse():
                try:
                    with app.app_context(): streams.pulse()
                except Exception:
                    logging.getLogger('autotrader.api').warning('Chart push paused')
            try:
                outstanding = executor.submit(pulse)
            except RuntimeError:
                return
    if not app.testing:
        Thread(target=chart_loop, name='chart-event-pump', daemon=True).start()

    def dispatch():
        if request.endpoint in ('portfolio.get_stock_chart_stream','portfolio.get_stock_chart_latest'):
            return original_dispatch()
        if not request.path.startswith('/api/') or (request.method == 'GET' and request.path in {'/api/options/market-session', '/api/performance/history'}):
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

        def expired_response():
            response = jsonify(status='rejected', code='NOT_EXECUTED', error='Request expired before execution; no operation was started')
            response.status_code = 503
            response.headers['Retry-After'] = '2'
            return response

        @copy_current_request_context
        def run():
            started = time.monotonic()
            if started - queued_at >= 10:
                response = expired_response()
                return response.get_data(), response.status_code, list(response.headers)
            logger.debug('ib_job_start id=%s queue_ms=%.1f', request_id, (started - queued_at) * 1000)
            try:
                from api.routes.account import write_guard
                rejected = write_guard()
                response = app.make_response(rejected if rejected is not None else original_dispatch())
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
                if not acquire_slot(key is not None):
                    logger.warning('ib_queue_full id=%s', request_id)
                    response = jsonify(status='rejected', code='QUEUE_FULL', error='IB requests are busy; please retry shortly')
                    response.status_code = 503
                    response.headers['Retry-After'] = '2'
                    return response
                try:
                    future = executor.submit(run)
                    future.wheel_job_id = request_id
                except Exception:
                    release_slot(key is not None)
                    raise
                if key is not None:
                    pending_reads[key] = future

                def completed(done):
                    # Jobs retain their slots even when HTTP clients disconnect.
                    with lock:
                        if key is not None and pending_reads.get(key) is done:
                            pending_reads.pop(key, None)
                        release_slot(key is not None)

                future.add_done_callback(completed)
        try:
            body, status, headers = future.result(timeout=10)
        except TimeoutError:
            # Cancel only jobs that have not begun. A running trade must retain
            # its acknowledgement path; never report it as not submitted.
            if future.cancel():
                return expired_response()
            try:
                body, status, headers = future.result()
            except CancelledError:
                return expired_response()
        except CancelledError:
            return expired_response()
        return app.response_class(body, status=status, headers=headers)

    app.dispatch_request = dispatch
