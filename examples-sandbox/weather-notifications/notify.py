#!/usr/bin/env python3
"""Send a local LCD notification without opening a browser."""
import argparse
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'examples-sandbox/automations'))
from notifications import send
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('title');p.add_argument('message',nargs='?',default='')
p.add_argument('--source',default='Automation');p.add_argument('--template',default='message')
p.add_argument('--duration',type=int,default=60);p.add_argument('--accent')
a=p.parse_args();payload=dict(title=a.title,message=a.message,source=a.source,template=a.template,duration=a.duration)
if a.accent:payload['theme']={'accent':a.accent}
print(send(payload,ROOT/'state/weather-notifications/inbox'))
