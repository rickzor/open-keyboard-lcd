#!/usr/bin/env python3
"""SANDBOX, live integration untested: optional Slack Socket Mode adapter: app mentions -> local LCD inbox."""
import argparse
import logging
import os
import sqlite3
import threading
from notifications import Inbox, DEFAULT_DIR


def map_event(payload, include_text=False):
    event=payload.get('event',{})
    if event.get('type')!='app_mention' or event.get('bot_id'): return None
    event_id=payload.get('event_id')
    if not isinstance(event_id,str) or not event_id: return None
    return {'id':'slack:'+event_id,'source':'Slack','template':'slack',
            'title':'New app mention',
            'message':str(event.get('text',''))[:240] if include_text else 'Open Slack to read the message.',
            'priority':5,'duration':15,'ttl':300}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inbox',default=str(DEFAULT_DIR))
    parser.add_argument('--include-text',action='store_true',help='Display private Slack message text')
    args=parser.parse_args()
    if not os.environ.get('SLACK_APP_TOKEN') or not os.environ.get('SLACK_BOT_TOKEN'):
        raise SystemExit('Set SLACK_APP_TOKEN and SLACK_BOT_TOKEN in the environment')
    try:
        from slack_sdk.web import WebClient
        from slack_sdk.socket_mode import SocketModeClient
        from slack_sdk.socket_mode.response import SocketModeResponse
    except ImportError:
        raise SystemExit('Install optional dependency: pip install slack-sdk') from None
    inbox=Inbox(args.inbox)
    client=SocketModeClient(app_token=os.environ['SLACK_APP_TOKEN'],
        web_client=WebClient(token=os.environ['SLACK_BOT_TOKEN']))
    def process(client,req):
        if req.type!='events_api': return
        item=map_event(req.payload,args.include_text)
        if item:
            try: inbox.submit(item)
            except (OSError,ValueError,OverflowError,sqlite3.Error):
                logging.warning('Could not queue Slack notification; leaving envelope unacknowledged for retry')
                return
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
    client.socket_mode_request_listeners.append(process)
    client.connect()
    try: threading.Event().wait()
    finally: client.close()


if __name__=='__main__':
    logging.basicConfig(level=logging.WARNING)
    try: main()
    except KeyboardInterrupt: pass
