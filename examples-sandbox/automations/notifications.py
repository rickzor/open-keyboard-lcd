#!/usr/bin/env python3
"""SANDBOX, not end-to-end verified: authenticated loopback notification inbox; no USB access in this process."""
import argparse
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import os
from pathlib import Path
import secrets
import sqlite3
import time
import urllib.error
import urllib.request
import uuid

from notification_cards import PRESETS, ICONS

DEFAULT_DIR=Path(__file__).resolve().parents[2]/'state'/'notifications'


def validate(payload):
    if not isinstance(payload,dict): raise ValueError('Expected a JSON object')
    allowed={'id','source','title','message','duration','ttl','priority','template','theme','icon','animate'}
    if set(payload)-allowed: raise ValueError('Unknown notification field')
    template=payload.get('template','message')
    if not isinstance(template,str) or template not in PRESETS: raise ValueError('Unknown template')
    result={'template':template}
    theme=payload.get('theme',{})
    if not isinstance(theme,dict) or set(theme)-{'background','accent','text','muted'}:
        raise ValueError('Invalid theme')
    if any(not isinstance(v,str) or not re.fullmatch(r'#[0-9A-Fa-f]{6}',v) for v in theme.values()):
        raise ValueError('Theme colors must be #RRGGBB')
    result['theme']=theme
    icon=payload.get('icon',PRESETS[template]['icon'])
    if not isinstance(icon,str) or icon not in ICONS: raise ValueError('Unknown icon')
    result['icon']=icon
    animate=payload.get('animate',True)
    if not isinstance(animate,bool): raise ValueError('animate must be a boolean')
    result['animate']=animate
    for key,default,limit in [('id',str(uuid.uuid4()),160),('source','Automation',40),('title',PRESETS[template]['title'],80),('message','',240)]:
        value=payload.get(key,default)
        if not isinstance(value,str) or len(value)>limit or (key!='message' and not value.strip()):
            raise ValueError(f'Invalid {key}')
        result[key]=' '.join(value.split())
    for key,default,low,high in [('duration',15,5,120),('ttl',300,5,3600),('priority',5,0,9)]:
        value=payload.get(key,default)
        if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:
            raise ValueError(f'Invalid {key}')
        result[key]=value
    return result


class Inbox:
    def __init__(self,folder=DEFAULT_DIR):
        self.folder=Path(folder); self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.database=self.folder/'inbox.sqlite3'
        self.token_path=self.folder/'token'
        try:
            fd=os.open(self.token_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError: pass
        else:
            with os.fdopen(fd,'w') as stream: stream.write(secrets.token_urlsafe(32))
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS notices (id TEXT PRIMARY KEY, body TEXT, received REAL, expires REAL, priority INTEGER, delivered INTEGER DEFAULT 0)')
        os.chmod(self.database,0o600)

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.database,timeout=5)
        try:
            with db: yield db
        finally: db.close()

    def submit(self,payload,now=None):
        now=time.time() if now is None else now
        item=validate(payload)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            # Retain only IDs (not private message text) for 24h duplicate protection.
            db.execute('DELETE FROM notices WHERE received < ?', (now-86400,))
            db.execute('UPDATE notices SET body=NULL, delivered=1 WHERE expires<=?',(now,))
            if db.execute('SELECT 1 FROM notices WHERE id=?',(item['id'],)).fetchone():
                return {'id':item['id'],'status':'duplicate'}
            if db.execute('SELECT COUNT(*) FROM notices WHERE delivered=0').fetchone()[0]>=100:
                raise OverflowError('Notification queue is full')
            if db.execute('SELECT COUNT(*) FROM notices').fetchone()[0]>=10000:
                raise OverflowError('Daily notification limit reached')
            db.execute('INSERT INTO notices VALUES (?,?,?,?,?,0)',(item['id'],json.dumps(item),now,now+item['ttl'],item['priority']))
        return {'id':item['id'],'status':'queued'}

    def peek(self,now):
        with self.connect() as db:
            db.execute('UPDATE notices SET body=NULL, delivered=1 WHERE expires<=?',(now,))
            row=db.execute('SELECT body, expires FROM notices WHERE delivered=0 ORDER BY priority DESC, received ASC, id ASC LIMIT 1').fetchone()
        if not row: return None
        item=json.loads(row[0]); item['_expires']=row[1]
        return item

    def acknowledge(self,notice_id):
        with self.connect() as db:
            db.execute('UPDATE notices SET body=NULL, delivered=1 WHERE id=?',(notice_id,))


def notification_key(item):
    return 'notice:'+hashlib.sha256(item['id'].encode()).hexdigest()


def serve(inbox,port=8765):
    token=inbox.token_path.read_text().strip()
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup(); self.connection.settimeout(5)
        def log_message(self,*args): pass  # Do not log tokens or private messages.
        def reply(self,status,data):
            body=json.dumps(data).encode()
            self.send_response(status); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            if self.path!='/notify': return self.reply(404,{'error':'Not found'})
            # No browser-origin requests or cross-origin access. Native local clients only.
            if self.headers.get('Origin'): return self.reply(403,{'error':'Browser origins are not accepted'})
            if not secrets.compare_digest(self.headers.get('Authorization','').encode(), ('Bearer '+token).encode()):
                return self.reply(401,{'error':'Unauthorized'})
            if self.headers.get('Transfer-Encoding') or self.headers.get_content_type()!='application/json':
                return self.reply(415,{'error':'Send a bounded JSON body'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8192: return self.reply(413,{'error':'Body must be 1..8192 bytes'})
                body=self.rfile.read(length)
                if len(body)!=length: raise ValueError('Incomplete body')
                result=inbox.submit(json.loads(body))
            except (ValueError,UnicodeError): return self.reply(400,{'error':'Invalid notification'})
            except OverflowError: return self.reply(429,{'error':'Inbox capacity reached'})
            except sqlite3.Error: return self.reply(503,{'error':'Inbox temporarily unavailable'})
            self.reply(202,result)
    return HTTPServer(('127.0.0.1',port),Handler)


def send(payload,folder=DEFAULT_DIR,port=8765):
    token=(Path(folder)/'token').read_text().strip()
    body=json.dumps(validate(payload)).encode()
    # Fixed loopback destination: never transmit the local bearer token to a remote URL.
    req=urllib.request.Request(f'http://127.0.0.1:{port}/notify',data=body,headers={
        'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req,timeout=10) as response: return json.load(response)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['serve','send'])
    parser.add_argument('--inbox',type=Path,default=DEFAULT_DIR)
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--source',default='Automation'); parser.add_argument('--title')
    parser.add_argument('--message',default=''); parser.add_argument('--id')
    parser.add_argument('--duration',type=int,default=15); parser.add_argument('--ttl',type=int,default=300)
    parser.add_argument('--priority',type=int,default=5)
    parser.add_argument('--template',choices=PRESETS,default='message')
    parser.add_argument('--accent',help='Override accent with #RRGGBB')
    parser.add_argument('--static',action='store_true',help='Disable status-dot animation')
    args=parser.parse_args()
    if args.command=='serve':
        inbox=Inbox(args.inbox)
        with serve(inbox,args.port) as server:
            print(f'Listening on 127.0.0.1:{server.server_port}; token file: {inbox.token_path}',flush=True)
            server.serve_forever()
    else:
        payload={k:getattr(args,k) for k in ('source','title','message','duration','ttl','priority')}
        payload['template']=args.template; payload['animate']=not args.static
        if args.accent: payload['theme']={'accent':args.accent}
        if args.title is None: payload.pop('title')
        if args.id: payload['id']=args.id
        print(json.dumps(send(payload,args.inbox,args.port)))


if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: pass
    except (OSError,ValueError,urllib.error.URLError):
        raise SystemExit('Notification request failed; check inbox service, token file, and arguments')
