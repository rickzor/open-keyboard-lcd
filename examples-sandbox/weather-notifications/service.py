#!/usr/bin/env python3
"""One USB owner: hourly weather, EventKit reminders, authenticated local notifications."""
import argparse
import fcntl
import json
import os
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'examples-sandbox/weather-display'))
import live_weather as weather_ui
from lcd_automations import due_meetings
import calendar_app
from display_sleep import DisplaySleep
from notifications import Inbox, serve, notification_key
from notification_cards import PRESETS, lines
D=weather_ui.display

def card(item):
    theme=item.get('theme',{}); accent=theme.get('accent', '#ab9cff' if item['template']=='calendar' else PRESETS[item['template']]['accent'])
    im=Image.new('RGB',(240,136),theme.get('background','black')); d=ImageDraw.Draw(im)
    d.rounded_rectangle((12,13,16,122),radius=2,fill=accent)
    d.text((27,13),weather_ui.clipped(d,item['source'].upper(),198,weather_ui.font(12)),font=weather_ui.font(12),fill=accent)
    title_lines=lines(d,item['title'],weather_ui.font(27),200,2)
    for i,line in enumerate(title_lines): d.text((25,38+i*29),line,font=weather_ui.font(27),fill=theme.get('text','white'))
    y=101 if len(title_lines)>1 else 83
    d.text((27,y),weather_ui.clipped(d,item['message'],198,weather_ui.font(18)),font=weather_ui.font(18),fill=theme.get('muted','#d1c9ff'))
    return weather_ui.art.encode_frames([im],fps=1)

def sleep_frames(mode):
    if mode=='black':return [Image.new('RGB',(240,136),'black')]
    frames=[]
    for n in range(16):
        im=Image.new('RGB',(240,136),'black');d=ImageDraw.Draw(im)
        icon=weather_ui.art.frame('MOON',n,labels=False).crop((57,15,183,117)).resize((72,58),Image.Resampling.LANCZOS)
        icon=icon.point(lambda v:int(v*.35));im.paste(icon,(70,33))
        for i in range(3):
            y=51-i*12-(n//4)%2
            d.text((145+i*13,y),'z',font=weather_ui.font(12+i*2),fill='#34405b')
        frames.append(im)
    return frames

def sleep_payload(mode):return weather_ui.art.encode_frames(sleep_frames(mode),fps=8)

class Screen:
    def __init__(self,controller,folder,clock=time.time):
        self.controller=controller;self.folder=folder;self.clock=clock
        self.path=folder/'service.json'
        self.state=json.loads(self.path.read_text()) if self.path.exists() else {'until':0,'seen':[]}
    def save(self): D.save_ledger(self.path,self.state)
    def weather(self,data):
        # Cache first, even while a notification is visible; return uses the latest weather.
        path=self.folder/'weather.qgif'; tmp=path.with_suffix('.tmp');tmp.write_bytes(data);tmp.replace(path)
    def show(self,data):
        current=self.controller.state
        if current.get('notification',{}).get('sha256')!=D.digest(data) or current.get('active')!='persistent':
            self.controller.show_animation(data,'service:'+D.digest(data),persistent=True)
        else:
            with self.controller.transport() as keyboard:self.controller.checked(keyboard)
    def set_sleep(self,asleep,payload):
        if asleep==self.state.get('sleeping',False):return False
        if asleep:
            self.show(payload)
        else:
            path=self.folder/'weather.qgif'
            if not path.exists():return False
            self.show(path.read_bytes())
        self.state.update(sleeping=asleep,until=0);self.save()
        print('Display sleep animation active.' if asleep else 'Display awake; weather restored.',flush=True)
        return True
    def tick(self,inbox):
        now=self.clock();item=inbox.peek(now)
        if self.state.get('sleeping',False):
            if item:inbox.acknowledge(item['id'])
            return
        if item:
            key=notification_key(item)
            if key not in self.state['seen']:
                payload=card(item)
                # Write intent before USB so restart can restore weather after an interruption.
                self.state['until']=now+item['duration'];self.save()
                self.show(payload)
                self.state['until']=self.clock()+item['duration']
                self.state['seen']=(self.state['seen']+[key])[-1024:];self.save()
                print('Notification displayed.',flush=True)
            inbox.acknowledge(item['id'])
        elif now>=self.state['until']:
            path=self.folder/'weather.qgif'
            if path.exists():
                data=path.read_bytes()
                if self.state['until'] or self.controller.state.get('notification',{}).get('sha256')!=D.digest(data):
                    self.show(data);self.state['until']=0;self.save()
                    print('Weather displayed.',flush=True)

def weather_worker(config,results,stop):
    while not stop.is_set():
        delay=3600
        try:
            c=weather_ui.load_config(config);data=weather_ui.weather(c['latitude'],c['longitude'],c['units'])
            frames=weather_ui.render(data,c['location']);payload=weather_ui.art.encode_frames(frames,fps=8)
            if len(payload)>D.BLOCK:raise ValueError('Weather exceeds one block')
            results.put(payload)
            print('Weather fetched; next check in one hour.',flush=True)
        except Exception as error:
            delay=300;print('Weather unavailable; retry in five minutes ('+type(error).__name__+').',flush=True)
        stop.wait(delay)

def calendar_worker(inbox,stop):
    available=None
    while not stop.is_set():
        delay=10
        try:
            request=ROOT/'state/weather-notifications/authorize-calendar'
            if request.exists():
                request.unlink()
                calendar_app.read(authorize=True)
            now=time.time();events=calendar_app.read()
            if available is not True:print('Calendar connection ready.',flush=True)
            available=True
            for start,key,event in due_meetings(events,now,{}):
                inbox.submit({'id':'calendar:'+key,'source':'Calendar','template':'calendar',
                    'title':event['title'][:80],'message':'In 1 minute' if start-now>40 else 'Starting soon',
                    'duration':60,'ttl':max(5,min(60,int(start-now))),'priority':8})
        except Exception as error:
            if available is not False:print('Calendar unavailable; authorize calendar-reader and sync accounts ('+type(error).__name__+').',flush=True)
            available=False;delay=60
        stop.wait(delay)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state',type=Path,default=ROOT/'state/weather-display')
    p.add_argument('--config',type=Path,default=weather_ui.DEFAULT_CONFIG)
    p.add_argument('--inbox',type=Path,default=ROOT/'state/weather-notifications/inbox')
    p.add_argument('--cache',type=Path,default=ROOT/'state/weather-notifications')
    p.add_argument('--seed-weather',type=Path)
    p.add_argument('--display-config',type=Path,default=Path(__file__).with_name('display.json'))
    p.add_argument('--port',type=int,default=8765);a=p.parse_args()
    os.environ.pop('OPENAI_API_KEY',None)  # Not needed by this service or its child processes.
    a.cache.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (a.state/'controller.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        controller=D.ResidentDisplay(a.state)
        # Refuse pending/foreign state before launching any producers.
        with controller.transport() as keyboard:controller.checked(keyboard)
        screen=Screen(controller,a.cache)
        mode=json.loads(a.display_config.read_text()).get('sleep_mode','animation')
        if mode not in ('animation','black','disabled'):raise ValueError('Invalid sleep_mode')
        detector=DisplaySleep() if mode!='disabled' else None
        sleeping_image=sleep_payload(mode) if detector else None
        next_display_check=0
        print('Display sleep mode: '+mode,flush=True)
        if not (a.cache/'weather.qgif').exists() and a.seed_weather:screen.weather(a.seed_weather.read_bytes())
        inbox=Inbox(a.inbox);stop=threading.Event();results=queue.Queue()
        with serve(inbox,a.port) as server:
            threads=[threading.Thread(target=server.serve_forever,daemon=True),
                threading.Thread(target=weather_worker,args=(a.config,results,stop),daemon=True),
                threading.Thread(target=calendar_worker,args=(inbox,stop),daemon=True)]
            for thread in threads:thread.start()
            print('Background display ready; local notifications on 127.0.0.1:'+str(a.port),flush=True)
            try:
                while True:
                    try:
                        while True:screen.weather(results.get_nowait())
                    except queue.Empty:pass
                    if time.monotonic()>=next_display_check:
                        next_display_check=time.monotonic()+1
                        asleep=detector.poll() if detector else False
                        if asleep is not None and screen.set_sleep(asleep,sleeping_image):
                            if not asleep:
                                while (queued:=inbox.peek(time.time())) is not None:inbox.acknowledge(queued['id'])
                            time.sleep(.25);continue
                    screen.tick(inbox);time.sleep(.25)
            finally:stop.set();server.shutdown()
if __name__=='__main__':main()
