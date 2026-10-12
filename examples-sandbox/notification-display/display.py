#!/usr/bin/env python3
"""Experimental resident default GIF + one reusable notification block."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'examples-sandbox'/'automations'))
import rt82
from pool import save_ledger
from qgif import encode_frames, inspect_qgif
from notification_cards import notification_frames
from notifications import Inbox, notification_key, serve, validate

BLOCK=65536
DEFAULT_NAMES=['Himalaya - Annapurna']
DEFAULT_STATE=ROOT/'state'/'notification-display'


def digest(data): return hashlib.sha256(data).hexdigest()


def table_for(entry, allocation=1):
    """One visible slot points to any resident image; allocation=1 for updates."""
    table=bytearray(56)
    table[:3]=bytes([0,1,allocation])
    table[3:8]=bytes([entry['block'],0])+entry['bytes'].to_bytes(3,'little')
    return bytes(table)


def plan(images):
    if not 1<=len(images)<=10: raise ValueError('Supply 1–10 mountain images')
    entries=[]; block=1  # Block zero belongs exclusively to notifications.
    for name,data in images:
        info=inspect_qgif(data)
        if (info['width'],info['height'])!=(240,136): raise ValueError('Images must be 240×136')
        entries.append({'name':name,'block':block,'bytes':len(data),'sha256':digest(data)})
        block+=math.ceil(len(data)/BLOCK)
    if block+1>255: raise ValueError('Resident library exceeds the protocol address/allocation limit')
    return entries,block


def notification_data(item):
    data=encode_frames(notification_frames(item),fps=8)
    if len(data)>BLOCK: raise ValueError('Notification exceeds reserved first block')
    return data


def prepare(collection,folder,names):
    folder=Path(folder)
    if (folder/'library.json').exists(): raise ValueError('Library already prepared; choose a new folder')
    records=json.loads(Path(collection).read_text())
    by_name={r['name']:r for r in records}
    if len(set(names))!=len(names): raise ValueError('Duplicate mountain name')
    images=[]
    for name in names:
        row=by_name[name]
        path=Path(row['qgif']) if row.get('qgif') else Path(row['directory'])/'flyover.qgif'
        data=path.read_bytes()
        if row.get('sha256') and digest(data)!=row['sha256']: raise ValueError('Source hash mismatch')
        images.append((name,data))
    entries,blocks=plan(images)
    folder.mkdir(parents=True,exist_ok=True)
    for i,((name,data),entry) in enumerate(zip(images,entries)):
        entry['file']=f'mountain-{i+1}.qgif'
        (folder/entry['file']).write_bytes(data)
    save_ledger(folder/'library.json',{'version':1,'blocks':blocks,'mountains':entries})
    return entries,blocks


def load_library(folder):
    folder=Path(folder); config=json.loads((folder/'library.json').read_text())
    images=[]
    for entry in config['mountains']:
        path=folder/entry['file']
        if path.resolve().parent!=folder.resolve(): raise ValueError('Invalid library image path')
        data=path.read_bytes()
        if digest(data)!=entry['sha256']: raise ValueError('Resident-library source hash changed')
        images.append((entry['name'],data))
    expected,blocks=plan(images)
    if blocks!=config['blocks'] or any(any(a[k]!=b[k] for k in a) for a,b in zip(expected,config['mountains'])):
        raise ValueError('Library allocation differs from its payloads')
    return config,images


@contextmanager
def usb():
    with (ROOT/'.usb.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        keyboard=rt82.Keyboard()
        try: keyboard.activate(); yield keyboard
        finally: keyboard.close()


def configure(keyboard,table):
    keyboard.command(0x1B,0,0,0,56)
    keyboard.keyboard_command(0xE3,bytes([0,0,0,1,0,0,1]))
    time.sleep(.1)
    keyboard.command(0x14,0,0,0,56)
    keyboard.command(0x15,0,0,0,56,data=table)
    keyboard.command(0x15,56,0,0,56)
    keyboard.command(0x15,112,0,0,16)
    keyboard.command(0x16,0,0,0,56)


def write_image(keyboard,data,block,start=0,checkpoint=None):
    if start<0 or start>len(data) or (start!=len(data) and start%56): raise ValueError('Invalid resume offset')
    for offset in range(start,len(data),56):
        address=block*BLOCK+offset; chunk=data[offset:offset+56]
        try:
            keyboard.command(0x19,address&255,(address>>8)&255,(address>>16)&255,len(chunk),data=chunk)
        except (OSError,RuntimeError) as error:
            raise RuntimeError(f'Image write failed at block {block}, offset {offset}, address 0x{address:06x}: {error}') from error
        if offset and offset%(56*2048)==0:
            if checkpoint: checkpoint(offset+len(chunk))
            print(f'  {offset}/{len(data)} bytes',flush=True)
    if checkpoint: checkpoint(len(data))


def finish(keyboard,expected):
    keyboard.command(0x1A); keyboard.sync_time()
    actual=keyboard.inspect(); keyboard.command(0x11)
    if actual!=expected: raise RuntimeError('Playback metadata mismatch; stopping')


class ResidentDisplay:
    def __init__(self,folder=DEFAULT_STATE,transport=usb,clock=time.time,choose=secrets.choice):
        self.folder=Path(folder); self.path=self.folder/'resident.json'
        self.transport=transport; self.clock=clock; self.choose=choose
        self.state=json.loads(self.path.read_text()) if self.path.exists() else None

    def save(self): save_ledger(self.path,self.state)

    def checked(self,keyboard):
        if not self.state or self.state['status']!='ready':
            raise RuntimeError('Resident library is not ready; inspect pending state before recovery')
        if keyboard.via.identity!=self.state['identity']: raise RuntimeError('Keyboard identity changed')
        if keyboard.inspect().hex()!=self.state['table_hex']:
            raise RuntimeError('Keyboard metadata changed outside this controller; refusing writes')

    def initialize(self,library):
        config,images=load_library(library)
        placeholder=notification_data(validate({'template':'focus','title':'Mountain display','message':'Ready for notifications','animate':False}))
        notice={'name':'Notification','block':0,'bytes':len(placeholder),'sha256':digest(placeholder)}
        initial=table_for(notice,config['blocks'])
        self.folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.transport() as keyboard:
            self.state={'version':1,'status':'initializing','identity':keyboard.via.identity,
                'mountains':config['mountains'],'notification':notice,'table_hex':initial.hex(),
                'active':'notification','until':0,'seen':[],'blocks':config['blocks']}
            self.save()
            save_ledger(ROOT/'state'/'append-pool.json',{'status':'invalidated-by-resident-library'})
            configure(keyboard,initial)
            keyboard.command(0x18,0,0,0,1,data=bytes([config['blocks']+1]),wait=False)
            time.sleep(.5*(config['blocks']+1))
            write_image(keyboard,placeholder,0)
            for index,(entry,(_,data)) in enumerate(zip(config['mountains'],images)):
                print(f"Loading {entry['name']} at block {entry['block']}: {len(data)} bytes",flush=True)
                self.initial_checkpoint(index,0)
                write_image(keyboard,data,entry['block'],checkpoint=lambda offset:self.initial_checkpoint(index,offset))
            finish(keyboard,initial)
            self.state['status']='ready'; self.save()
        self.random_mountain()

    def initial_checkpoint(self,index,offset):
        self.state['checkpoint']={'image_index':index,'offset':offset}; self.save()

    def resume_initialize(self,library):
        """Explicit retry of identical bytes in an already erased, owned library.

        Never erase. A durable checkpoint can lag the last acknowledged report;
        replaying that suffix uses the same bytes at the same addresses.
        """
        config,images=load_library(library)
        if not self.state or self.state['status']!='initializing' or 'checkpoint' not in self.state:
            raise RuntimeError('No resumable library initialization checkpoint')
        if config['mountains']!=self.state['mountains'] or config['blocks']!=self.state['blocks']:
            raise RuntimeError('Resume requires the exact original library')
        checkpoint=self.state['checkpoint']; start_index=checkpoint['image_index']; start_offset=checkpoint['offset']
        if not 0<=start_index<len(images): raise ValueError('Invalid initialization checkpoint')
        initial=bytes.fromhex(self.state['table_hex'])
        with self.transport() as keyboard:
            if keyboard.via.identity!=self.state['identity'] or keyboard.inspect()!=initial:
                raise RuntimeError('Device or metadata differs from interrupted initialization')
            configure(keyboard,initial)  # Re-enter transfer mode; no erase.
            for index in range(start_index,len(images)):
                entry=config['mountains'][index]; data=images[index][1]
                offset=start_offset if index==start_index else 0
                print(f"Resuming {entry['name']} at byte {offset}; no erase",flush=True)
                self.initial_checkpoint(index,offset)
                write_image(keyboard,data,entry['block'],offset,lambda next_offset:self.initial_checkpoint(index,next_offset))
            finish(keyboard,initial)
            self.state['status']='ready'; self.save()
        self.random_mountain()

    def pending(self,kind,table,active):
        self.state['pending']={'kind':kind,'before':self.state['table_hex'],'after':table.hex(),'active':active}
        self.state['status']='pending'; self.save()

    def complete(self,table,active):
        self.state.update(status='ready',table_hex=table.hex(),active=active)
        self.state.pop('pending',None)

    def select(self,index):
        if not self.state or not 0<=index<len(self.state['mountains']): raise ValueError('Invalid mountain index')
        table=table_for(self.state['mountains'][index])
        with self.transport() as keyboard:
            self.checked(keyboard)
            self.pending('select',table,index)
            configure(keyboard,table)  # No erase and no image-data writes.
            finish(keyboard,table)
            self.complete(table,index)
            self.state.update(until=0,last_mountain=index); self.save()
        print('Showing '+self.state['mountains'][index]['name'],flush=True)

    def random_mountain(self):
        if not self.state: raise RuntimeError('Initialize the resident library first')
        choices=list(range(len(self.state['mountains'])))
        # Avoid immediately choosing the same mountain when there is a choice.
        previous=self.state.get('last_mountain',self.state.get('active'))
        if len(choices)>1 and previous in choices: choices.remove(previous)
        self.select(self.choose(choices))

    def notify(self,item):
        key=notification_key(item)
        if self.state and key in self.state.get('seen',[]): return
        data=notification_data(item)
        self.show_animation(data,key)

    def show_animation(self,data,key,*,persistent=False):
        """Show a locally encoded animation using only the notification block."""
        info=inspect_qgif(data)
        if len(data)>BLOCK or (info['width'],info['height'])!=(240,136):
            raise ValueError('Notification animation must be 240×136 and fit one 64-KiB block')
        if not persistent and self.state and key in self.state.get('seen',[]): return
        active='persistent' if persistent else 'notification'
        entry={'name':'Notification','block':0,'bytes':len(data),'sha256':digest(data)}
        table=table_for(entry,1)
        with self.transport() as keyboard:
            self.checked(keyboard)
            self.pending('notification',table,active)
            configure(keyboard,table)
            # Exact narrowly tested first-block sequence: allocation=1, index=3/count=1.
            keyboard.command(0x18,3,0,0,1,data=b'\x01',wait=False)
            time.sleep(1)
            write_image(keyboard,data,0)
            finish(keyboard,table)
            self.complete(table,active)
            self.state.update(notification=entry,until=0 if persistent else self.clock()+60,
                              seen=(self.state.get('seen',[])+[key])[-256:])
            self.save()
        print('Persistent screen displayed.' if persistent else 'Notification displayed; return timer reset to 60 seconds.',flush=True)

    def tick(self,inbox):
        item=inbox.peek(self.clock())
        if item:
            self.notify(item); inbox.acknowledge(item['id'])
        elif self.state and self.state['active']=='notification' and self.clock()>=self.state['until']:
            self.random_mountain()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state',type=Path,default=DEFAULT_STATE)
    commands=parser.add_subparsers(dest='command',required=True)
    prep=commands.add_parser('prepare',help='Copy selected QGIFs into a resident-library bundle; no USB')
    prep.add_argument('collection',type=Path); prep.add_argument('library',type=Path)
    prep.add_argument('--names',nargs='+',default=DEFAULT_NAMES)
    init=commands.add_parser('initialize',help='One-time full flash upload; replaces the current image set')
    init.add_argument('library',type=Path)
    resume=commands.add_parser('resume-initialize',help='Resume identical library bytes from a saved checkpoint; no erase')
    resume.add_argument('library',type=Path)
    run=commands.add_parser('run',help='Random mountain on startup; notifications preempt it for 60 seconds')
    run.add_argument('--port',type=int,default=8765)
    run.add_argument('--inbox',type=Path,default=ROOT/'state'/'notifications')
    select=commands.add_parser('select',help='Switch a resident mountain using metadata only')
    select.add_argument('index',type=int,help='One-based mountain index')
    commands.add_parser('random')
    commands.add_parser('status')
    args=parser.parse_args()
    if args.command=='prepare':
        entries,blocks=prepare(args.collection,args.library,args.names)
        print(json.dumps({'mountains':entries,'blocks':blocks,'allocated_bytes':blocks*BLOCK},indent=2)); return
    args.state.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (args.state/'controller.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        display=ResidentDisplay(args.state)
        if args.command=='initialize': display.initialize(args.library)
        elif args.command=='resume-initialize': display.resume_initialize(args.library)
        elif args.command=='select': display.select(args.index-1)
        elif args.command=='random': display.random_mountain()
        elif args.command=='status': print(json.dumps(display.state,indent=2))
        else:
            inbox=Inbox(args.inbox)
            with serve(inbox,args.port) as server:
                # Bind before touching the display; a port conflict must not reset it.
                if not display.state or display.state['status']!='ready': raise RuntimeError('Initialize the resident library first')
                if display.state['active']!='notification' or display.clock()>=display.state['until']:
                    display.random_mountain()
                thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
                print(f'Resident display listening on 127.0.0.1:{args.port}',flush=True)
                try:
                    while True: display.tick(inbox); time.sleep(.25)
                finally: server.shutdown(); thread.join()


if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: pass
    except (OSError,ValueError,RuntimeError,KeyError) as error: raise SystemExit(str(error))
