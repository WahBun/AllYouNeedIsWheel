"""Pro-only UI preview; proxy the existing Mini API, never start another IB client.
Usage: .venv/bin/python ops/chart_preview.py --backend http://<mini>:8000
"""
import argparse
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask, request, Response, abort
from api.routes.superchart import bp


def create_preview(backend):
    root = Path(__file__).resolve().parents[1]
    app = Flask(__name__, template_folder=str(root/'frontend/templates'), static_folder=str(root/'frontend/static'))
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.register_blueprint(bp)

    @app.route('/api/<path:path>', methods=['GET', 'POST'])
    def proxy(path):
        allowed = path in ('account/profiles', 'portfolio/bootstrap', 'options/pending-orders', 'portfolio/chart-contracts') or path.startswith(('portfolio/stock-chart/', 'portfolio/stock-chart-history/', 'portfolio/paper-chart/', 'portfolio/chart-executions/', 'portfolio/chart-ema/'))
        if not allowed or '..' in path: abort(404)
        if request.method == 'POST':
            if not path.startswith('portfolio/paper-chart/') or request.headers.get('Origin') != request.host_url.rstrip('/') or request.headers.get('X-All-You-Need-Is-Wheel') != '1': abort(403)
        headers={key:request.headers[key] for key in ('Content-Type','X-All-You-Need-Is-Wheel','X-Wheel-Account-Epoch') if key in request.headers}
        url=backend.rstrip('/')+'/api/'+path+('?' + request.query_string.decode() if request.query_string else '')
        req=Request(url,data=request.get_data() if request.method=='POST' else None,headers=headers,method=request.method)
        try:
            with urlopen(req, timeout=40) as upstream:
                return Response(upstream.read(),status=upstream.status,content_type=upstream.headers.get('Content-Type'),headers={'Cache-Control':'no-store'})
        except HTTPError as error:
            return Response(error.read(),status=error.code,content_type='application/json')
        except Exception:
            return {'error':'Mini unavailable; request outcome may be unknown'},503
    return app

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--backend',required=True);parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    if urlparse(args.backend).scheme not in ('http','https'): parser.error('HTTP backend required')
    create_preview(args.backend).run(host='127.0.0.1',port=args.port,threaded=True,debug=False)
