"""Web host for the exact chart assets shipped in the native app."""
from pathlib import Path
from flask import Blueprint, Response, render_template, request, jsonify

bp = Blueprint('superchart', __name__)
ASSETS = Path(__file__).resolve().parents[2] / 'ios' / 'Wheel' / 'ChartAssets'


def chart_document():
    html = (ASSETS / 'stock-chart.html').read_text()
    html = html.replace('/*LIBRARY*/', (ASSETS / 'lightweight-charts.standalone.production.js').read_text())
    bridge = "window.webkit={messageHandlers:Object.fromEntries(['paperAction','entryChanged','drawingsChanged','chartReady','beState','historyRequest'].map(name=>[name,{postMessage:body=>parent.postMessage({wheelChart:true,name,body,sentAt:performance.timeOrigin+performance.now()},location.origin)}]))};"
    html = html.replace('<head>', '<head><script>' + bridge + '</script>', 1)
    return html.replace('</body>', '<script>' + (ASSETS / 'chart-drawings.js').read_text() + '</script><script>' + (ASSETS / 'chart-add-orders.js').read_text() + '</script><script src="/static/js/vendor/html2canvas-1.4.1.min.js"></script><script src="/static/js/chart-context-menu.js"></script><script src="/static/js/chart-volatility.js"></script></body>')


@bp.get('/superchart')
def index():
    return render_template('superchart.html')


@bp.get('/superchart/frame')
def frame():
    return Response(chart_document(), mimetype='text/html', headers={'Cache-Control': 'no-store', 'Content-Security-Policy': "frame-ancestors 'self'"})


@bp.route('/api/chart-drawings/<int:cid>', methods=['GET','POST'])
def drawings(cid):
    from api.services.chart_drawings import exchange
    if request.content_length and request.content_length > 2_000_000:
        return jsonify(error='Drawing payload too large'),413
    try:
        body=request.get_json(silent=True) if request.method=='POST' else {}
        if not isinstance(body,dict): raise ValueError('Invalid drawing payload')
        return jsonify(exchange(cid,body.get('operations',[]))),200,{'Cache-Control':'no-store'}
    except ValueError as error:
        return jsonify(error=str(error)),400
