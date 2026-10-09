"""Analysis annotations only. No broker connection or order methods."""
import json
import math
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / 'chart_drawings.db'

def exchange(cid, operations, path=None):
    if not isinstance(cid,int) or cid <= 0: raise ValueError('Invalid contract')
    if not isinstance(operations,list) or len(operations)>400: raise ValueError('Too many operations')
    for op in operations:
        if not isinstance(op,dict) or not isinstance(op.get('op'),str) or not 1<=len(op['op'])<=100 or not isinstance(op.get('id'),str) or not 1<=len(op['id'])<=150: raise ValueError('Invalid operation')
        if op.get('kind') not in ('put','delete','import'): raise ValueError('Invalid operation type')
        if not isinstance(op.get('base',0),int): raise ValueError('Invalid revision')
        if op['kind']!='delete':
            value=op.get('value')
            if not isinstance(value,dict) or value.get('type') not in {'trend','info','hray','channel','fib','fibext','long','short','range','highlight','arrow','up','down','rect','path','triangle','curve','text','note','price'} or value.get('id')!=op['id'] or not isinstance(value.get('p'),list) or len(value['p'])>400: raise ValueError('Invalid drawing')
            for point in value['p']:
                if not isinstance(point,dict) or any(not isinstance(point.get(k),(int,float)) or not math.isfinite(point[k]) for k in ('time','price')) or point['price']<=0: raise ValueError('Invalid point')
    with sqlite3.connect(path or DB,timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS drawings(cid INTEGER,id TEXT,value TEXT,rev INTEGER,PRIMARY KEY(cid,id))')
        db.execute('CREATE TABLE IF NOT EXISTS drawing_ops(cid INTEGER,op TEXT,PRIMARY KEY(cid,op))')
        db.execute('BEGIN IMMEDIATE')
        revision=db.execute('SELECT COALESCE(MAX(rev),0) FROM drawings WHERE cid=?',(cid,)).fetchone()[0]
        for op in operations:
            if db.execute('SELECT 1 FROM drawing_ops WHERE cid=? AND op=?',(cid,op['op'])).fetchone(): continue
            old=db.execute('SELECT value,rev FROM drawings WHERE cid=? AND id=?',(cid,op['id'])).fetchone()
            target=op['id'];value=op.get('value')
            if op['kind']=='import' and old: pass
            elif old and old[1]>op.get('base',0) and op['kind']=='delete': pass
            else:
                # Preserve both concurrent edits. A stale edit cannot resurrect a deleted ID.
                if old and old[1]>op.get('base',0) and op['kind']=='put':
                    if old[0] is not None and json.loads(old[0])==value:
                        db.execute('INSERT INTO drawing_ops VALUES (?,?)',(cid,op['op']));continue
                    target='conflict-'+op['op'];value={**value,'id':target}
                revision+=1
                db.execute('INSERT OR REPLACE INTO drawings VALUES (?,?,?,?)',(cid,target,None if op['kind']=='delete' else json.dumps(value,allow_nan=False),revision))
            db.execute('INSERT INTO drawing_ops VALUES (?,?)',(cid,op['op']))
        rows=db.execute('SELECT value FROM drawings WHERE cid=? AND value IS NOT NULL ORDER BY rev',(cid,)).fetchall()
        return dict(con_id=cid,revision=revision,drawings=[json.loads(row[0]) for row in rows])
