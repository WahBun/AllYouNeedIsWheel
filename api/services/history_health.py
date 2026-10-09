"""Passive Paper history evidence. No extra IB requests or trading writes."""
import json
import time
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / 'logs/paper-history-health.json'


def record(conn, con_id, outcome):
    try:
        account = conn.account_id
        if not isinstance(account, str) or not account.startswith('DU') or conn.port != 4002:
            return
        if conn.ib.managedAccounts() != [account]:
            return
        now = time.time()
        try:
            data = json.loads(PATH.read_text())
        except (OSError, ValueError):
            data = {}
        if outcome == 'success':
            data = {'success': now, 'failures': []}
        elif outcome == 'timeout':
            data['failures'] = [x for x in data.get('failures', []) if now-x[0] < 600]
            data['failures'].append([now, int(con_id)])
            data['failures'] = data['failures'][-100:]
        else:
            return
        data['updated'] = now
        PATH.parent.mkdir(exist_ok=True)
        temp = PATH.with_suffix('.tmp')
        temp.write_text(json.dumps(data))
        temp.chmod(0o600)
        temp.replace(PATH)
    except Exception:
        # Monitoring must never break chart delivery.
        return
