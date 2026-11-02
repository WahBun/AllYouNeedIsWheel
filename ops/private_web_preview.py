"""Serve the working Superchart UI on loopback with synthetic, read-only data."""
import argparse
import hashlib
import re
import importlib.util
import json
import math
import logging
import secrets
from datetime import datetime, timezone
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from flask import Flask, Response, abort, redirect, render_template, request, send_from_directory

EPOCH = 'wheel-demo'
RATES = ('18', '69.9', '70')
SYMBOLS = {1: 'QQQ', 2: 'TSLL'}


def demo_rate(value):
    return value if value in RATES else RATES[0]


def chart_packet(cid, interval, session):
    if cid not in SYMBOLS or interval not in (1, 5, 15, 30, 60, 480, 1440, 10080, 43200):
        abort(404)
    step = interval * 60
    end = int(time.time()) // step * step
    bars = []
    count = min(96, end // step)
    for i in range(count):
        price = round((450 if cid == 1 else 12) + math.sin(i / 5) * 0.9, 2)
        bars.append(dict(time=end - (count - 1 - i) * step,
                         open=price, high=price + .15, low=price - .15,
                         close=price + .05, volume=1000 + i * 10))
    return dict(symbol=SYMBOLS[cid], con_id=cid, interval=interval, session=session,
                security_type='STK', currency='USD', multiplier=1, bars=bars,
                mode='snapshot', status='Demo prices', account_epoch=EPOCH,
                last=bars[-1]['close'], server_time=time.time(), history_expanded=True)


def create_demo(source):
    root = Path(source).absolute()
    app = Flask(__name__, static_folder=str(root / 'frontend/static'),
                template_folder=str(root / 'frontend/templates'))
    app.config['TEMPLATES_AUTO_RELOAD'] = True

    token = secrets.token_urlsafe(32)
    app.config['MAX_CONTENT_LENGTH'] = 256 * 1024
    app.config['PREVIEW_ORIGINS'] = set()
    editor = Path(__file__).with_name('preview_editor')

    groups = json.loads((editor / 'properties.json').read_text())
    controls = {key: spec for group in groups.values() for key, spec in group.items()}
    draft_key = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:20]

    @app.get('/preview-editor/<any("editor.js","editor.css","reorder.js"):asset>')
    def editor_asset(asset):
        return send_from_directory(editor, asset)

    @app.post('/preview-editor/reviews')
    def save_review():
        if request.headers.get('Origin') not in app.config['PREVIEW_ORIGINS'] or request.headers.get('X-Wheel-Preview') != token:
            abort(403)
        data = request.get_json()
        if not isinstance(data, dict):
            abort(400)
        changes, viewport = data.get('changes'), data.get('viewport')
        if not isinstance(viewport, list) or len(viewport) != 2 or not all(type(v) is int and 0 < v <= 16384 for v in viewport):
            abort(400)
        if not isinstance(changes, list) or not 1 <= len(changes) <= 256:
            abort(400)
        for item in changes:
            if (not isinstance(item, dict) or not {'selector', 'properties'} <= item.keys()
                    or item.keys() - {'scope', 'selector', 'properties', 'layoutOrder'}):
                abort(400)
            if item.get('scope', 'page') not in ('page', 'chart'):
                abort(400)
            sel, props = item['selector'], item['properties']
            if not isinstance(sel, str) or not 1 <= len(sel) <= 512 or not isinstance(props, dict) or set(props) - controls.keys():
                abort(400)
            if 'layoutOrder' in item:
                layout = item['layoutOrder']
                if not isinstance(layout, dict) or set(layout) != {'from', 'to'}:
                    abort(400)
                before, after = layout['from'], layout['to']
                if (not isinstance(before, list) or not isinstance(after, list)
                        or not 2 <= len(before) <= 128 or len(before) != len(after)):
                    abort(400)
                key_pattern = r'(?:[.#][A-Za-z_][\w-]*|[a-z][a-z0-9-]*(?::nth-of-type\([1-9]\d{0,4}\)|\[data-interval="\d{1,6}"\])?)'
                if (not all(isinstance(k, str) and len(k) <= 160 and re.fullmatch(key_pattern, k, re.ASCII)
                            for k in before + after) or len(set(before)) != len(before) or set(before) != set(after)):
                    abort(400)
            elif not props:
                abort(400)
            for key, pair in props.items():
                if not isinstance(pair, dict) or set(pair) != {'from', 'to'}:
                    abort(400)
                before, after = pair['from'], pair['to']
                # Preserve original CSS keywords, transparency and mixed edge values in the handoff.
                if not ((isinstance(before, str) and len(before) <= 160) or
                        (type(before) in (int, float) and abs(before) <= 32768)):
                    abort(400)
                spec = controls[key]
                if spec == 'color':
                    valid = isinstance(after, str) and re.fullmatch(r'#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?', after)
                elif isinstance(spec[0], int):
                    valid = type(after) in (int, float) and spec[0] <= after <= spec[1]
                else:
                    valid = after in spec
                if not valid:
                    abort(400)
        head = subprocess.run(['git','-C',str(root),'rev-parse','HEAD'], capture_output=True, text=True)
        directory = Path.home() / 'Library/Application Support/Wheel Web Preview/Layout Reviews'
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        name = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + secrets.token_hex(4)
        report = dict(source=str(root.resolve()), head=head.stdout.strip() or None,
                      viewport=viewport, changes=changes, units='CSS pixels for dimensions; CSS values for other properties')
        with (directory / (name + '.json')).open('x') as out:
            json.dump(report, out, indent=2)
        return dict(review=name), 201

    @app.after_request
    def response_headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "connect-src 'self'; frame-ancestors 'self'; object-src 'none'"
        return response

    @app.get('/')
    def home():
        return redirect('/superchart?con_id=1&margin=' + demo_rate(request.args.get('margin')))

    @app.get('/superchart')
    def preview():
        rate = demo_rate(request.args.get('margin'))
        choices = ''.join(f'<option value="{r}" {"selected" if r == rate else ""}>{r}%</option>' for r in RATES)
        controls = ('<span style="white-space:nowrap;color:var(--accent)">Demo · Margin '
                    '<select aria-label="Sample margin" onchange="const u=new window.URL(window.location.href);'
                    "u.searchParams.set(\'margin\',this.value);window.location.assign(u.href)"
                    f'">{choices}</select></span>')
        html = render_template('superchart.html')
        # Preserve the production element for its update handlers, but clearly label this preview.
        html = html.replace('<span id="connection">', controls + '<span hidden id="connection">', 1)
        # These sample prices use the chart's normal HTTP snapshot path.
        html = html.replace('<head>', f'<head><meta name="wheel-preview-token" content="{token}"><meta name="wheel-blueprint-key" content="{draft_key}"><script type="application/json" id="blueprint-properties">{json.dumps(groups)}</script><script>window.EventSource=undefined;</script>', 1)
        return html.replace('</body>', """<script>addEventListener('load',()=>{
          const detail=document.getElementById('chart-detail');
          if(detail?.hidden)document.getElementById('toggle-trade')?.click();
        });</script><script src="/preview-editor/reorder.js"></script><script src="/preview-editor/editor.js"></script></body>""", 1)

    @app.get('/superchart/frame')
    def frame():
        # Load only the renderer, never register the production API or initialize a broker client.
        spec = importlib.util.spec_from_file_location('preview_frame', root / 'api/routes/superchart.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return Response(module.chart_document(), mimetype='text/html')

    @app.get('/api/<path:path>')
    def fixtures(path):
        if path == 'account/profiles':
            return dict(selected='demo', verified=True, epoch=EPOCH, readonly=True)
        if path == 'portfolio/bootstrap':
            query = parse_qs(urlsplit(request.referrer or '').query)
            rate = float(demo_rate(query.get('margin', ['18'])[0]))
            positions = [dict(con_id=k, symbol=v, position=10, avg_cost=100, unrealized_pnl=20,
                              security_type='STK') for k, v in SYMBOLS.items()]
            return dict(summary=dict(account_value=25000, initial_margin=250 * rate, leverage_percentage=rate),
                        connection=dict(mode='demo', account_epoch=EPOCH), positions=positions)
        kind, _, cid = path.rpartition('/')
        if kind in ('portfolio/stock-chart', 'portfolio/stock-chart-latest') and cid.isdecimal():
            return chart_packet(int(cid), request.args.get('interval', 5, type=int),
                                request.args.get('session', 'all'))
        if kind == 'portfolio/stock-chart-stream':
            return '', 204
        if kind == 'portfolio/stock-chart-history':
            return dict(bars=[])
        if path == 'portfolio/chart-contracts':
            return dict(contracts=[dict(con_id=k, symbol=v, label=v) for k, v in SYMBOLS.items()])
        if path == 'options/pending-orders':
            return dict(orders=[])
        if kind == 'portfolio/chart-executions':
            return dict(con_id=int(cid) if cid.isdecimal() else None, executions=[])
        if kind == 'portfolio/chart-reference':
            return dict(con_id=int(cid) if cid.isdecimal() else None, previous_close=None)
        if kind in ('portfolio/chart-volatility', 'portfolio/chart-pnl'):
            return dict(status='unavailable', account_epoch=EPOCH)
        if path == 'notifications/events':
            return dict(events=[], cursor=0, epoch=EPOCH)
        if path == 'notifications/moonshine-rules':
            return dict(rules=[], epoch=EPOCH)
        if kind == 'portfolio/chart-ema':
            return dict(frames={})
        if kind == 'chart-drawings':
            return dict(revision=0, drawings=[])
        if path == 'chart-favorites':
            return dict(revision=0, favorites=[])
        if path.startswith('notifications/alerts/'):
            return dict(epoch=EPOCH, alerts=[])
        abort(404)

    return app


def port_in_use(config):
    if '8443' in (config.get('TCP') or {}):
        return True
    if any(k.endswith(':8443') and v for k, v in (config.get('AllowFunnel') or {}).items()):
        return True
    return any(port_in_use(v) for v in (config.get('Foreground') or {}).values())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--share', action='store_true', help='Serve a private HTTPS URL until stopped')
    args = parser.parse_args()
    app = create_demo(args.source)
    app.config['PREVIEW_ORIGINS'].update(f'http://{name}:{args.port}' for name in ('localhost','127.0.0.1'))
    if not args.share:
        app.run(host='127.0.0.1', port=args.port, threaded=True, use_reloader=False)
    else:
        from werkzeug.serving import make_server
        cli = shutil.which('tailscale') or '/usr/local/bin/tailscale'
        config = json.loads(subprocess.check_output([cli, 'serve', 'status', '--json']))
        if port_in_use(config):
            parser.exit(1, 'Tailscale port 8443 is already in use. Close the previous preview first.\n')
        device = json.loads(subprocess.check_output([cli, 'status', '--json']))['Self']['DNSName'].rstrip('.')
        app.config['PREVIEW_ORIGINS'].add(f'https://{device}:8443')
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        with make_server('127.0.0.1', args.port, app, threaded=True) as server:
            print(f'Local preview: http://127.0.0.1:{server.server_port}/', flush=True)
            threading.Thread(target=server.serve_forever, daemon=True).start()
            # Foreground Serve is removed by Tailscale when this session ends.
            subprocess.run([cli, 'serve', '--https=8443', f'http://127.0.0.1:{server.server_port}'], check=True)
