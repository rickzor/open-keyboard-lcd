#!/usr/bin/env python3
"""One persistent animated weather card; hourly Open-Meteo updates."""
import argparse
import fcntl
import json
from pathlib import Path
import sys
import time
from PIL import Image, ImageDraw
import render_weather as art
sys.path.insert(0,str(art.ROOT/'examples-sandbox'/'notification-display'))
import display
from widgets import weather, condition, font, clipped

DEFAULT_CONFIG=Path(__file__).with_name('weather.json')

def load_config(path):
    c=json.loads(path.read_text())
    if not -90<=float(c['latitude'])<=90 or not -180<=float(c['longitude'])<=180:
        raise ValueError('Latitude/longitude out of range')
    if c['units'] not in ('fahrenheit','celsius'): raise ValueError('Unsupported units')
    if not str(c['location']).strip(): raise ValueError('Location label is required')
    return c

def icon_kind(data):
    label=condition(data['code'])
    return {'Clear':'SUNNY' if data['day'] else 'MOON',
        'Partly cloudy':'SUN AND CLOUD' if data['day'] else 'MOON AND CLOUD',
        'Cloudy':'CLOUDY','Fog':'FOG','Rain':'RAIN','Snow':'SNOW',
        'Thunderstorm':'THUNDER'}.get(label,'CLOUDY')

def render(data,location):
    frames=[]
    for n in range(art.FRAMES):
        im=Image.new('RGB',(240,136),'black');d=ImageDraw.Draw(im)
        icon=art.frame(icon_kind(data),n,labels=False).crop((57,15,183,117)).resize((88,72),Image.Resampling.LANCZOS)
        im.paste(icon,(145,33))
        d.text((12,9),clipped(d,location,216,font(15)),font=font(15),fill='#a6c8e0')
        d.text((12,36),f"{data['temperature']:.0f}°{data['unit']}",font=font(36),fill='white')
        d.text((12,83),condition(data['code']),font=font(18),fill='white')
        d.text((12,115),f"{data['time'][11:16]} local · Open-Meteo",font=font(10),fill='#6f899b')
        frames.append(im)
    return frames

def refresh(controller,config,out,provider=weather):
    data=provider(config['latitude'],config['longitude'],config['units'])
    frames=render(data,config['location']);encoded=art.encode_frames(frames,fps=art.FPS)
    if len(encoded)>display.BLOCK: raise ValueError('Weather card exceeds safe first-block size')
    out.mkdir(parents=True,exist_ok=True)
    frames[0].save(out/'current-weather.gif',save_all=True,append_images=frames[1:],duration=[120,130]*8,loop=0,optimize=False)
    frames[4].save(out/'current-weather.png');(out/'current-weather.qgif').write_bytes(encoded)
    digest=display.digest(encoded)
    if controller.state.get('active')=='persistent' and controller.state.get('notification',{}).get('sha256')==digest:
        with controller.transport() as keyboard: controller.checked(keyboard)
        print('Weather unchanged; no flash write.',flush=True)
    else: controller.show_animation(encoded,'weather:'+digest,persistent=True)
    report={'location':config['location'],**data,'bytes':len(encoded),'checked_at':time.time(),'next_check_at':time.time()+3600}
    display.save_ledger(out/'current-weather.json',report)
    print(f"{config['location']}: {data['temperature']}°{data['unit']}, {condition(data['code'])}; {len(encoded):,} bytes. Next check in one hour.",flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=DEFAULT_CONFIG)
    p.add_argument('--state',type=Path,default=art.ROOT/'state'/'weather-display')
    p.add_argument('--out',type=Path,default=art.ROOT/'state'/'weather-live')
    p.add_argument('--once',action='store_true');a=p.parse_args()
    a.state.mkdir(parents=True,exist_ok=True)
    with (a.state/'controller.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        controller=display.ResidentDisplay(a.state)
        if not controller.state: raise RuntimeError('Initialize the weather display first; see README')
        while True:
            # Provider failures happen before any USB mutation. Preserve the last screen.
            try:
                c=load_config(a.config)
                data=weather(c['latitude'],c['longitude'],c['units'])
            except (OSError,RuntimeError,ValueError,KeyError) as error:
                print(f'Weather fetch/config failed; keeping last screen: {error}',flush=True)
                if a.once: raise
                time.sleep(300);continue
            # HID failures stop the worker; never automatically repeat a partial erase/write.
            refresh(controller,c,a.out,provider=lambda *_:data)
            if a.once:return
            time.sleep(3600)
if __name__=='__main__':main()
