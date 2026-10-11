#!/usr/bin/env python3
"""SANDBOX, not end-to-end verified: opt-in background LCD examples. Default output is local preview files only."""
import argparse
import datetime as dt
import fcntl
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from qgif import encode_frames, inspect_qgif
from widgets import weather, weather_frames, meeting_frames, giphy_frames, save_gif

LOG=logging.getLogger('lcd-examples')


def save_json(path, data):
    path=Path(path); temporary=path.with_suffix('.tmp')
    with temporary.open('w') as stream:
        json.dump(data,stream,indent=2); stream.flush()
        import os
        os.fsync(stream.fileno())
    temporary.replace(path)


class Display:
    """Owns the complete single-image display set. Never claims to preserve unknown on-device GIFs."""
    def __init__(self, folder, usb=False, allow_recovery=False):
        self.folder=Path(folder); self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/'display.json'; self.usb=usb
        self.state=json.loads(self.path.read_text()) if self.path.exists() else {}
        if self.state.get('usb',usb)!=usb:
            raise RuntimeError('Use separate state directories for preview and USB modes')
        if self.state.get('pending') and not allow_recovery:
            raise RuntimeError('Previous write was interrupted. Reinitialize explicitly; no automatic retry.')

    def asset(self, frames, fps, label):
        data=encode_frames(frames,fps=fps)
        inspect_qgif(data)
        # Bound flash traffic and interruption latency for widgets/alerts.
        if len(data)>524288: raise ValueError('Example animation exceeds 512 KiB budget')
        name=hashlib.sha256(data).hexdigest()
        path=self.folder/(name+'.qgif'); path.write_bytes(data)
        save_gif(frames,self.folder/(name+'.gif'),fps)
        return {'hash':name,'label':label}

    def commit(self, candidate, image, initialize=False):
        data=(self.folder/(image['hash']+'.qgif')).read_bytes()
        if hashlib.sha256(data).hexdigest()!=image['hash']: raise RuntimeError('Stored image is corrupt')
        changed=image['hash']!=self.state.get('visible',{}).get('hash')
        if changed or initialize:
            if self.usb:
                from rt82 import Keyboard
                with (ROOT/'.usb.lock').open('w') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    keyboard=Keyboard()
                    try:
                        keyboard.activate()
                        if not initialize and keyboard.inspect().hex()!=self.state.get('table'):
                            raise RuntimeError('Device metadata changed; refusing to overwrite another image set')
                        pending=dict(self.state,pending=True,usb=True)
                        save_json(self.path,pending)
                        table=keyboard.upload_set([data])
                        if keyboard.inspect()!=table: raise RuntimeError('Upload metadata mismatch')
                        keyboard.command(0x11); candidate['table']=table.hex()
                    finally: keyboard.close()
            (self.folder/'current.gif').write_bytes((self.folder/(image['hash']+'.gif')).read_bytes())
        candidate.update(visible=image,usb=self.usb,pending=False)
        save_json(self.path,candidate); self.state=candidate
        # Keep only active/restorable images, not a history of calendar titles/media.
        keep={v['hash'] for k,v in candidate.items() if k in ('base','visible','restore') and v}
        for path in self.folder.iterdir():
            if path.suffix in ('.gif','.qgif') and len(path.stem)==64 and path.stem not in keep:
                path.unlink()

    def base(self, image, initialize=False):
        if self.usb and not self.state and not initialize:
            raise RuntimeError('Run init --replace-all-slots to explicitly establish the managed display')
        candidate={'base':image} if initialize else dict(self.state,base=image)
        # Freeze both display and restoration snapshot while an alert is active.
        self.commit(candidate,self.state['visible'] if self.state.get('until') and not initialize else image,initialize)

    def alert(self, image, until, event_key):
        if not self.state.get('base'): raise RuntimeError('Initialize a base image before alerts')
        if event_key in self.state.get('seen',{}): return
        candidate=dict(self.state)
        candidate['restore']=candidate.get('restore') or candidate['visible']
        candidate['until']=max(until,candidate.get('until',0))
        candidate['seen']={k:v for k,v in candidate.get('seen',{}).items() if v>until-86400}
        candidate['seen'][event_key]=until
        self.commit(candidate,image)

    def expire(self, now):
        if self.state.get('until') and now>=self.state['until']:
            candidate=dict(self.state)
            image=candidate.pop('restore'); candidate.pop('until')
            # Restore exactly the previous image; later periodic jobs may replace it.
            candidate['base']=image
            self.commit(candidate,image)
            return True
        return False


def due_meetings(events, now, seen):
    result=[]
    for event in events:
        if event.get('all_day') or event.get('declined'): continue
        start=float(event['start']); key=hashlib.sha256(f"{event['id']}:{start}".encode()).hexdigest()
        if 0 < start-now <= 60 and key not in seen:
            result.append((start,key,event))
    return sorted(result,key=lambda item:(item[0],item[1]))


def read_events(config):
    if config.get('calendar_fixture'):
        return json.loads(Path(config['calendar_fixture']).read_text())
    helper=Path(config.get('calendar_helper',Path(__file__).with_name('calendar-reader')))
    completed=subprocess.run([str(helper)],capture_output=True,text=True,timeout=20)
    if completed.returncode:
        # Avoid dumping private event data or helper internals into daemon logs.
        raise RuntimeError('Calendar access unavailable; run calendar-reader --authorize interactively')
    return json.loads(completed.stdout)


def notification_tick(display, config, now):
    """One display worker consumes highest-priority queued notices, without USB in HTTP handlers."""
    if not config.get('notifications') or display.state.get('until'): return False
    from notifications import Inbox, DEFAULT_DIR, notification_key
    from notification_cards import notification_frames
    inbox=Inbox(config.get('notification_inbox',DEFAULT_DIR))
    item=inbox.peek(now)
    if not item: return False
    key=notification_key(item)
    if key not in display.state.get('seen',{}):
        image=display.asset(notification_frames(item),4,'notification')
        display.alert(image,min(now+item['duration'],item['_expires']),key)
    inbox.acknowledge(item['id'])
    return bool(display.state.get('until'))


def tick(display, config, now, schedule, providers=None):
    providers=providers or {'weather':weather,'giphy':giphy_frames,'calendar':read_events}
    if display.expire(now):
        return
    if config.get('calendar',False) and now>=schedule.get('calendar',0):
        schedule['calendar']=now+10
        try:
            meetings=due_meetings(providers['calendar'](config),now,display.state.get('seen',{}))
            if meetings:
                start,key,event=meetings[0]
                label=dt.datetime.fromtimestamp(start).strftime('%H:%M')
                title=event['title'] if config.get('show_meeting_titles',False) else 'Upcoming meeting'
                image=display.asset(meeting_frames(title,label),4,'meeting')
                display.alert(image,start+15,key)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError,KeyError):
            if display.path.exists() and json.loads(display.path.read_text()).get('pending'): raise
            LOG.warning('Calendar check failed; previous display retained')
    if notification_tick(display,config,now): return
    # Avoid provider downloads/writes while an alert is active.
    if display.state.get('until'): return
    # When combined, hourly GIF takes precedence at coincident deadlines; weather appears halfway through the hour.
    giphy_updated=False
    for kind,interval in [('giphy',3600),('weather',1800)]:
        if not config.get(kind,False) or now<schedule.get(kind,0): continue
        schedule[kind]=now+interval
        if kind=='weather' and giphy_updated: continue
        try:
            if kind=='weather':
                data=providers[kind](config.get('latitude',37.7749),config.get('longitude',-122.4194),config.get('units','fahrenheit'))
                frames=weather_frames(data,config.get('location','San Francisco, CA')); fps=6
            else:
                frames,_=providers[kind](config.get('giphy_tag','cute animals'),config.get('approved_giphy_ids')); fps=10
            image=display.asset(frames,fps,kind); display.base(image)
            if kind=='giphy': giphy_updated=True
        except (OSError,ValueError,RuntimeError,KeyError):
            if display.path.exists() and json.loads(display.path.read_text()).get('pending'): raise
            LOG.warning('%s update failed; previous display retained',kind)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['demo','once','run','init'])
    parser.add_argument('--config',type=Path,default=Path(__file__).with_name('weather.json'))
    parser.add_argument('--state',type=Path,default=ROOT/'state/automation-preview')
    parser.add_argument('--usb',action='store_true',help='Actually replace the keyboard display with one managed image')
    parser.add_argument('--replace-all-slots',action='store_true',help='Required for USB init; replaces existing keyboard images')
    args=parser.parse_args()
    if args.command=='demo' and args.usb: parser.error('demo never writes USB')
    args.state.mkdir(parents=True,exist_ok=True)
    with (args.state/'runner.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        display=Display(args.state,args.usb,allow_recovery=args.command=='init')
        if args.command in ('demo','init'):
            if args.usb and not args.replace_all_slots: parser.error('USB init requires --replace-all-slots')
            sample={'temperature':63,'unit':'F','code':2,'day':True,'time':'2026-10-11T12:30'}
            image=display.asset(weather_frames(sample),6,'sample weather'); display.base(image,initialize=True)
            if args.command=='demo':
                alert=display.asset(meeting_frames('Design review','12:31'),4,'sample meeting')
                save_gif(meeting_frames('Design review','12:31'),args.state/'meeting-preview.gif',4)
                display.alert(alert,61,'demo'); display.expire(62)
                assert display.state['visible']==image
            print(f'Preview: {args.state / "current.gif"}'); return
        config=json.loads(args.config.read_text())
        if args.usb and not display.state: raise RuntimeError('Initialize the managed display before running with --usb')
        schedule={}
        while True:
            tick(display,config,time.time(),schedule)
            if args.command=='once': break
            time.sleep(1)


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO,format='%(levelname)s %(message)s')
    try: main()
    except KeyboardInterrupt: pass
    except (OSError,ValueError,RuntimeError) as error:
        LOG.error('%s',error); sys.exit(1)
